"""Deep Agent - 基于create_deep_agent的深度分析智能体"""

from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.subagents import SubAgentMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, SummarizationMiddleware, TodoListMiddleware, dynamic_prompt

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.middlewares import inject_attachment_context
from src.agents.common.tools import get_tavily_search

from .context import DeepContext
from .prompts import DEEP_PROMPT


def _get_research_sub_agent(search_tools: list) -> dict:
    """Get research sub-agent config with search tools."""
    return {
        "name": "research-agent",
        "description": ("利用搜索工具，用于研究更深入的问题。将调研结果写入到主题研究文件中。"),
        "system_prompt": (
            "你是一位专注的研究员。你的工作是根据用户的问题进行研究。"
            "进行彻底的研究，然后用详细的答案回复用户的问题，只有你的最终答案会被传递给用户。"
            "除了你的最终信息，他们不会知道任何其他事情，所以你的最终报告应该就是你的最终信息！"
            "将调研结果保存到主题研究文件中 /sub_research/xxx.md 中。"
        ),
        "tools": search_tools,
    }


critique_sub_agent = {
    "name": "critique-agent",
    "description": "用于评论最终报告。给这个代理一些关于你希望它如何评论报告的信息。",
    "system_prompt": (
        "你是一位专注的编辑。你的任务是评论一份报告。\n\n"
        "你可以在 `final_report.md` 找到这份报告。\n\n"
        "你可以在 `question.txt` 找到这份报告的问题/主题。\n\n"
        "用户可能会要求评论报告的特定方面。请用详细的评论回复用户，指出报告中可以改进的地方。\n\n"
        "如果有助于你评论报告，你可以使用搜索工具来搜索信息\n\n"
        "不要自己写入 `final_report.md`。\n\n"
        "需要检查的事项：\n"
        "- 检查每个部分的标题是否恰当\n"
        "- 检查报告的写法是否像论文或教科书——它应该是以文本为主，不要只是一个项目符号列表！\n"
        "- 检查报告是否全面。如果任何段落或部分过短，或缺少重要细节，请指出来。\n"
        "- 检查文章是否涵盖了行业的关键领域，确保了整体理解，并且没有遗漏重要部分。\n"
        "- 检查文章是否深入分析了原因、影响和趋势，提供了有价值的见解\n"
        "- 检查文章是否紧扣研究主题并直接回答问题\n"
        "- 检查文章是否结构清晰、语言流畅、易于理解。"
    ),
}


@dynamic_prompt
def context_aware_prompt(request: ModelRequest) -> str:
    """从 runtime context 动态生成系统提示词"""
    return DEEP_PROMPT + "\n\n\n" + request.runtime.context.system_prompt


class DeepAgent(BaseAgent):
    name = "深度分析智能体"
    description = "具备规划、深度分析和子智能体协作能力的智能体，可以处理复杂的多步骤任务"
    context_schema = DeepContext
    capabilities = [
        "file_upload",
        "todo",
        "files",
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph = None
        self.checkpointer = None

    async def get_tools(self):
        """返回 Deep Agent 的专用工具"""
        tools = []
        tavily_search = get_tavily_search()
        if tavily_search:
            tools.append(tavily_search)

        # Assert that search tool is available for DeepAgent
        assert tools, (
            "DeepAgent requires at least one search tool. "
            "Please configure TAVILY_API_KEY environment variable to enable web search."
        )
        return tools

    async def get_graph(self, **kwargs):
        """构建 Deep Agent 的图"""
        if self.graph:
            return self.graph

        # 获取上下文配置
        context = self.context_schema.from_file(module_name=self.module_name)

        model = load_chat_model(context.model)
        sub_model = load_chat_model(context.subagents_model)
        tools = await self.get_tools()

        # Build subagents with search tools
        research_sub_agent = _get_research_sub_agent(tools)

        # 使用 create_deep_agent 创建深度智能体
        graph = create_agent(
            model=model,
            tools=tools,
            system_prompt=context.system_prompt,
            middleware=[
                context_aware_prompt,  # 动态系统提示词
                inject_attachment_context,  # 附件上下文注入
                TodoListMiddleware(),
                FilesystemMiddleware(),
                SubAgentMiddleware(
                    default_model=sub_model,
                    default_tools=tools,
                    subagents=[critique_sub_agent, research_sub_agent],
                    default_middleware=[
                        TodoListMiddleware(),  # 子智能体也有 todo 列表
                        FilesystemMiddleware(),  # 当前的两个文件系统是隔离的
                        SummarizationMiddleware(
                            model=sub_model,
                            trigger=("tokens", 110000),
                            keep=("messages", 10),
                            trim_tokens_to_summarize=None,
                        ),
                        PatchToolCallsMiddleware(),
                    ],
                    general_purpose_agent=True,
                ),
                SummarizationMiddleware(
                    model=model,
                    trigger=("tokens", 110000),
                    keep=("messages", 10),
                    trim_tokens_to_summarize=None,
                ),
                PatchToolCallsMiddleware(),
            ],
            checkpointer=await self._get_checkpointer(),
        )

        self.graph = graph
        return graph
