import asyncio
import base64
import os
import re
import time
import zipfile
from pathlib import Path

import aiofiles
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter
from langchain_community.document_loaders import (
    CSVLoader,
    JSONLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredHTMLLoader,
    UnstructuredMarkdownLoader,
    UnstructuredWordDocumentLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.knowledge.utils import calculate_content_hash
from src.storage.minio import get_minio_client
from src.utils import hashstr, logger

SUPPORTED_FILE_EXTENSIONS: tuple[str, ...] = (
    ".txt",
    ".md",
    ".docx",
    ".html",
    ".htm",
    ".json",
    ".csv",
    ".xls",
    ".xlsx",
    ".pdf",
    ".pptx",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tiff",
    ".tif",
    ".zip",
)


def is_supported_file_extension(file_name: str | os.PathLike[str]) -> bool:
    """Check whether the given file path has a supported extension."""
    return Path(file_name).suffix.lower() in SUPPORTED_FILE_EXTENSIONS


# Docling 文档转换器（单例模式）
_docling_converter: DocumentConverter | None = None


def _get_docling_converter() -> DocumentConverter:
    """获取 Docling 文档转换器单例"""
    global _docling_converter
    if _docling_converter is None:
        _docling_converter = DocumentConverter(
            format_options={
                InputFormat.DOCX: None,
                InputFormat.XLSX: None,
                InputFormat.PPTX: None,
            }
        )
    return _docling_converter


def _upload_image_to_minio(image_data: bytes, filename: str, db_id: str) -> str:
    """上传图片到 MinIO，返回 URL"""
    minio_client = get_minio_client()
    minio_client.ensure_bucket_exists("kb-images")
    file_id = hashstr(filename, length=16)
    timestamp = int(time.time() * 1000000)
    suffix = Path(filename).suffix.lower()
    object_name = f"{db_id}/{file_id}/images/{timestamp}_{Path(filename).name}"
    content_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }
    content_type = content_type_map.get(suffix, "image/jpeg")

    result = minio_client.upload_file(
        bucket_name="kb-images",
        object_name=object_name,
        data=image_data,
        content_type=content_type,
    )
    return result.url


def _parse_data_uri(data_uri: str) -> tuple[bytes, str]:
    """解析 data URI，返回 (image_data, mime_type)"""
    header, base64_data = data_uri.split(",", 1)
    mime_type = header.split(":")[1].split(";")[0]
    image_data = base64.b64decode(base64_data)
    return image_data, mime_type


def _convert_with_docling(file_path: Path, params: dict | None = None) -> str:
    """
    使用 Docling 将 docx/xlsx/pptx 转换为 Markdown

    Args:
        file_path: 文件路径
        params: 参数，包含 db_id 用于图片上传

    Returns:
        Markdown 字符串
    """
    params = params or {}
    db_id = params.get("db_id") or "docling-docs"

    converter = _get_docling_converter()
    result = converter.convert(file_path)

    if result.status.name != "SUCCESS":
        raise RuntimeError(f"Docling 转换失败: {result.status}")

    doc = result.document

    # 提取图片并上传到 MinIO
    if hasattr(doc, "pictures") and doc.pictures:
        image_refs: list[tuple[str, bytes]] = []

        for pic in doc.pictures:
            if hasattr(pic, "image") and hasattr(pic.image, "uri"):
                uri = str(pic.image.uri)
                if uri.startswith("data:"):
                    image_data, mime_type = _parse_data_uri(uri)
                    timestamp = int(time.time() * 1000000)  # 微秒级时间戳
                    filename = f"image_{timestamp}.{mime_type.split('/')[-1]}"
                    image_refs.append((filename, image_data))

        # 上传图片并收集 URL
        image_urls: list[str] = []
        for filename, image_data in image_refs:
            try:
                url = _upload_image_to_minio(image_data, filename, db_id)
                image_urls.append(f"![{filename}]({url})")
            except Exception as e:
                logger.error(f"上传图片失败 {filename}: {e}")
                image_urls.append(f"[图片: {filename}]")

        # 导出 Markdown
        markdown = doc.export_to_markdown()

        # 替换 <!-- image --> 占位符为图片 URL
        # Docling 使用 <!-- image --> 作为占位符
        for url in reversed(image_urls):
            markdown = re.sub(r"<!--\s*image\s*-->", url, markdown, count=1)

        return markdown

    # 无图片时直接导出
    return doc.export_to_markdown()


