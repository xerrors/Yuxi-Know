import hashlib
import os
import time
import traceback
from pathlib import Path

import aiofiles
from langchain_text_splitters import MarkdownTextSplitter

from src import config
from src.config.static.models import EmbedModelInfo
from src.utils import hashstr, logger
from src.utils.datetime_utils import utc_isoformat


def validate_file_path(file_path: str, db_id: str = None) -> str:
    """
    验证文件路径安全性，防止路径遍历攻击 - 支持本地文件和MinIO URL

    Args:
        file_path: 要验证的文件路径或MinIO URL
        db_id: 数据库ID，用于获取知识库特定的上传目录

    Returns:
        str: 规范化后的安全路径

    Raises:
        ValueError: 如果路径不安全
    """
    try:
        # 检测是否是MinIO URL，如果是则直接返回（不进行路径遍历检查）
        if is_minio_url(file_path):
            logger.debug(f"MinIO URL detected, skipping path validation: {file_path}")
            return file_path

        # 规范化路径（仅对本地文件）
        normalized_path = os.path.abspath(os.path.realpath(file_path))

        # 获取允许的根目录
        from src.knowledge import knowledge_base

        allowed_dirs = [
            os.path.abspath(os.path.realpath(config.save_dir)),
        ]

        # 如果指定了db_id，添加知识库特定的上传目录
        if db_id:
            try:
                allowed_dirs.append(os.path.abspath(os.path.realpath(knowledge_base.get_db_upload_path(db_id))))
            except Exception:
                # 如果无法获取db路径，使用通用上传目录
                allowed_dirs.append(
                    os.path.abspath(os.path.realpath(os.path.join(config.save_dir, "database", "uploads")))
                )

        # 检查路径是否在允许的目录内
        is_safe = False
        for allowed_dir in allowed_dirs:
            try:
                if normalized_path.startswith(allowed_dir):
                    is_safe = True
                    break
            except Exception:
                continue

        if not is_safe:
            logger.warning(f"Path traversal attempt detected: {file_path} (normalized: {normalized_path})")
            raise ValueError(f"Access denied: Invalid file path: {file_path}")

        return normalized_path

    except Exception as e:
        logger.error(f"Path validation failed for {file_path}: {e}")
        raise ValueError(f"Invalid file path: {file_path}")


def _unescape_separator(separator: str | None) -> str | None:
    """将前端传入的字面量转义字符转换为实际字符

    例如: "\\n\\n\\n" -> "\n\n\n"
    """
    if not separator:
        return None

    # 处理常见的转义序列
    separator = separator.replace("\\n", "\n")
    separator = separator.replace("\\r", "\r")
    separator = separator.replace("\\t", "\t")
    separator = separator.replace("\\\\", "\\")

    return separator


def split_text_into_chunks(text: str, file_id: str, filename: str, params: dict = {}) -> list[dict]:
    """
    将文本分割成块，使用 LangChain 的 MarkdownTextSplitter 进行智能分割
    """
    chunks = []
    chunk_size = params.get("chunk_size", 1000)
    chunk_overlap = params.get("chunk_overlap", 200)

    # 获取分隔符并转换为实际字符
    separator = params.get("qa_separator")
    separator = _unescape_separator(separator)

    # 向后兼容：如果旧配置设置了 use_qa_split=True 但未指定 separator，使用默认分隔符
    use_qa_split = params.get("use_qa_split", False)
    if use_qa_split and not separator:
        separator = "\n\n\n"
        logger.debug("启用了向后兼容模式：use_qa_split=True，使用默认分隔符 \\n\\n\\n")

    # 使用 MarkdownTextSplitter 进行智能分割
    # MarkdownTextSplitter 会尝试沿着 Markdown 格式的标题进行分割
    text_splitter = MarkdownTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    # 如果设置了分隔符，先分割后以当前的分割逻辑处理
    if separator:
        # 转换分隔符为可视格式（换行符显示为 \n）
        separator_display = separator.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        logger.debug(f"启用预分割模式，使用分隔符: '{separator_display}'")
        pre_chunks = text.split(separator)
        text_chunks = []
        for pre_chunk in pre_chunks:
            if pre_chunk.strip():
                text_chunks.extend(text_splitter.split_text(pre_chunk))
    else:
        text_chunks = text_splitter.split_text(text)

    # 转换为标准格式
    for chunk_index, chunk_content in enumerate(text_chunks):
        if chunk_content.strip():  # 跳过空块
            chunks.append(
                {
                    "id": f"{file_id}_chunk_{chunk_index}",
                    "content": chunk_content,  # .strip(),
                    "file_id": file_id,
                    "filename": filename,
                    "chunk_index": chunk_index,
                    "source": filename,
                    "chunk_id": f"{file_id}_chunk_{chunk_index}",
                }
            )

    logger.debug(f"Successfully split text into {len(chunks)} chunks using MarkdownTextSplitter")
    return chunks


