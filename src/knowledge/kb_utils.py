import os
import time
from pathlib import Path
from typing import Any
from langchain_text_splitters import MarkdownTextSplitter
from src.utils import hashstr, get_docker_safe_url, logger
from src import config


def split_text_into_chunks(text: str, file_id: str, filename: str, params: dict = {}) -> list[dict]:
    """
    将文本分割成块，使用 LangChain 的 MarkdownTextSplitter 进行智能分割
    """
    chunks = []
    chunk_size = params.get('chunk_size', 1000)
    chunk_overlap = params.get('chunk_overlap', 200)

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
            chunks.append({
                "id": f"{file_id}_chunk_{chunk_index}",
                "content": chunk_content.strip(),
                "file_id": file_id,
                "filename": filename,
                "chunk_index": chunk_index,
                "source": filename,
                "chunk_id": f"{file_id}_chunk_{chunk_index}"
            })

    logger.debug(f"Successfully split text into {len(chunks)} chunks using MarkdownTextSplitter")
    return chunks


def prepare_item_metadata(item: str, content_type: str, db_id: str) -> dict:
    """
    准备文件或URL的元数据
    """
    if content_type == "file":
        file_path = Path(item)
        file_id = f"file_{hashstr(str(file_path) + str(time.time()), 6)}"
        file_type = file_path.suffix.lower().replace(".", "")
        filename = file_path.name
        item_path = os.path.relpath(file_path, Path.cwd())
    else:  # URL
        file_id = f"url_{hashstr(item + str(time.time()), 6)}"
        file_type = "url"
        filename = f"webpage_{hashstr(item, 6)}.md"
        item_path = item

    return {
        "database_id": db_id,
        "filename": filename,
        "path": item_path,
        "file_type": file_type,
        "status": "processing",
        "created_at": time.time(),
        "file_id": file_id
    }


def split_text_into_qa_chunks(text: str, file_id: str, filename: str,
                             qa_separator: None | str = None, params: dict = {}) -> list[dict]:
    """
    将文本按QA对分割成块，使用 LangChain 的 CharacterTextSplitter 进行分割"""
    qa_separator = qa_separator or '\n\n'
    text_chunks = text.split(qa_separator)

    # 转换为标准格式
    chunks = []
    for chunk_index, chunk_content in enumerate(text_chunks):
        if chunk_content.strip():  # 跳过空块
            chunk_content = chunk_content.strip()[:4096]
            chunks.append({
                "id": f"{file_id}_qa_chunk_{chunk_index}",
                "content": chunk_content.strip(),
                "file_id": file_id,
                "filename": filename,
                "chunk_index": chunk_index,
                "source": filename,
                "chunk_id": f"{file_id}_qa_chunk_{chunk_index}",
                "chunk_type": "qa"  # 标识为QA类型的chunk
            })

    logger.debug(f"QA chunks: {chunks[0]}")
    logger.debug(f"Successfully split QA text into {len(chunks)} chunks using CharacterTextSplitter with `{qa_separator=}`")
    return chunks


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
            config_dict['model'] = embed_info["name"]
            config_dict['api_key'] = os.getenv(embed_info["api_key"], embed_info["api_key"])
            config_dict['base_url'] = embed_info["base_url"]
            config_dict['dimension'] = embed_info.get("dimension", 1024)
        else:
            from src.models import select_embedding_model
            default_model = select_embedding_model(config.embed_model)
            config_dict['model'] = default_model.model
            config_dict['api_key'] = default_model.api_key
            config_dict['base_url'] = default_model.base_url
            config_dict['dimension'] = getattr(default_model, 'dimension', 1024)

    except Exception as e:
        logger.error(f"Error in get_embedding_config: {e}, {embed_info}")
        raise ValueError(f"Error in get_embedding_config: {e}")

    logger.debug(f"Embedding config: {config_dict}")
    return config_dict