def chunk_with_parser(file_path, params=None):
    """
    使用文件解析器将文件切分成固定大小的块

    Args:
        file_path: 文件路径
        params: 参数
    """
    params = params or {}
    chunk_size = int(params.get("chunk_size", 500))
    chunk_overlap = int(params.get("chunk_overlap", 100))

    file_type = Path(file_path).suffix.lower()

    # 选择合适的加载器
    if file_type in [".txt"]:
        loader = TextLoader(file_path)

    elif file_type in [".md"]:
        loader = UnstructuredMarkdownLoader(file_path)

    elif file_type in [".docx", ".doc"]:
        loader = UnstructuredWordDocumentLoader(file_path)

    elif file_type in [".html", ".htm"]:
        loader = UnstructuredHTMLLoader(file_path)

    elif file_type in [".json"]:
        loader = JSONLoader(file_path, jq_schema=".")

    elif file_type in [".csv"]:
        loader = CSVLoader(file_path)

    else:
        raise ValueError(f"不支持的文件类型: {file_type}")

    # 加载文档
    docs = loader.load()

    # 创建文本分割器
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    # 分割文档
    nodes = text_splitter.split_documents(docs)

    # 添加序号信息到metadata
    for i, node in enumerate(nodes):
        if node.metadata is None:
            node.metadata = {}
        node.metadata["chunk_idx"] = i

    return nodes


def chunk_text(text, params=None):
    """
    将文本切分成固定大小的块
    """
    params = params or {}
    chunk_size = int(params.get("chunk_size", 500))
    chunk_overlap = int(params.get("chunk_overlap", 100))

    # 创建文本分割器
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=["\n\n", "\n", ".", " ", ""]
    )

    # 分割文档
    nodes = text_splitter.split_text(text)

    # 添加序号信息到metadata
    nodes = [{"text": node, "metadata": {"chunk_idx": i}} for i, node in enumerate(nodes)]
    return nodes


def chunk(text_or_path, params=None):
    raise NotImplementedError("chunk is deprecated, use chunk_with_parser or chunk_text instead")


def pdfreader(file_path, params=None):
    """读取PDF文件并返回text文本"""
    if isinstance(file_path, str):
        file_path = Path(file_path)

    assert file_path.exists(), "File not found"
    assert file_path.suffix.lower() == ".pdf", "File format not supported"

    # 使用LangChain的PDF加载器
    loader = PyPDFLoader(str(file_path))
    docs = loader.load()

    # 简单的拼接起来之后返回纯文本
    text = "\n\n".join([d.page_content for d in docs])
    return text


def plainreader(file_path):
    """读取普通文本文件并返回text文本"""
    assert os.path.exists(file_path), "File not found"

    # 使用LangChain的文本加载器
    loader = TextLoader(str(file_path))
    docs = loader.load()
    text = "\n\n".join([d.page_content for d in docs])
    return text


def parse_pdf(file, params=None):
    """
    解析PDF文件，支持多种OCR方式

    Args:
        file: PDF文件路径
        params: 参数字典，包含enable_ocr设置

    Returns:
        str: 解析得到的文本

    Raises:
        DocumentProcessorException: 处理失败时抛出
    """
    from src.plugins.document_processor_base import DocumentProcessorException
    from src.plugins.document_processor_factory import DocumentProcessorFactory

    params = params or {}
    opt_ocr = params.get("enable_ocr", "disable")

    if opt_ocr == "disable":
        return pdfreader(file, params=params)

    try:
        return DocumentProcessorFactory.process_file(opt_ocr, file, params)

    except DocumentProcessorException as e:
        logger.error(f"文档处理失败: {e.service_name} - {str(e)}")
        raise
    except Exception as e:
        logger.error(f"PDF 解析失败: {str(e)}")
        raise DocumentProcessorException(f"PDF解析失败: {str(e)}", opt_ocr, "parsing_failed")


