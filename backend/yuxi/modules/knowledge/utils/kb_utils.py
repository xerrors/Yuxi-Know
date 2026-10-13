import hashlib
import time
from urllib.parse import quote

from yuxi.infrastructure.minio.object_urls import is_minio_url, parse_minio_url
from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.knowledge.chunking.presets import resolve_chunk_processing_params
from yuxi.shared.datetime import utc_isoformat
from yuxi.shared.hashing import hashstr

# Web 上传请求与持久 Job payload 的既有协议键；只在上传元数据边界读取。
PREPROCESSED_UPLOADS_KEY = "_preprocessed_map"

_DROPPED_PROCESSING_PARAM_KEYS = {
    PREPROCESSED_UPLOADS_KEY,
    "auto_index",
    "content_hashes",
    "file_sizes",
    "enable_ocr",
    "ocr_engine_config",
}


def sanitize_processing_params(params: dict | None) -> dict | None:
    """移除不应写入单文件元数据的参数。"""
    if not params:
        return None

    return {key: value for key, value in params.items() if key not in _DROPPED_PROCESSING_PARAM_KEYS}


def params_for_uploaded_document(item: str, params: dict) -> dict:
    """将批量上传参数收敛为单个文档的处理参数。"""
    source_paths = params.get("source_paths")
    item_params = dict(params)
    item_params.pop("source_paths", None)
    if isinstance(source_paths, dict) and source_paths.get(item):
        item_params["source_path"] = source_paths[item]
    return item_params


def resolve_processing_params(
    kb_additional_params: dict | None,
    file_processing_params: dict | None,
    request_params: dict | None = None,
) -> dict:
    """合并文件、请求中的 OCR 和分块参数。"""

    merged_params = sanitize_processing_params(merge_processing_params(file_processing_params, request_params)) or {}
    chunk_params = resolve_chunk_processing_params(
        kb_additional_params=kb_additional_params,
        file_processing_params=file_processing_params,
        request_params=request_params,
    )
    merged_params.update(chunk_params)
    return merged_params


async def calculate_content_hash(data: bytes | bytearray) -> str:
    """计算文件内容的 SHA-256 哈希值。"""
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()


async def prepare_item_metadata(item: str, content_type: str, kb_id: str, params: dict | None = None) -> dict:
    """
    准备 MinIO 文件元数据；URL 导入需先通过 fetch-url 预处理为 MinIO 文件。

    Args:
        item: MinIO URL
        content_type: 内容类型，目前仅支持 "file"
        kb_id: 知识库ID
        params: 处理参数，可选
    """
    # 检查是否有预处理信息 (针对 URL 转 HTML 文件的情况)
    if params and PREPROCESSED_UPLOADS_KEY in params and item in params[PREPROCESSED_UPLOADS_KEY]:
        pre_info = params[PREPROCESSED_UPLOADS_KEY][item]

        # 使用预处理信息
        filename = pre_info.get("filename", item)  # 通常是原始 URL

        # 截断文件名以适应数据库限制 (512 chars)，保留部分后缀信息如果可能
        if len(filename) > 500:
            filename_display = filename[:400] + "..." + filename[-90:]
        else:
            filename_display = filename

        file_type = "html"  # 强制转换为 html 类型，以便后续作为文件处理
        item_path = pre_info["path"]  # MinIO path
        content_hash = pre_info["content_hash"]

        # 使用 item(url) 生成 ID，保证同一 URL 即使多次添加 ID 也不同（配合 time）
        # 或者我们应该基于 hash？不，基于 time 更符合上传逻辑
        file_id = f"file_{hashstr(item + str(time.time()), 6)}"

        metadata = {
            "kb_id": kb_id,
            "filename": filename_display,
            "path": item_path,
            "file_type": file_type,
            "status": "indexing",
            "created_at": utc_isoformat(),
            "file_id": file_id,
            "content_hash": content_hash,
            "size": pre_info.get("file_size"),
            "parent_id": params.get("parent_id"),
        }

        if params:
            safe_params = sanitize_processing_params(params) or {}
            # 覆盖 content_type 为 file，确保后续解析走文件流程（MinIO 下载 -> HTML 解析）
            # 而不是再次尝试作为 URL 抓取
            safe_params["content_type"] = "file"
            safe_params["original_source"] = item  # 保存完整 URL 到 JSON 字段，避免数据库字段长度限制
            metadata["processing_params"] = safe_params

        return metadata

    if content_type == "file":
        if not is_minio_url(item):
            raise ValueError(f"File source must be a MinIO URL: {item}")

        logger.debug(f"Processing MinIO file: {item}")
        _, object_name = parse_minio_url(item)
        filename = object_name.rsplit("/", 1)[-1]

        import re

        timestamp_pattern = r"^(.+)_(\d{13})(\.[^.]+)$"
        match = re.match(timestamp_pattern, filename)
        filename_display = match.group(1) + match.group(3) if match else filename
        source_path = _normalize_source_path(params.get("source_path")) if params else None
        if source_path:
            filename_display = source_path

        file_type = filename_display.rsplit(".", 1)[-1].lower() if "." in filename_display else ""
        item_path = item

        content_hash = None
        if params and "content_hashes" in params and isinstance(params["content_hashes"], dict):
            content_hash = params["content_hashes"].get(item)

        if not content_hash:
            raise ValueError(f"Missing content_hash for file: {item}")

        file_sizes = params.get("file_sizes") if params else None
        if not isinstance(file_sizes, dict):
            file_sizes = {}
        file_size = file_sizes.get(item)
        file_id = f"file_{hashstr(str(item_path) + str(time.time()), 6)}"

    else:
        raise ValueError(f"Unsupported content_type: {content_type}")

    metadata = {
        "kb_id": kb_id,
        "filename": filename_display,  # 使用显示用的文件名
        "path": item_path,
        "file_type": file_type,
        "status": "indexing",
        "created_at": utc_isoformat(),
        "file_id": file_id,
        "content_hash": content_hash,
        "size": file_size,
        "parent_id": params.get("parent_id") if params else None,
    }

    # 保存处理参数到元数据
    if params:
        metadata["processing_params"] = sanitize_processing_params(params)

    return metadata


