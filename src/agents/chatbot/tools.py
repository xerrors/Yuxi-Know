import os
from typing import Any

import requests
from langchain.tools import tool

from src.agents.common.toolkits.mysql import get_mysql_tools
from src.agents.common.tools import get_buildin_tools
from src.storage.minio import upload_image_to_minio
from src.utils import logger

#TODO:[已完成]修改了tool定义的示例，使用更符合langgraph调用的方式
@tool(name_or_callable="全能计算器",description="可以对给定的2个数字选择进行加减乘除四种计算")
def calculator(a: float, b: float, operation: str) -> float:
    """
    可以对给定的2个数字选择进行加减乘除四种计算

    Args:
      a: 第一个数字
      b: 第二个数字
      operation: 计算操作符号，可以是add，subtract，multiply，divide

    Returns:
        float: 最终的计算结果
    """
    try:
        if operation == "add":
            return a + b
        elif operation == "subtract":
            return a - b
        elif operation == "multiply":
            return a * b
        elif operation == "divide":
            if b == 0:
                raise ZeroDivisionError("除数不能为零")
            return a / b
        else:
            raise ValueError(f"不支持的运算类型: {operation}，仅支持 add, subtract, multiply, divide")
    except Exception as e:
        logger.error(f"Calculator error: {e}")
        raise


@tool
async def text_to_img_qwen(text: str) -> str:
    """（用来测试文件存储）使用Kolors模型生成图片， 会返回图片的URL"""

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

    image_url = upload_image_to_minio(bucket_name="generated-images", data=file_data, file_extension="jpg")
    logger.info(f"Image uploaded. URL: {image_url}")
    return image_url


def get_tools() -> list[Any]:
    """获取所有可运行的工具（给大模型使用）"""
    tools = get_buildin_tools()
    tools.append(calculator)
    tools.append(text_to_img_qwen)
    tools.extend(get_mysql_tools())
    return tools