def parse_image(file, params=None):
    """
    解析图像文件，支持多种OCR方式

    Args:
        file: 图像文件路径
        params: 参数字典，包含enable_ocr设置

    Returns:
        str: 解析得到的文本

    Raises:
        DocumentProcessorException: 处理失败时抛出
        ValueError: 图像文件禁用OCR时抛出
    """
    from src.plugins.document_processor_base import DocumentProcessorException
    from src.plugins.document_processor_factory import DocumentProcessorFactory

    params = params or {}
    opt_ocr = params.get("enable_ocr", "disable")

    # 图像文件必须使用 OCR,不能禁用
    if opt_ocr == "disable":
        raise ValueError(
            "图像文件必须启用OCR才能提取文本内容。"
            "请选择OCR方式 (onnx_rapid_ocr/mineru_ocr/mineru_official/paddlex_ocr) 或移除该文件。"
        )

    try:
        return DocumentProcessorFactory.process_file(opt_ocr, file, params)

    except DocumentProcessorException as e:
        logger.error(f"图像处理失败: {e.service_name} - {str(e)}")
        raise
    except Exception as e:
        logger.error(f"图像解析失败: {str(e)}")
        raise DocumentProcessorException(f"图像解析失败: {str(e)}", opt_ocr, "parsing_failed")


async def parse_pdf_async(file, params=None):
    return await asyncio.to_thread(parse_pdf, file, params=params)


async def parse_image_async(file, params=None):
    return await asyncio.to_thread(parse_image, file, params=params)