async def calculate_content_hash(data: bytes | bytearray | str | os.PathLike[str] | Path) -> str:
    """
    计算文件内容的 SHA-256 哈希值。

    Args:
        data: 文件内容的二进制数据或文件路径

    Returns:
        str: 十六进制哈希值
    """
    sha256 = hashlib.sha256()

    if isinstance(data, (bytes, bytearray)):
        sha256.update(data)
        return sha256.hexdigest()

    if isinstance(data, (str, os.PathLike, Path)):
        path = Path(data)
        async with aiofiles.open(path, "rb") as file_handle:
            chunk = await file_handle.read(8192)
            while chunk:
                sha256.update(chunk)
                chunk = await file_handle.read(8192)

        return sha256.hexdigest()

    # 理论上不会执行到这里，但保留作为防御性编程
    raise TypeError(f"Unsupported data type for hashing: {type(data)!r}")  # type: ignore[unreachable]


async def prepare_item_metadata(item: str, content_type: str, db_id: str, params: dict | None = None) -> dict:
    """
    准备文件或URL的元数据 - 支持本地文件和MinIO文件

    Args:
        item: 文件路径或MinIO URL
        content_type: 内容类型 ("file" 或 "url")
        db_id: 数据库ID
        params: 处理参数，可选
    """
    if content_type == "file":
        # 检测是否是MinIO URL还是本地文件路径
        if is_minio_url(item):
            # MinIO文件处理
            logger.debug(f"Processing MinIO file: {item}")
            # 从MinIO URL中提取文件名
            if "?" in item:
                # URL可能包含查询参数，去掉它们
                item_clean = item.split("?")[0]
            else:
                item_clean = item

            # 获取文件名（从路径的最后部分）
            filename = item_clean.split("/")[-1]

            # 如果文件名包含时间戳，提取原始文件名
            import re

            timestamp_pattern = r"^(.+)_(\d{13})(\.[^.]+)$"
            match = re.match(timestamp_pattern, filename)
            if match:
                original_filename = match.group(1) + match.group(3)
                # 存储原始文件名用于显示
                filename_display = original_filename
            else:
                filename_display = filename

            file_type = filename.split(".")[-1].lower() if "." in filename else ""
            item_path = item  # 保持MinIO URL作为路径

            # 从 content_hashes 映射中获取 content_hash
            content_hash = None
            if params and "content_hashes" in params and isinstance(params["content_hashes"], dict):
                content_hash = params["content_hashes"].get(item)

            if not content_hash:
                raise ValueError(f"Missing content_hash for file: {item}")

        else:
            # 本地文件处理
            file_path = Path(item)
            file_type = file_path.suffix.lower().replace(".", "")
            filename = file_path.name
            filename_display = filename
            item_path = os.path.relpath(file_path, Path.cwd())
            content_hash = None
            try:
                if file_path.exists():
                    content_hash = await calculate_content_hash(file_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to calculate content hash for {file_path}: {exc}")

        # 生成文件ID
        file_id = f"file_{hashstr(str(item_path) + str(time.time()), 6)}"

    else:
        raise ValueError("URL 元数据生成已禁用")

    metadata = {
        "database_id": db_id,
        "filename": filename_display,  # 使用显示用的文件名
        "path": item_path,
        "file_type": file_type,
        "status": "processing",
        "created_at": utc_isoformat(),
        "file_id": file_id,
        "content_hash": content_hash,
        "parent_id": params.get("parent_id") if params else None,
    }

    # 保存处理参数到元数据
    if params:
        metadata["processing_params"] = params.copy()

    return metadata


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

    logger.debug(f"Merged processing params: {metadata_params=}, {request_params=}, {merged_params=}")
    return merged_params


def get_embedding_config(embed_info: dict) -> dict:
    """
    获取嵌入模型配置

    Args:
        embed_info: 嵌入信息字典

    Returns:
        dict: 标准化的嵌入配置
    """
    try:
        # 使用最新配置
        assert isinstance(embed_info, dict), f"embed_info must be a dict, got {type(embed_info)}"
        assert "model_id" in embed_info, f"embed_info must contain 'model_id', got {embed_info}"
        logger.warning(f"Using model_id: {embed_info['model_id']}")
        config_dict = config.embed_model_names[embed_info["model_id"]].model_dump()
        config_dict["api_key"] = os.getenv(config_dict["api_key"]) or config_dict["api_key"]
        return config_dict

    except AssertionError as e:
        logger.error(f"AssertionError in get_embedding_config: {e}, embed_info={embed_info}")

    # 兼容性检查：旧版配置字段
    try:
        # 1. 检查 embed_info 是否有效
        if not embed_info or ("model" not in embed_info and "name" not in embed_info):
            logger.error(f"Invalid embed_info: {embed_info}, using default embedding model config")
            raise ValueError("Invalid embed_info: must be a non-empty dictionary")

        # 2. 检查是否是 EmbedModelInfo 对象（在某些情况下可能直接传入对象）
        if hasattr(embed_info, "name") and isinstance(embed_info, EmbedModelInfo):
            logger.debug(f"Using EmbedModelInfo object: {embed_info.name}, {traceback.format_exc()}")
            config_dict = embed_info.model_dump()
            config_dict["api_key"] = os.getenv(config_dict["api_key"]) or config_dict["api_key"]
            return config_dict

        raise ValueError(f"Unsupported embed_info format: {embed_info}")

    except Exception as e:
        logger.error(f"Error in get_embedding_config: {e}, embed_info={embed_info}")
        # 返回默认配置作为fallback
        logger.warning("Falling back to default embedding model config")
        try:
            config_dict = config.embed_model_names[config.embed_model].model_dump()
            config_dict["api_key"] = os.getenv(config_dict["api_key"]) or config_dict["api_key"]
            return config_dict
        except Exception as fallback_error:
            logger.error(f"Failed to get default embedding config: {fallback_error}")
            raise ValueError(f"Failed to get embedding config and fallback failed: {e}")


def is_minio_url(file_path: str) -> bool:
    """
    检测是否是MinIO URL

    Args:
        file_path: 文件路径或URL

    Returns:
        bool: 是否是MinIO URL
    """
    return file_path.startswith(("http://", "https://", "s3://")) or "minio" in file_path.lower()


def parse_minio_url(file_path: str) -> tuple[str, str]:
    """
    解析MinIO URL，提取bucket名称和对象名称

    支持标准 HTTP/HTTPS URL 格式：
    - http(s)://host/bucket-name/path/to/object

    Args:
        file_path: MinIO文件URL (http:// 或 https://)

    Returns:
        tuple[str, str]: (bucket_name, object_name)

    Raises:
        ValueError: 如果无法解析URL
    """
    try:
        from urllib.parse import urlparse

        # 解析URL
        parsed_url = urlparse(file_path)

        # 对于 minio:// 协议，bucket名称在netloc中
        if parsed_url.scheme == "minio":
            bucket_name = parsed_url.netloc
            object_name = parsed_url.path.lstrip("/")
        else:
            # 对于 http/https 协议，bucket名称在path的第一部分
            object_name = parsed_url.path.lstrip("/")
            path_parts = object_name.split("/", 1)
            if len(path_parts) > 1:
                bucket_name = path_parts[0]
                object_name = path_parts[1]
            else:
                raise ValueError(f"无法解析MinIO URL中的bucket名称: {file_path}")

        logger.debug(f"Parsed MinIO URL: bucket_name={bucket_name}, object_name={object_name}")
        return bucket_name, object_name

    except Exception as e:
        logger.error(f"Failed to parse MinIO URL {file_path}: {e}")
        raise ValueError(f"无法解析MinIO URL: {file_path}")
