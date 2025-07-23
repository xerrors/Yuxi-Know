import os
import time
from pathlib import Path
from typing import Dict, List, Any
from src.utils import hashstr, get_docker_safe_url, logger
from src import config


def split_text_into_chunks(text: str, file_id: str, filename: str,
                          chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Dict]:
    """
    将文本分割成块

    Args:
        text: 要分割的文本
        file_id: 文件ID
        filename: 文件名
        chunk_size: 块大小
        chunk_overlap: 块重叠大小

    Returns:
        List[Dict]: 分割后的文本块列表
    """
    chunks = []

    # 简单的分块策略：按段落和长度分割
    paragraphs = text.split('\n\n')

    current_chunk = ""
    chunk_index = 0

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        # 如果当前块加上新段落会超过限制，保存当前块
        if len(current_chunk) + len(paragraph) > chunk_size and current_chunk:
            chunks.append({
                "id": f"{file_id}_chunk_{chunk_index}",
                "content": current_chunk.strip(),
                "file_id": file_id,
                "filename": filename,
                "chunk_index": chunk_index,
                "source": filename,
                "chunk_id": f"{file_id}_chunk_{chunk_index}"
            })

            # 开始新块，包含重叠内容
            if len(current_chunk) > chunk_overlap:
                current_chunk = current_chunk[-chunk_overlap:] + "\n\n" + paragraph
            else:
                current_chunk = paragraph
            chunk_index += 1
        else:
            if current_chunk:
                current_chunk += "\n\n" + paragraph
            else:
                current_chunk = paragraph

    # 添加最后一块
    if current_chunk.strip():
        chunks.append({
            "id": f"{file_id}_chunk_{chunk_index}",
            "content": current_chunk.strip(),
            "file_id": file_id,
            "filename": filename,
            "chunk_index": chunk_index,
            "source": filename,
            "chunk_id": f"{file_id}_chunk_{chunk_index}"
        })

    return chunks


def prepare_item_metadata(item: str, content_type: str, db_id: str) -> Dict:
    """
    准备文件或URL的元数据

    Args:
        item: 文件路径或URL
        content_type: 内容类型 ('file' 或 'url')
        db_id: 数据库ID

    Returns:
        Dict: 包含元数据的字典
    """
    if content_type == "file":
        file_path = Path(item)
        file_id = f"file_{hashstr(str(file_path) + str(time.time()), 6)}"
        file_type = file_path.suffix.lower().replace(".", "")
        filename = file_path.name
        item_path = str(file_path)
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


def get_embedding_config(embed_info: Dict) -> Dict:
    """
    获取嵌入模型配置

    Args:
        embed_info: 嵌入信息字典

    Returns:
        Dict: 标准化的嵌入配置
    """
    config_dict = {}

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

    logger.debug(f"Embedding config: {config_dict}")
    return config_dict