async def process_file_to_markdown(file_path: str, params: dict | None = None) -> str:
    """
    将不同类型的文件转换为markdown格式 - 支持本地文件和MinIO文件

    Args:
        file_path: 文件路径或MinIO URL
        params: 处理参数，对于ZIP文件需要包含 db_id

    Returns:
        markdown格式内容

    Note:
        对于ZIP文件，会在params中保存处理结果供调用方使用：
        - params['_zip_images_info']: 图片信息列表
        - params['_zip_content_hash']: 内容哈希值
    """
    import os
    import tempfile

    # 检测是否是MinIO URL
    from src.knowledge.utils.kb_utils import is_minio_url

    if is_minio_url(file_path):
        # 从MinIO下载文件到临时位置
        logger.debug(f"Downloading file from MinIO: {file_path}")

        # 从MinIO URL中提取文件名
        if "?" in file_path:
            file_path_clean = file_path.split("?")[0]
        else:
            file_path_clean = file_path

        original_filename = file_path_clean.split("/")[-1]

        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(original_filename).suffix) as temp_file:
            temp_path = temp_file.name

        try:
            # 使用通用函数解析MinIO URL并下载文件
            from src.knowledge.utils.kb_utils import parse_minio_url
            from src.storage.minio.client import get_minio_client

            # 解析MinIO URL获取bucket_name和object_name
            bucket_name, object_name = parse_minio_url(file_path)

            # 获取MinIO客户端并下载文件
            minio_client = get_minio_client()
            file_content = await minio_client.adownload_file(bucket_name, object_name)

            # 写入临时文件
            async with aiofiles.open(temp_path, "wb") as f:
                await f.write(file_content)

            logger.debug(f"File downloaded to temp path: {temp_path}")

            # 使用临时文件路径
            actual_file_path = temp_path

        except Exception as e:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            logger.error(f"Failed to download file from MinIO: {e}")
            raise ValueError(f"无法从MinIO下载文件: {e}")
    else:
        # 本地文件
        actual_file_path = file_path

    try:
        file_path_obj = Path(actual_file_path)
        file_ext = file_path_obj.suffix.lower()
        original_filename = file_path_obj.name

        if file_ext == ".pdf":
            # 使用 OCR 处理 PDF
            text = await parse_pdf_async(str(file_path_obj), params=params)
            result = f"{text}"

        elif file_ext in [".txt", ".md"]:
            # 直接读取文本文件
            with open(file_path_obj, encoding="utf-8") as f:
                content = f.read()
            result = f"{content}"

        elif file_ext in [".docx", ".pptx"]:
            # 使用 Docling 处理 docx 和 pptx
            result = _convert_with_docling(file_path_obj, params=params)

        elif file_ext == ".doc":
            # 旧版 .doc 文件仍使用原有解析方式
            from langchain_community.document_loaders import UnstructuredWordDocumentLoader

            loader = UnstructuredWordDocumentLoader(str(file_path_obj))
            docs = loader.load()
            result = "\n".join(doc.page_content for doc in docs).strip()

        elif file_ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"]:
            # 使用 OCR 处理图片
            text = await parse_image_async(str(file_path_obj), params=params)
            result = f"{text}"

        elif file_ext in [".html", ".htm"]:
            # 使用 BeautifulSoup 处理 HTML 文件
            from markdownify import markdownify as md

            with open(file_path_obj, encoding="utf-8") as f:
                content = f.read()
            text = md(content, heading_style="ATX")
            result = f"{text}"

        elif file_ext == ".csv":
            # 处理 CSV 文件
            import pandas as pd

            df = pd.read_csv(file_path_obj)
            # 将每一行数据与表头组合成独立的表格
            markdown_content = ""

            for index, row in df.iterrows():
                # 创建包含表头和当前行的小表格
                row_df = pd.DataFrame([row], columns=df.columns)
                markdown_table = row_df.to_markdown(index=False)
                markdown_content += f"{markdown_table}\n\n"

            result = markdown_content.strip()

        elif file_ext in [".xls", ".xlsx"]:
            # 使用 Docling 处理 Excel 文件
            result = _convert_with_docling(file_path_obj, params=params)

        elif file_ext == ".json":
            # 处理 JSON 文件
            import json

            async with aiofiles.open(file_path_obj, encoding="utf-8") as f:
                content = await f.read()
            data = json.loads(content)
            # 将 JSON 数据格式化为 markdown 代码块
            json_str = json.dumps(data, ensure_ascii=False, indent=2)
            result = f"```json\n{json_str}\n```"

        elif file_ext == ".zip":
            if not params or "db_id" not in params:
                raise ValueError("ZIP文件处理需要在params中提供db_id参数")

            zip_result = await _process_zip_file(str(file_path_obj), params["db_id"])

            # 将处理结果保存到params中供调用方使用
            params["_zip_images_info"] = zip_result["images_info"]
            params["_zip_content_hash"] = zip_result["content_hash"]

            result = zip_result["markdown_content"]

        else:
            # 尝试作为文本文件读取
            raise ValueError(f"Unsupported file type: {file_ext}")

    except Exception:
        # 清理临时文件
        if is_minio_url(file_path) and os.path.exists(actual_file_path):
            try:
                os.unlink(actual_file_path)
                logger.debug(f"Cleaned up temp file: {actual_file_path}")
            except Exception as cleanup_e:
                logger.warning(f"Failed to clean up temp file {actual_file_path}: {cleanup_e}")
        raise

    finally:
        # 清理临时文件
        if is_minio_url(file_path) and os.path.exists(actual_file_path):
            try:
                os.unlink(actual_file_path)
                logger.debug(f"Cleaned up temp file: {actual_file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {actual_file_path}: {e}")

    return result


