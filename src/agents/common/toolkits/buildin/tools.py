import os
import traceback
import uuid
from typing import Annotated, Any

import requests
from langgraph.types import interrupt

from src import config, graph_base
from src.agents.common.toolkits import tool
from src.storage.minio import aupload_file_to_minio
from src.utils import logger

# Lazy initialization for TavilySearch (only when TAVILY_API_KEY is available)
_tavily_search_instance = None


def get_tavily_search():
    """Get TavilySearch instance lazily, only when API key is available."""
    global _tavily_search_instance
    if _tavily_search_instance is None and config.enable_web_search:
        from langchain_tavily import TavilySearch

        _tavily_search_instance = TavilySearch()
        _tavily_search_instance.metadata = {"name": "Tavily 网页搜索", "category": "buildin", "tags": ["搜索"]}

    # 即使没有配置 API_KEY 也返回实例，调用时会出错
    return _tavily_search_instance


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


@tool(category="buildin", tags=["图片", "测试"], display_name="文生图测试")
async def text_to_img_demo(text: str) -> str:
    """【测试用】使用模型生成图片， 会返回图片的URL"""

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
        logger.error(f"Failed to generate image with: {e}")
        raise ValueError(f"Image generation failed: {e}")

    try:
        image_url = response_json["images"][0]["url"]
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Failed to parse image URL from response: {e}, {response_json=}")
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


@tool(category="debug", tags=["内置", "审批"], display_name="人工审批")
def get_approved_user_goal(
    operation_description: str,
) -> dict:
    """
    请求人工审批，在执行重要操作前获得人类确认。

    Args:
        operation_description: 需要审批的操作描述，例如 "调用知识库工具"
    Returns:
        dict: 包含审批结果的字典，格式为 {"approved": bool, "message": str}
    """
    # 构建详细的中断信息
    interrupt_info = {
        "question": "是否批准以下操作？",
        "operation": operation_description,
    }

    # 触发人工审批
    is_approved = interrupt(interrupt_info)

    # 返回审批结果
    if is_approved:
        result = {
            "approved": True,
            "message": f"✅ 操作已批准：{operation_description}",
        }
        print(f"✅ 人工审批通过: {operation_description}")
    else:
        result = {
            "approved": False,
            "message": f"❌ 操作被拒绝：{operation_description}",
        }
        print(f"❌ 人工审批被拒绝: {operation_description}")

    return result


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


def get_buildin_tools() -> list:
    """获取内置工具列表"""
    static_tools = [
        query_knowledge_graph,
        get_approved_user_goal,
        calculator,
        text_to_img_demo,
    ]

    # 始终添加 tavily_search，无论是否配置 API_KEY（调用时会出错）
    static_tools.append(get_tavily_search())

    return static_tools
