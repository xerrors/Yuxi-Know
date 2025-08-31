import inspect
import asyncio
import traceback
from typing import Annotated, Any
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool, tool
from langchain_tavily import TavilySearch

from src import config, graph_base, knowledge_base
from src.utils import logger


@tool
def query_knowledge_graph(query: Annotated[str, "The keyword to query knowledge graph."]) -> Any:
    """Use this to query knowledge graph, which include some food domain knowledge."""
    try:
        logger.debug(f"Querying knowledge graph with: {query}")
        result = graph_base.query_node(query, hops=2, return_format='triples')
        logger.debug(f"Knowledge graph query returned {len(result.get('triples', [])) if isinstance(result, dict) else 'N/A'} triples")
        return result
    except Exception as e:
        logger.error(f"Knowledge graph query error: {e}, {traceback.format_exc()}")
        return f"知识图谱查询失败: {str(e)}"

def get_static_tools() -> list:
    """注册静态工具"""
    static_tools = [
        query_knowledge_graph,
    ]

    # 检查是否启用网页搜索
    if config.enable_web_search:
        static_tools.append(TavilySearch(max_results=10))

    return static_tools


class KnowledgeRetrieverModel(BaseModel):
    query_text: str = Field(
        description=(
            "查询的关键词，查询的时候，应该尽量以可能帮助回答这个问题的关键词进行查询，"
            "不要直接使用用户的原始输入去查询。"
        )
    )



def get_kb_based_tools() -> list:
    """获取所有知识库基于的工具"""
    # 获取所有知识库
    kb_tools = []
    retrievers = knowledge_base.get_retrievers()

    def _create_retriever_wrapper(db_id: str, retriever_info: dict[str, Any]):
        """创建检索器包装函数的工厂函数，避免闭包变量捕获问题"""
        async def async_retriever_wrapper(query_text: str) -> Any:
            """异步检索器包装函数"""
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
            # 使用改进的工具ID生成策略
            tool_id = f"query_{db_id[:8]}"

            # 构建工具描述
            description = (
                f"使用 {retrieve_info['name']} 知识库进行检索。\n"
                f"下面是这个知识库的描述：\n{retrieve_info['description'] or '没有描述。'} "
            )

            # 使用工厂函数创建检索器包装函数，避免闭包问题
            retriever_wrapper = _create_retriever_wrapper(db_id, retrieve_info)

            # 使用 StructuredTool.from_function 创建异步工具
            tool = StructuredTool.from_function(
                coroutine=retriever_wrapper,
                name=tool_id,
                description=description,
                args_schema=KnowledgeRetrieverModel,
                metadata=retrieve_info["metadata"] | {
                    "tag": ["knowledgebase"]
                }
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
                metadata = getattr(tool_obj, 'metadata', {}) or {}
                info = {
                    "id": tool_obj.name,
                    "name": metadata.get('name', tool_obj.name),
                    "description": tool_obj.description,
                    'metadata': metadata,
                    "args": [],
                    # "is_async": is_async  # Include async information
                }

                if hasattr(tool_obj, 'args_schema') and tool_obj.args_schema:
                    schema = tool_obj.args_schema.schema()
                    for arg_name, arg_info in schema.get('properties', {}).items():
                        info["args"].append({
                            "name": arg_name,
                            "type": arg_info.get('type', ''),
                            "description": arg_info.get('description', '')
                        })

                tools_info.append(info)
                # logger.debug(f"Successfully processed tool info for {tool_obj.name}")

            except Exception as e:
                logger.error(f"Failed to process tool {getattr(tool_obj, 'name', 'unknown')}: {e}\n{traceback.format_exc()}")
                continue

    except Exception as e:
        logger.error(f"Failed to get tools info: {e}\n{traceback.format_exc()}")
        return []

    logger.info(f"Successfully extracted info for {len(tools_info)} tools")
    return tools_info
