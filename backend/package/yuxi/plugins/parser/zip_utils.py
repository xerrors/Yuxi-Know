import asyncio
import hashlib
import os
import re
import time
import zipfile
from pathlib import Path

from yuxi.storage.minio import get_minio_client
from yuxi.utils import logger

DEFAULT_IMAGE_BUCKET = "public"
DEFAULT_IMAGE_PREFIX = "unknown/kb-images"


def _normalize_object_prefix(prefix: str | None) -> str:
    normalized = (prefix or DEFAULT_IMAGE_PREFIX).strip("/")
    return normalized or DEFAULT_IMAGE_PREFIX


async def process_zip_file(
    zip_path: str,
    image_bucket: str = DEFAULT_IMAGE_BUCKET,
    image_prefix: str = DEFAULT_IMAGE_PREFIX,
) -> dict:
    """
    处理ZIP文件，提取markdown内容和图片

    Args:
        zip_path: ZIP文件路径
        image_bucket: 图片上传的目标 bucket
        image_prefix: 图片上传对象前缀

    Returns:
        dict: {
            "markdown_content": str,
            "content_hash": str,
            "images_info": list[dict]
        }
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.startswith("/") or name.startswith("\\"):
                raise ValueError(f"ZIP 包含不安全路径: {name}")
            if ".." in Path(name).parts:
                raise ValueError(f"ZIP 路径包含上级引用: {name}")

        md_files = [n for n in zf.namelist() if n.lower().endswith(".md")]
        if not md_files:
            raise ValueError("压缩包中未找到 .md 文件")

        md_file = next((n for n in md_files if Path(n).name == "full.md"), md_files[0])

        with zf.open(md_file) as f:
            markdown_content = f.read().decode("utf-8")

        images_info = []
        images_dir = find_images_directory(zf, md_file)
        normalized_prefix = _normalize_object_prefix(image_prefix)

        if images_dir:
            images_info = await process_images(
                zf,
                images_dir,
                image_bucket=image_bucket,
                image_prefix=normalized_prefix,
            )
            markdown_content = replace_image_links(markdown_content, images_info)

    content_hash = hashlib.sha256(markdown_content.encode("utf-8")).hexdigest()

    return {
        "markdown_content": markdown_content,
        "content_hash": content_hash,
        "images_info": images_info,
    }


def process_zip_file_sync(
    zip_path: str,
    image_bucket: str = DEFAULT_IMAGE_BUCKET,
    image_prefix: str = DEFAULT_IMAGE_PREFIX,
) -> dict:
    """同步调用 ZIP 处理，供同步解析器使用。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(process_zip_file(zip_path, image_bucket=image_bucket, image_prefix=image_prefix))

    result: dict | None = None
    error: Exception | None = None

    def runner() -> None:
        nonlocal result, error
        try:
            result = asyncio.run(process_zip_file(zip_path, image_bucket=image_bucket, image_prefix=image_prefix))
        except Exception as exc:  # pragma: no cover - pass through outer raise
            error = exc

    import threading

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if error is not None:
        raise error

    if result is None:
        raise RuntimeError("ZIP 处理失败: 未返回结果")

    return result


def find_images_directory(zip_file: zipfile.ZipFile, md_file_path: str) -> str | None:
    """查找images目录"""
    md_parent = Path(md_file_path).parent

    candidates = []
    if str(md_parent) != ".":
        candidates.extend([str(md_parent / "images"), str(md_parent.parent / "images")])
    candidates.append("images")

    for cand in candidates:
        cand_clean = cand.rstrip("/")
        if any(n.startswith(cand_clean + "/") for n in zip_file.namelist()):
            return cand_clean

    return None


async def process_images(
    zip_file: zipfile.ZipFile,
    images_dir: str,
    image_bucket: str,
    image_prefix: str,
) -> list[dict]:
    """处理图片：上传到MinIO并返回信息"""
    supported_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

    images = []
    image_names = [n for n in zip_file.namelist() if n.startswith(images_dir + "/")]
    normalized_prefix = _normalize_object_prefix(image_prefix)

    minio_client = get_minio_client()
    await asyncio.to_thread(minio_client.ensure_bucket_exists, image_bucket)

    for img_name in image_names:
        suffix = Path(img_name).suffix.lower()
        if suffix not in supported_extensions:
            continue

        try:
            with zip_file.open(img_name) as f:
                data = f.read()

            timestamp = int(time.time() * 1000000)
            object_name = f"{normalized_prefix}/{timestamp}_{Path(img_name).name}"

            result = await minio_client.aupload_file(
                bucket_name=image_bucket,
                object_name=object_name,
                data=data,
            )

            img_info = {
                "name": Path(img_name).name,
                "url": result.url,
                "path": f"images/{Path(img_name).name}",
            }
            images.append(img_info)

            logger.debug(f"图片上传成功: {Path(img_name).name} -> {result.url}")

        except Exception as e:
            logger.error(f"上传图片失败 {Path(img_name).name}: {e}")
            continue

    return images


def replace_image_links(markdown_content: str, images: list[dict]) -> str:
    """替换markdown中的图片链接为MinIO URL"""
    if not images:
        return markdown_content

    image_map = {}
    for img in images:
        path = img["path"]
        url = img["url"]
        image_map[path] = url
        image_map[f"/{path}"] = url
        image_map[img["name"]] = url

    def replace_link(match):
        alt_text = match.group(1) or ""
        img_path = match.group(2)

        for pattern, url in image_map.items():
            if img_path.endswith(pattern) or img_path == pattern:
                return f"![{alt_text}]({url})"

        filename = os.path.basename(img_path)
        if filename in image_map:
            return f"![{alt_text}]({image_map[filename]})"

        return match.group(0)

    pattern = r"!\[([^\]]*)\]\(([^)]+)\)"
    return re.sub(pattern, replace_link, markdown_content)
