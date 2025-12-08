import hashlib
import os
import time
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


def split_text_into_chunks(text: str, file_id: str, filename: str, params: dict = {}) -> list[dict]:
    """
    将文本分割成块，使用 LangChain 的 MarkdownTextSplitter 进行智能分割
    """
    chunks = []
    chunk_size = params.get("chunk_size", 1000)
    chunk_overlap = params.get("chunk_overlap", 200)

    # 使用 MarkdownTextSplitter 进行智能分割
    # MarkdownTextSplitter 会尝试沿着 Markdown 格式的标题进行分割
    text_splitter = MarkdownTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

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

    raise TypeError(f"Unsupported data type for hashing: {type(data)!r}")


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
            timestamp_pattern = r'^(.+)_(\d{13})(\.[^.]+)$'
            match = re.match(timestamp_pattern, filename)
            if match:
                original_filename = match.group(1) + match.group(3)
                # 存储原始文件名用于显示
                filename_display = original_filename
            else:
                filename_display = filename

            file_type = filename.split(".")[-1].lower() if "." in filename else ""
            item_path = item  # 保持MinIO URL作为路径

            # 从URL或params中获取content_hash（如果有的话）
            content_hash = None
            if params and "content_hash" in params:
                content_hash = params["content_hash"]

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
    }

    # 保存处理参数到元数据
    if params:
        metadata["processing_params"] = params.copy()

    return metadata


def split_text_into_qa_chunks(
    text: str, file_id: str, filename: str, qa_separator: None | str = None, params: dict = {}
) -> list[dict]:
    """
    将文本按QA对分割成块，使用 LangChain 的 CharacterTextSplitter 进行分割"""
    qa_separator = qa_separator or "\n\n"
    text_chunks = text.split(qa_separator)

    # 转换为标准格式
    chunks = []
    for chunk_index, chunk_content in enumerate(text_chunks):
        if chunk_content.strip():  # 跳过空块
            chunk_content = chunk_content.strip()[:4096]
            chunks.append(
                {
                    "id": f"{file_id}_qa_chunk_{chunk_index}",
                    "content": chunk_content.strip(),
                    "file_id": file_id,
                    "filename": filename,
                    "chunk_index": chunk_index,
                    "source": filename,
                    "chunk_id": f"{file_id}_qa_chunk_{chunk_index}",
                    "chunk_type": "qa",  # 标识为QA类型的chunk
                }
            )

    logger.debug(f"QA chunks: {chunks[0]}")
    logger.debug(
        f"Successfully split QA text into {len(chunks)} chunks using CharacterTextSplitter with `{qa_separator=}`"
    )
    return chunks


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
    config_dict = {}

    try:
        if embed_info:
            # 优先检查是否有 model_id 字段
            if "model_id" in embed_info:
                return config.embed_model_names[embed_info["model_id"]].model_dump()
            elif hasattr(embed_info, "name") and isinstance(embed_info, EmbedModelInfo):
                return embed_info.model_dump()
            else:
                # 字典形式（保持向后兼容）
                config_dict["model"] = embed_info["name"]
                config_dict["api_key"] = os.getenv(embed_info["api_key"]) or embed_info["api_key"]
                config_dict["base_url"] = embed_info["base_url"]
                config_dict["dimension"] = embed_info.get("dimension", 1024)
        else:
            return config.embed_model_names[config.embed_model].model_dump()

    except Exception as e:
        logger.error(f"Error in get_embedding_config: {e}, {embed_info}")
        raise ValueError(f"Error in get_embedding_config: {e}")

    logger.debug(f"Embedding config: {config_dict}")
    return config_dict


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

    Args:
        file_path: MinIO文件URL

    Returns:
        tuple[str, str]: (bucket_name, object_name)

    Raises:
        ValueError: 如果无法解析URL
    """
    try:
        from urllib.parse import urlparse

        # 解析URL
        parsed_url = urlparse(file_path)

        # 从URL路径中提取对象名称（去掉开头的斜杠）
        object_name = parsed_url.path.lstrip('/')

        # 分离bucket名称和对象名称
        path_parts = object_name.split('/', 1)
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
