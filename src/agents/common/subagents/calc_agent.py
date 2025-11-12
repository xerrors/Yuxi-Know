from langchain.agents import create_agent
from langchain.tools import tool

from src import config
from src.agents.common import load_chat_model
from src.agents.common.tools import calculator

calc_agent = create_agent(
    model=load_chat_model(config.default_model),
    tools=[calculator],
    system_prompt="你可以使用计算器工具，处理各种数学计算任务。",
)


@tool(name_or_callable="calc_agent_tool", description="进行计算任务，输入是数学表达式或描述，输出计算结果。")
async def calc_agent_tool(description: str) -> str:
    """CalcAgent 工具 - 使用子智能体 CalcAgent 进行计算任务"""
    response = await calc_agent.ainvoke({"messages": [("user", description)]})
    return response["messages"][-1].content
