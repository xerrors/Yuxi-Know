"""知识库工具模块"""
import inspect
import traceback
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src import knowledge_base
from src.utils import logger


class KnowledgeRetrieverModel(BaseModel):
    query_text: str | None = Field(
        default=None,
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


class CommonKnowledgeRetriever(KnowledgeRetrieverModel):
    """Common knowledge retriever model."""

    file_name: str | None = Field(
        default=None,
        description=(
            "（非必要不启用此参数，留空即可）当操作类型为 'search' 且已经读取思维导图之后，可以指定文件关键词，支持模糊匹配。\n"
            "仅当检索结果过多且不相关，需要进一步缩小范围时使用。"
        )
    )


def get_kb_based_tools(db_names: list[str] | None = None) -> list:
    """获取所有知识库基于的工具"""
    # 获取所有知识库
    kb_tools = []
    retrievers = knowledge_base.get_retrievers()
    if db_names is None:
        db_ids = None
    else:
        db_ids = [kb_id for kb_id, kb in retrievers.items() if kb["name"] in db_names]

    def _create_retriever_wrapper(db_id: str, retriever_info: dict[str, Any]):
        """创建检索器包装函数的工厂函数，避免闭包变量捕获问题"""

        async def async_retriever_wrapper(
            query_text: str, operation: str = "search", file_name: str | None = None
        ) -> Any:
            """异步检索器包装函数，支持检索和获取思维导图"""

            # 获取思维导图
            if operation == "get_mindmap":
                try:
                    logger.debug(f"Getting mindmap for database {db_id}")

                    from src.repositories.knowledge_base_repository import KnowledgeBaseRepository

                    kb_repo = KnowledgeBaseRepository()
                    kb = await kb_repo.get_by_id(db_id)

                    if kb is None:
                        return f"知识库 {retriever_info['name']} 不存在"

                    mindmap_data = kb.mindmap

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
                kwargs = {}
                if file_name:
                    kwargs["file_name"] = file_name

                if inspect.iscoroutinefunction(retriever):
                    result = await retriever(query_text, **kwargs)
                else:
                    result = retriever(query_text, **kwargs)
                logger.debug(f"Retrieved {len(result) if isinstance(result, list) else 'N/A'} results from {db_id}")
                return result
            except Exception as e:
                logger.error(f"Error in retriever {db_id}: {e}")
                return f"检索失败: {str(e)}"

        return async_retriever_wrapper

    for db_id, retrieve_info in retrievers.items():
        if db_ids is not None and db_id not in db_ids:
            continue

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

            args_schema = KnowledgeRetrieverModel
            if retrieve_info["metadata"]["kb_type"] in ["milvus"]:
                args_schema = CommonKnowledgeRetriever

            # 使用 StructuredTool.from_function 创建异步工具
            tool = StructuredTool.from_function(
                coroutine=retriever_wrapper,
                name=safename,
                description=description,
                args_schema=args_schema,
                metadata=retrieve_info["metadata"] | {"tag": ["knowledgebase"]},
            )

            kb_tools.append(tool)
            # logger.debug(f"Successfully created tool {tool_id} for database {db_id}")

        except Exception as e:
            logger.error(f"Failed to create tool for database {db_id}: {e}, \n{traceback.format_exc()}")
            continue

    return kb_tools