async def _process_zip_file(zip_path: str, db_id: str) -> dict:
    """
    处理ZIP文件，提取markdown内容和图片（内部函数）

    Args:
        zip_path: ZIP文件路径
        db_id: 数据库ID

    Returns:
        dict: {
            "markdown_content": str,      # markdown内容
            "content_hash": str,         # 内容哈希值
            "images_info": list[dict]    # 图片信息列表
        }

    Raises:
        FileNotFoundError: ZIP文件不存在
        ValueError: ZIP文件格式错误或内容不符合要求
    """
    # 1. 安全检查
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"ZIP 文件不存在: {zip_path}")

    # 2. 解压ZIP并提取内容
    with zipfile.ZipFile(zip_path, "r") as zf:
        # 安全检查：防止路径遍历攻击
        for name in zf.namelist():
            if name.startswith("/") or name.startswith("\\"):
                raise ValueError(f"ZIP 包含不安全路径: {name}")
            if ".." in Path(name).parts:
                raise ValueError(f"ZIP 路径包含上级引用: {name}")

        # 查找markdown文件
        md_files = [n for n in zf.namelist() if n.lower().endswith(".md")]
        if not md_files:
            raise ValueError("压缩包中未找到 .md 文件")

        # 优先使用 full.md，否则使用第一个md文件
        md_file = next((n for n in md_files if Path(n).name == "full.md"), md_files[0])

        # 读取markdown内容
        with zf.open(md_file) as f:
            markdown_content = f.read().decode("utf-8")

        # 3. 处理图片
        images_info = []
        images_dir = _find_images_directory(zf, md_file)

        if images_dir:
            images_info = await _process_images(zf, images_dir, db_id, md_file)
            markdown_content = _replace_image_links(markdown_content, images_info)

    # 4. 生成结果
    content_hash = await calculate_content_hash(markdown_content.encode("utf-8"))

    return {
        "markdown_content": markdown_content,
        "content_hash": content_hash,
        "images_info": images_info,
    }


def _find_images_directory(zip_file: zipfile.ZipFile, md_file_path: str) -> str | None:
    """查找images目录"""
    md_parent = Path(md_file_path).parent

    # 候选目录
    candidates = []
    if str(md_parent) != ".":
        candidates.extend([str(md_parent / "images"), str(md_parent.parent / "images")])
    candidates.append("images")

    # 查找存在的目录
    for cand in candidates:
        cand_clean = cand.rstrip("/")
        if any(n.startswith(cand_clean + "/") for n in zip_file.namelist()):
            return cand_clean

    return None


async def _process_images(zip_file: zipfile.ZipFile, images_dir: str, db_id: str, md_file_path: str) -> list[dict]:
    """处理图片：上传到MinIO并返回信息"""
    # 支持的图片格式
    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    CONTENT_TYPE_MAP = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }

    images = []
    image_names = [n for n in zip_file.namelist() if n.startswith(images_dir + "/")]

    # 上传图片到MinIO
    minio_client = get_minio_client()
    bucket_name = "kb-images"
    await asyncio.to_thread(minio_client.ensure_bucket_exists, bucket_name)

    file_id = hashstr(Path(md_file_path).name, length=16)

    for img_name in image_names:
        suffix = Path(img_name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            continue

        try:
            # 读取图片数据
            with zip_file.open(img_name) as f:
                data = f.read()

            # 上传到MinIO
            timestamp = int(time.time() * 1000000)
            object_name = f"{db_id}/{file_id}/images/{timestamp}_{Path(img_name).name}"
            content_type = CONTENT_TYPE_MAP.get(suffix, "image/jpeg")

            result = await minio_client.aupload_file(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data,
                content_type=content_type,
            )

            # 记录图片信息
            img_info = {"name": Path(img_name).name, "url": result.url, "path": f"images/{Path(img_name).name}"}
            images.append(img_info)

            logger.debug(f"图片上传成功: {Path(img_name).name} -> {result.url}")

        except Exception as e:
            logger.error(f"上传图片失败 {Path(img_name).name}: {e}")
            continue

    return images


def _replace_image_links(markdown_content: str, images: list[dict]) -> str:
    """替换markdown中的图片链接为MinIO URL"""
    if not images:
        return markdown_content

    # 构建路径映射
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

        # 尝试匹配各种路径格式
        for pattern, url in image_map.items():
            if img_path.endswith(pattern) or img_path == pattern:
                return f"![{alt_text}]({url})"

        # 尝试文件名匹配
        filename = os.path.basename(img_path)
        if filename in image_map:
            return f"![{alt_text}]({image_map[filename]})"

        return match.group(0)

    # 使用正则表达式替换图片链接
    pattern = r"!\[([^\]]*)\]\(([^)]+)\)"
    return re.sub(pattern, replace_link, markdown_content)


async def process_url_to_markdown(url: str, params: dict | None = None) -> str:
    raise NotImplementedError("URL 解析功能已禁用")
