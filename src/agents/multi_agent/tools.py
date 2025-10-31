from typing import Any

from langchain.tools import tool
from langchain_core.runnables import RunnableConfig

from src.agents import agent_manager
from src.agents.common.tools import get_buildin_tools
from src.utils import logger

# TODO[修改建议]:能不能通过前端直接指定子智能体？
# 调用子智能体后的日志是输出到tool_calls的
@tool(name_or_callable="对话聊天智能体", description="调用指定智能体进行对话聊天的功能")
async def call_chatbot(query: str, config: RunnableConfig) -> str:
    """
    调用指定chatbot智能体进行对话聊天的功能

    Args:
        query: 根据需要构造的提问
        config: LangGraph运行时配置(自动注入)
    Returns:
        str: 最终的回答结果
    """
    try:
        input = [{"role": "user", "content": query}]
        chatbot = agent_manager.get_agent("ChatbotAgent")
        configurable = config.get("configurable",{})
        input_context = {
            "thread_id":configurable.get("thread_id"),
            "user_id": configurable.get("user_id"),
        }
        message = await chatbot.invoke_messages(input,input_context=input_context)
        # 直接获取最后一个消息的内容
        final_answer = message.get('messages', [])[-1].content
        logger.info(f"ChatbotAgent: {final_answer}")
        return final_answer
    except Exception as e:
        logger.error(f"CallAgent error: {e}")
        raise

@tool(name_or_callable="加密计算智能体", description="调用指定智能体进行加密计算的功能")
async def call_react_agent(query: str, config: RunnableConfig) -> str:
    """
    调用指定智能体进行加密计算的功能

    Args:
        query: 根据需要构造的提问
        config: LangGraph运行时配置(自动注入)
    Returns:
        str: 最终的回答结果
    """
    try:
        input = [{"role": "user", "content": query}]
        chatbot = agent_manager.get_agent("ReActAgent")
        configurable = config.get("configurable",{})
        input_context = {
            "thread_id":configurable.get("thread_id"),
            "user_id": configurable.get("user_id"),
        }
        message = await chatbot.invoke_messages(input,input_context=input_context)
        # 直接获取最后一个消息的内容
        final_answer = message.get('messages', [])[-1].content
        logger.info(f"ReActAgent: {final_answer}")
        return final_answer
    except Exception as e:
        logger.error(f"CallAgent error: {e}")
        raise


def get_tools() -> list[Any]:
    """获取所有可运行的工具（给大模型使用）"""
    tools = get_buildin_tools()
    tools.append(call_chatbot)
    tools.append(call_react_agent)
    return tools
