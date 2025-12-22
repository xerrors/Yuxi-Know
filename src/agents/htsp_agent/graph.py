from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.mcp import MCP_SERVERS
from src.agents.common.middlewares import (
    DynamicToolMiddleware,
    context_aware_prompt,
    context_based_model,
    inject_attachment_context,
)
from src.agents.common.subagents import calc_agent_tool

from .context import Context
from .tools import get_tools


class HtspAgent(BaseAgent):
    name = "合同审批助手"
    description = "专门用于合同审批流程的智能助手，支持合同审核、风险评估、条款检查等功能。"
    capabilities = ["file_upload"]  # 支持文件上传功能

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph = None
        self.checkpointer = None
        self.context_schema = Context

    def get_tools(self):
        """返回合同审批相关工具"""
        base_tools = get_tools()
        base_tools.append(calc_agent_tool)
        return base_tools

    async def get_graph(self, **kwargs):
        """构建图"""
        if self.graph:
            return self.graph

        # 创建动态工具中间件实例，并传入所有可用的 MCP 服务器列表
        dynamic_tool_middleware = DynamicToolMiddleware(
            base_tools=self.get_tools(), mcp_servers=list(MCP_SERVERS.keys())
        )

        # 预加载所有 MCP 工具并注册到 middleware.tools
        await dynamic_tool_middleware.initialize_mcp_tools()

        # 使用 create_agent 创建智能体，并传入 middleware
        graph = create_agent(
            model=load_chat_model("siliconflow/Qwen/Qwen3-235B-A22B-Instruct-2507"),  # 默认模型，会被 middleware 覆盖
            tools=self.get_tools(),  # 注册合同审批相关工具
            middleware=[
                context_aware_prompt,  # 动态系统提示词
                inject_attachment_context,  # 附件上下文注入（LangChain 标准中间件）
                context_based_model,  # 动态模型选择
                dynamic_tool_middleware,  # 动态工具选择（支持 MCP 工具注册）
                ModelRetryMiddleware(),  # 模型重试中间件
            ],
            checkpointer=await self._get_checkpointer(),
        )

        self.graph = graph
        return graph

    async def process_messages_non_stream(self, messages: list[str], input_context=None, **kwargs):
        """非流式处理消息，等待完整响应后一次性返回"""
        context = self.context_schema.from_file(module_name=self.module_name, input_context=input_context)
        
        # 检查是否启用流式输出
        if getattr(context, 'streaming', False):
            # 如果启用了流式输出，回退到原有的流式方法
            async for msg, metadata in self.stream_messages(messages, input_context=input_context):
                yield msg, metadata
            return
        
        # 使用 invoke 方法进行非流式处理
        result = await self.invoke_messages(messages, input_context=input_context)
        
        # 从结果中提取AI响应消息
        messages_list = result.get("messages", [])
        for msg in messages_list:
            if hasattr(msg, 'type') and msg.type == 'ai':
                # 返回AI消息和元数据
                yield msg, {"agent_id": self.id, "non_stream": True}


def main():
    pass


if __name__ == "__main__":
    main()
    # asyncio.run(main())