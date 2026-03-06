import os
import traceback
import uuid
from typing import Annotated, Any

import requests

from src import config, graph_base
from src.agents.common.toolkits.registry import ToolExtraMetadata, _all_tool_instances, _extra_registry, tool
from src.storage.minio import aupload_file_to_minio
from src.utils import logger

# Lazy initialization for TavilySearch (only when API key is available)
_tavily_search_instance = None


def _create_tavily_search():
    """Create and register TavilySearch tool with metadata."""
    global _tavily_search_instance
    if _tavily_search_instance is None:
        from langchain_tavily import TavilySearch

        _tavily_search_instance = TavilySearch()

    return _tavily_search_instance


# 注册 TavilySearch 工具（延迟初始化）
def _register_tavily_tool():
    """Register TavilySearch tool with extra metadata."""
    tavily_instance = _create_tavily_search()
    # 手动注册到全局注册表
    _extra_registry["tavily_search"] = ToolExtraMetadata(
        category="buildin",
        tags=["搜索"],
        display_name="Tavily 网页搜索",
    )
    # 添加到工具实例列表
    _all_tool_instances.append(tavily_instance)


# 模块加载时注册
if config.enable_web_search:
    try:
        _register_tavily_tool()
    except Exception as e:
        logger.warning(f"Failed to register TavilySearch tool: {e}")


@tool(category="buildin", tags=["计算"], display_name="计算器")
def calculator(a: float, b: float, operation: str) -> float:
    """计算器：对给定的2个数字进行基本数学运算"""
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


KG_QUERY_DESCRIPTION = """
使用这个工具可以查询知识图谱中包含的三元组信息。
关键词（query），使用可能帮助回答这个问题的关键词进行查询，不要直接使用用户的原始输入去查询。
"""


@tool(category="buildin", tags=["图谱"], display_name="查询知识图谱", description=KG_QUERY_DESCRIPTION)
def query_knowledge_graph(query: Annotated[str, "The keyword to query knowledge graph."]) -> Any:
    """使用这个工具可以查询知识图谱中包含的三元组信息。关键词（query），使用可能帮助回答这个问题的关键词进行查询，不要直接使用用户的原始输入去查询。"""
    try:
        logger.debug(f"Querying knowledge graph with: {query}")
        result = graph_base.query_node(query, hops=2, return_format="triples")
        logger.debug(
            f"Knowledge graph query returned "
            f"{len(result.get('triples', [])) if isinstance(result, dict) else 'N/A'} triples"
        )
        return result
    except Exception as e:
        logger.error(f"Knowledge graph query error: {e}, {traceback.format_exc()}")
        return f"知识图谱查询失败: {str(e)}"


@tool(category="buildin", tags=["图片", "生成"], display_name="Qwen-Image")
async def text_to_img_qwen_image(
    prompt: Annotated[str, "用于生成图片的文本描述"],
    negative_prompt: Annotated[str, "负面提示词，用于指定不想出现在图片中的元素"] = "",
    num_inference_steps: Annotated[int, "推理步数，范围1-100"] = 20,
    guidance_scale: Annotated[float, "引导强度，控制图片与提示词的匹配程度"] = 7.5,
) -> str:
    """使用 Qwen-Image 模型生成图片，返回图片的URL，需要注意的是，生成结果不会默认展示，需要将返回的URL进行展示处理。"""
    url = "https://api.siliconflow.cn/v1/images/generations"

    payload = {
        "model": "Qwen/Qwen-Image",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "num_inference_steps": num_inference_steps,
        "guidance_scale": guidance_scale,
    }
    headers = {"Authorization": f"Bearer {os.getenv('SILICONFLOW_API_KEY')}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers)
        response_json = response.json()
    except Exception as e:
        logger.error(f"Failed to generate image with: {e}")
        raise ValueError(f"Image generation failed: {e}")

    try:
        image_url = response_json["images"][0]["url"]
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Failed to parse image URL from response: {e}, {response_json=}")
        raise ValueError(f"Image URL extraction failed: {e}")

    # Upload to MinIO
    response = requests.get(image_url)
    file_data = response.content

    file_name = f"{uuid.uuid4()}.jpg"
    image_url = await aupload_file_to_minio(
        bucket_name="generated-images", file_name=file_name, data=file_data, file_extension="jpg"
    )
    logger.info(f"Image uploaded. URL: {image_url}")
    return image_url
