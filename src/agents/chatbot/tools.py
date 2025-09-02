from io import BytesIO
from typing import Any

from langchain_core.tools import tool
from PIL import Image, ImageDraw, ImageFont

from src.agents.common.tools import get_buildin_tools
from src.utils import logger
from src.utils.minio_utils import upload_image_to_minio


@tool
def calculator(a: float, b: float, operation: str) -> float:
    """Calculate two numbers. operation: add, subtract, multiply, divide"""
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
async def text_to_img(text: str) -> str:
    """
    文生图函数，根据文本生成一张包含该文本的图片，并将其上传到文件服务器，最终返回图片的公开访问 URL。
    A text-to-image function that generates an image containing the given text,
    uploads it to a file server, and returns the public URL of the image.
    """
    logger.info(f"Generating image for text: {text}")
    # 1. Simulate image generation using Pillow
    try:
        img = Image.new("RGB", (400, 100), color=(73, 109, 137))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 15)
        except OSError:
            font = ImageFont.load_default()
        draw.text((10, 10), f"Generated from: {text}", fill=(255, 255, 0), font=font)

        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)
        file_data = img_bytes.read()
        logger.info("Image data generated successfully.")
    except Exception as e:
        logger.error(f"Failed to generate image with Pillow: {e}")
        raise ValueError(f"Image generation failed: {e}")

    # 2. Upload to MinIO (Simplified)
    image_url = upload_image_to_minio(data=file_data, file_extension="jpg")
    logger.info(f"Image uploaded. URL: {image_url}")
    return image_url


def get_tools() -> list[Any]:
    """获取所有可运行的工具（给大模型使用）"""
    tools = get_buildin_tools()
    tools.append(calculator)
    tools.append(text_to_img)
    return tools