def _normalize_source_path(value: object) -> str | None:
    """归一化客户端传入的上传源路径，仅用于知识库文件树中的展示文件名。

    source_path 用来保留 CLI 目录上传时的相对层级。这里不会把它当作真实
    存储路径使用：反斜杠会转成斜杠，开头的 "./" 会被去掉，绝对路径和
    ".." 父目录跳转会被拒绝。
    """
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.startswith("/"):
        return None
    parts = [part for part in normalized.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        return None
    display_path = "/".join(parts)
    if len(display_path) > 512:
        raise ValueError("source_path is too long")
    return display_path


def merge_processing_params(metadata_params: dict | None, request_params: dict | None) -> dict:
    """
    合并处理参数：优先使用请求参数，缺失时使用元数据中的参数

    Args:
        metadata_params: 元数据中保存的参数
        request_params: 请求中提供的参数

    Returns:
        dict: 合并后的参数
    """
    merged_params = {}

    # 首先使用元数据中的参数作为默认值
    if metadata_params:
        merged_params.update(metadata_params)

    # 然后使用请求参数覆盖（如果提供）
    if request_params:
        merged_params.update(request_params)

    logger.debug(
        "Merged processing params: "
        f"metadata_keys={list(metadata_params.keys()) if metadata_params else []}, "
        f"request_keys={list(request_params.keys()) if request_params else []}, "
        f"merged_keys={list(merged_params.keys())}"
    )
    return merged_params


def build_kb_image_proxy_url(object_name: str) -> str:
    """构建知识库图片的后端鉴权代理 URL。

    图片存放在私有 bucket，前端通过该 URL 请求后端鉴权后读取图片。
    对象名格式为 ``{kb_id}/kb-images/{timestamp}_{filename}``，kb_id 即首段；
    路径参数只保留 ``kb-images/...`` 部分（保留斜杠、编码其余字符）。
    """
    kb_id, separator, relative_path = object_name.partition("/")
    if not kb_id or not separator or not relative_path.startswith("kb-images/"):
        raise ValueError("知识库图片对象名必须符合 {kb_id}/kb-images/{filename} 格式")
    return f"/api/knowledge/knowledge-bases/{kb_id}/images/{quote(relative_path, safe='/')}"
