"""Deep Agent - 基于create_deep_agent的深度分析智能体"""

from deepagents import create_deep_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.middlewares import context_based_model, inject_attachment_context
from src.agents.common.tools import search

from .prompts import DEEP_PROMPT

search_tools = [search]


research_sub_agent = {
    "name": "research-agent",
    "description": (
        "用于研究更深入的问题。一次只给这个研究员一个主题。不要向这个研究员传递多个子问题。"
        "相反，你应该将一个大主题分解成必要的组成部分，然后并行调用多个研究代理，每个子问题一个。"
    ),
    "system_prompt": (
        "你是一位专注的研究员。你的工作是根据用户的问题进行研究。"
        "进行彻底的研究，然后用详细的答案回复用户的问题，只有你的最终答案会被传递给用户。"
        "除了你的最终信息，他们不会知道任何其他事情，所以你的最终报告应该就是你的最终信息！"
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
        tools = search_tools
        return tools

    async def get_graph(self, **kwargs):
        """构建 Deep Agent 的图"""
        if self.graph:
            return self.graph

        # 获取上下文配置
        context = self.context_schema.from_file(module_name=self.module_name)

        # 使用 create_deep_agent 创建深度智能体
        graph = create_deep_agent(
            model=load_chat_model(context.model),
            tools=await self.get_tools(),
            subagents=[critique_sub_agent, research_sub_agent],
            middleware=[
                context_based_model,  # 动态模型选择
                context_aware_prompt,  # 动态系统提示词
                inject_attachment_context,  # 附件上下文注入
            ],
            checkpointer=await self._get_checkpointer(),
        )

        self.graph = graph
        return graph
