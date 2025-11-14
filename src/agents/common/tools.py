import asyncio
import traceback
from typing import Annotated, Any

from langchain.tools import tool
from langchain_core.tools import StructuredTool
from langchain_tavily import TavilySearch
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from src import config, graph_base, knowledge_base
from src.utils import logger

search = TavilySearch(max_results=10)
search.metadata = {"name": "Tavily 网页搜索"}


@tool(name_or_callable="计算器", description="可以对给定的2个数字选择进行 add, subtract, multiply, divide 运算")
def calculator(a: float, b: float, operation: str) -> float:
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


@tool(name_or_callable="人工审批工具(Debug)", description="请求人工审批工具，用于在执行重要操作前获得人类确认。")
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


@tool(name_or_callable="查询知识图谱", description=KG_QUERY_DESCRIPTION)
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


def get_static_tools() -> list:
    """注册静态工具"""
    static_tools = [query_knowledge_graph, get_approved_user_goal, calculator]

    # 检查是否启用网页搜索
    if config.enable_web_search:
        static_tools.append(search)

    return static_tools


class KnowledgeRetrieverModel(BaseModel):
    query_text: str = Field(
        description=(
            "查询的关键词，查询的时候，应该尽量以可能帮助回答这个问题的关键词进行查询，不要直接使用用户的原始输入去查询。"
        )
    )
    operation: str = Field(
        default="search",
        description=(
            "操作类型：'search' 表示检索知识库内容，'get_mindmap' 表示获取知识库的思维导图结构。"
            "当用户询问知识库的整体结构、文件分类、知识架构时，使用 'get_mindmap'。"
            "当用户需要查询具体内容时，使用 'search'。"
        ),
    )


def get_kb_based_tools() -> list:
    """获取所有知识库基于的工具"""
    # 获取所有知识库
    kb_tools = []
    retrievers = knowledge_base.get_retrievers()

    def _create_retriever_wrapper(db_id: str, retriever_info: dict[str, Any]):
        """创建检索器包装函数的工厂函数，避免闭包变量捕获问题"""

        async def async_retriever_wrapper(query_text: str, operation: str = "search") -> Any:
            """异步检索器包装函数，支持检索和获取思维导图"""

            # 获取思维导图
            if operation == "get_mindmap":
                try:
                    logger.debug(f"Getting mindmap for database {db_id}")

                    # 从知识库元数据中获取思维导图
                    if db_id not in knowledge_base.global_databases_meta:
                        return f"知识库 {retriever_info['name']} 不存在"

                    db_meta = knowledge_base.global_databases_meta[db_id]
                    mindmap_data = db_meta.get("mindmap")

                    if not mindmap_data:
                        return f"知识库 {retriever_info['name']} 还没有生成思维导图。"

                    # 将思维导图数据转换为文本格式，便于AI理解
                    def mindmap_to_text(node, level=0):
                        """递归将思维导图JSON转换为层级文本"""
                        indent = "  " * level
                        text = f"{indent}- {node.get('content', '')}\n"
                        for child in node.get("children", []):
                            text += mindmap_to_text(child, level + 1)
                        return text

                    mindmap_text = f"知识库 {retriever_info['name']} 的思维导图结构：\n\n"
                    mindmap_text += mindmap_to_text(mindmap_data)

                    logger.debug(f"Successfully retrieved mindmap for {db_id}")
                    return mindmap_text

                except Exception as e:
                    logger.error(f"Error getting mindmap for {db_id}: {e}")
                    return f"获取思维导图失败: {str(e)}"

            # 默认：检索知识库
            retriever = retriever_info["retriever"]
            try:
                logger.debug(f"Retrieving from database {db_id} with query: {query_text}")
                if asyncio.iscoroutinefunction(retriever):
                    result = await retriever(query_text)
                else:
                    result = retriever(query_text)
                logger.debug(f"Retrieved {len(result) if isinstance(result, list) else 'N/A'} results from {db_id}")
                return result
            except Exception as e:
                logger.error(f"Error in retriever {db_id}: {e}")
                return f"检索失败: {str(e)}"

        return async_retriever_wrapper

    for db_id, retrieve_info in retrievers.items():
        try:
            # 构建工具描述
            description = (
                f"使用 {retrieve_info['name']} 知识库的多功能工具。\n"
                f"知识库描述：{retrieve_info['description'] or '没有描述。'}\n\n"
                f"支持的操作：\n"
                f"1. 'search' - 检索知识库内容：根据关键词查询相关文档片段\n"
                f"2. 'get_mindmap' - 获取思维导图：查看知识库的整体结构和文件分类\n\n"
                f"使用建议：\n"
                f"- 需要查询具体内容时，使用 operation='search'\n"
                f"- 想了解知识库结构、文件分类时，使用 operation='get_mindmap'"
            )

            # 使用工厂函数创建检索器包装函数，避免闭包问题
            retriever_wrapper = _create_retriever_wrapper(db_id, retrieve_info)

            safename = retrieve_info["name"].replace(" ", "_")[:20]

            # 使用 StructuredTool.from_function 创建异步工具
            tool = StructuredTool.from_function(
                coroutine=retriever_wrapper,
                name=safename,
                description=description,
                args_schema=KnowledgeRetrieverModel,
                metadata=retrieve_info["metadata"] | {"tag": ["knowledgebase"]},
            )

            kb_tools.append(tool)
            # logger.debug(f"Successfully created tool {tool_id} for database {db_id}")

        except Exception as e:
            logger.error(f"Failed to create tool for database {db_id}: {e}, \n{traceback.format_exc()}")
            continue

    return kb_tools


def get_buildin_tools() -> list:
    """获取所有可运行的工具（给大模型使用）"""
    tools = []

    try:
        # 获取所有知识库基于的工具
        tools.extend(get_kb_based_tools())
        tools.extend(get_static_tools())

        from src.agents.common.toolkits.mysql.tools import get_mysql_tools

        tools.extend(get_mysql_tools())

    except Exception as e:
        logger.error(f"Failed to get knowledge base retrievers: {e}")

    return tools


def gen_tool_info(tools) -> list[dict[str, Any]]:
    """获取所有工具的信息（用于前端展示）"""
    tools_info = []

    try:
        # 获取注册的工具信息
        for tool_obj in tools:
            try:
                metadata = getattr(tool_obj, "metadata", {}) or {}
                info = {
                    "id": tool_obj.name,
                    "name": metadata.get("name", tool_obj.name),
                    "description": tool_obj.description,
                    "metadata": metadata,
                    "args": [],
                    # "is_async": is_async  # Include async information
                }

                if hasattr(tool_obj, "args_schema") and tool_obj.args_schema:
                    if isinstance(tool_obj.args_schema, dict):
                        schema = tool_obj.args_schema
                    else:
                        schema = tool_obj.args_schema.schema()

                    for arg_name, arg_info in schema.get("properties", {}).items():
                        info["args"].append(
                            {
                                "name": arg_name,
                                "type": arg_info.get("type", ""),
                                "description": arg_info.get("description", ""),
                            }
                        )

                tools_info.append(info)
                # logger.debug(f"Successfully processed tool info for {tool_obj.name}")

            except Exception as e:
                logger.error(
                    f"Failed to process tool {getattr(tool_obj, 'name', 'unknown')}: {e}\n{traceback.format_exc()}. "
                    f"Details: {dict(tool_obj.__dict__)}"
                )
                continue

    except Exception as e:
        logger.error(f"Failed to get tools info: {e}\n{traceback.format_exc()}")
        return []

    logger.info(f"Successfully extracted info for {len(tools_info)} tools")
    return tools_info
