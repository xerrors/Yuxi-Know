from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, ModelResponse, dynamic_prompt, wrap_model_call

from src.agents.common.base import BaseAgent
from src.agents.common.models import load_chat_model
from src.agents.common.tools import get_buildin_tools
from src.utils import logger


@dynamic_prompt
def context_aware_prompt(request: ModelRequest) -> str:
    runtime = request.runtime
    return runtime.context.system_prompt


@wrap_model_call
async def context_based_model(request: ModelRequest, handler) -> ModelResponse:
    # 从 runtime context 读取配置
    model_spec = request.runtime.context.model
    model = load_chat_model(model_spec)

    request = request.override(model=model)
    return await handler(request)


class ReActAgent(BaseAgent):
    name = "智能体 Demo"
    description = "A react agent that can answer questions and help with tasks."

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_tools(self):
        return get_buildin_tools()

    async def get_graph(self, **kwargs):
        if self.graph:
            return self.graph

        # 创建 ReActAgent
        graph = create_agent(
            model=load_chat_model("siliconflow/Qwen/Qwen3-235B-A22B-Instruct-2507"),  # 实际会被覆盖
            tools=self.get_tools(),
            middleware=[context_aware_prompt, context_based_model],
            checkpointer=await self._get_checkpointer(),
        )

        self.graph = graph
        return graph
