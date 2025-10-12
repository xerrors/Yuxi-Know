from pathlib import Path

from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langgraph.runtime import get_runtime

from src import config as sys_config
from src.agents.common.base import BaseAgent
from src.agents.common.context import BaseContext
from src.agents.common.models import load_chat_model
from src.agents.common.tools import get_buildin_tools
from src.utils import logger

model = load_chat_model("siliconflow/Qwen/Qwen3-235B-A22B-Instruct-2507")


def prompt(state) -> list[AnyMessage]:
    runtime = get_runtime(BaseContext)
    system_msg = SystemMessage(content=runtime.context.system_prompt)
    return [system_msg] + state["messages"]


class ReActAgent(BaseAgent):
    name = "ReAct (all tools)"
    description = "A react agent that can answer questions and help with tasks."

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph = None
        self.workdir = Path(sys_config.save_dir) / "agents" / self.module_name
        self.workdir.mkdir(parents=True, exist_ok=True)

    async def get_graph(self, **kwargs):
        if self.graph:
            return self.graph

        available_tools = get_buildin_tools()
        self.checkpointer = await self._get_checkpointer()

        # 创建 ReActAgent
        graph = create_react_agent(model, tools=available_tools, prompt=prompt, checkpointer=self.checkpointer)
        self.graph = graph
        logger.info("ReActAgent 使用内存 checkpointer 构建成功")
        return graph
