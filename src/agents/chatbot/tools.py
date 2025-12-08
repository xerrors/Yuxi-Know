import os
import uuid
from typing import Any

import requests
from langchain.tools import tool

from src.agents.common import get_buildin_tools
from src.agents.common.toolkits.mysql import get_mysql_tools
from src.storage.minio import aupload_file_to_minio
from src.utils import logger


@tool
async def text_to_img_qwen(text: str) -> str:
    """（用来测试文件存储）使用模型生成图片， 会返回图片的URL"""

    url = "https://api.siliconflow.cn/v1/images/generations"

    payload = {
        "model": "Qwen/Qwen-Image",
        "prompt": text,
    }
    headers = {"Authorization": f"Bearer {os.getenv('SILICONFLOW_API_KEY')}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers)
        response_json = response.json()
    except Exception as e:
        logger.error(f"Failed to generate image with Kolors: {e}")
        raise ValueError(f"Image generation failed: {e}")

    try:
        image_url = response_json["images"][0]["url"]
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Failed to parse image URL from Kolors response: {e}, {response_json=}")
        raise ValueError(f"Image URL extraction failed: {e}")

    # 2. Upload to MinIO (Simplified)
    response = requests.get(image_url)
    file_data = response.content

    file_name = f"{uuid.uuid4()}.jpg"
    image_url = await aupload_file_to_minio(
        bucket_name="generated-images", file_name=file_name, data=file_data, file_extension="jpg"
    )
    logger.info(f"Image uploaded. URL: {image_url}")
    return image_url


def get_tools() -> list[Any]:
    """获取所有可运行的工具（给大模型使用）"""
    tools = get_buildin_tools()
    tools.append(text_to_img_qwen)
    tools.extend(get_mysql_tools())
    return tools
