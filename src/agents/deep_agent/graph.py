"""Deep Agent - 基于create_deep_agent的深度分析智能体"""

import os
from typing import Literal

from deepagents import create_deep_agent
from tavily import TavilyClient

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.middlewares import (
    context_aware_prompt,
    context_based_model,
    inject_attachment_context,
)
from src.agents.common.tools import search

from .context import DeepContext

# 最佳实践是初始化客户端一次并复用它。
tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


# 用于进行研究的搜索工具
def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """运行网络搜索"""
    search_docs = tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )
    return search_docs


sub_research_prompt = """你是一位专注的研究员。你的工作是根据用户的问题进行研究。

进行彻底的研究，然后用详细的答案回复用户的问题

只有你的最终答案会被传递给用户。除了你的最终信息，他们不会知道任何其他事情，所以你的最终报告应该就是你的最终信息！"""

research_sub_agent = {
    "name": "research-agent",
    "description": (
        "用于研究更深入的问题。一次只给这个研究员一个主题。不要向这个研究员传递多个子问题。"
        "相反，你应该将一个大主题分解成必要的组成部分，然后并行调用多个研究代理，每个子问题一个。"
    ),
    "system_prompt": sub_research_prompt,
    "tools": [internet_search],
}

sub_critique_prompt = """你是一位专注的编辑。你的任务是评论一份报告。

你可以在 `final_report.md` 找到这份报告。

你可以在 `question.txt` 找到这份报告的问题/主题。

用户可能会要求评论报告的特定方面。请用详细的评论回复用户，指出报告中可以改进的地方。

如果有助于你评论报告，你可以使用搜索工具来搜索信息

不要自己写入 `final_report.md`。

需要检查的事项：
- 检查每个部分的标题是否恰当
- 检查报告的写法是否像论文或教科书——它应该是以文本为主，不要只是一个项目符号列表！
- 检查报告是否全面。如果任何段落或部分过短，或缺少重要细节，请指出来。
- 检查文章是否涵盖了行业的关键领域，确保了整体理解，并且没有遗漏重要部分。
- 检查文章是否深入分析了原因、影响和趋势，提供了有价值的见解
- 检查文章是否紧扣研究主题并直接回答问题
- 检查文章是否结构清晰、语言流畅、易于理解。
"""

critique_sub_agent = {
    "name": "critique-agent",
    "description": "用于评论最终报告。给这个代理一些关于你希望它如何评论报告的信息。",
    "system_prompt": sub_critique_prompt,
}


# 用于引导代理成为专家级研究员的提示前缀
research_instructions = """你是一位专家级研究员。你的工作是进行彻底的研究，然后撰写一份精美的报告。

你应该做的第一件事是把原始的用户问题写入 `question.txt`，以便你有一个记录。

使用 research-agent 进行深入研究。它会用详细的答案回应你的问题/主题。

当你认为有足够的信息来撰写最终报告时，就把它写入 `final_report.md`

你可以调用 critique-agent 来获取对最终报告的评论。之后（如果需要）你可以做更多的研究并编辑 `final_report.md`
你可以根据需要重复这个过程，直到你对结果满意为止。

一次只编辑一个文件（如果你并行调用这个工具，可能会有冲突）。

以下是撰写最终报告的说明：

<report_instructions>

关键：确保答案的语言与人类信息的语言相同！如果你制定了一个待办事项计划，你应该在计划中注明报告应该使用什么语言。
注意：报告应该使用的语言是问题所在的语言，而不是问题所涉及的国家/地区的语言。

请根据整体研究简报创建一个详细的答案，该答案应：
1. 组织良好，有恰当的标题（# 用于标题，## 用于章节，### 用于子章节）
2. 包含研究中的具体事实和见解
3. 使用 [标题](URL) 格式引用相关来源
4. 提供平衡、透彻的分析。尽可能全面，并包含与整体研究问题相关的所有信息。使用你进行深入研究，并期望得到详细、全面的答案
5. 在末尾包含一个“来源”部分，列出所有引用的链接

你可以用多种不同的方式来组织你的报告。以下是一些例子：

要回答一个要求你比较两件事物的问题，你可以这样组织你的报告：
1/ 引言
2/ 主题A概述
3/ 主题B概述
4/ A与B的比较
5/ 结论

要回答一个要求你返回一个事物列表的问题，你可能只需要一个部分，即整个列表。
1/ 事物列表或表格
或者，你可以选择将列表中的每一项都作为报告中的一个独立部分。当被要求提供列表时，你不需要引言或结论。
1/ 项目1
2/ 项目2
3/ 项目3

要回答一个要求你总结一个主题、给出一份报告或概述的问题，你可以这样组织你的报告：
1/ 主题概述
2/ 概念1
3/ 概念2
4/ 概念3
5/ 结论

如果你认为你可以用一个部分来回答问题，你也可以这样做！
1/ 答案

请记住：章节是一个非常灵活和松散的概念。你可以按照你认为最好的方式来组织你的报告，包括上面没有列出的方式！
确保你的各个部分是连贯的，并且对读者来说是有意义的。

对于报告的每个部分，请执行以下操作：
- 使用简单、清晰的语言
- 对报告的每个部分使用 ## 作为章节标题（Markdown 格式）
- 绝不要将自己称为报告的作者。这应该是一份专业的报告，不含任何自我指涉的语言。
- 不要在报告中说你正在做什么。只需撰写报告，不要添加任何你自己的评论。
- 每个部分的长度应足以用你收集到的信息。预计各部分会长且详尽。你正在撰写一份深入的研究报告，用户会期望得到透彻的答案。
- 在适当的时候使用项目符号来列出信息，但默认情况下，请以段落形式撰写。

请记住：
简报和研究可能是英文的，但在撰写最终答案时，你需要将这些信息翻译成正确的语言。
确保最终答案报告的语言与消息历史中的人类信息语言相同。

用清晰的 markdown 格式化报告，结构合理，并在适当的地方包含来源引用。

<引用规则>
- 在你的文本中为每个唯一的 URL 分配一个引文编号
- 以 ### 来源 结尾，列出每个来源及其对应的编号
- 重要提示：无论你选择哪些来源，最终列表中的来源编号都应连续无间断（1,2,3,4...）
- 每个来源都应该是列表中的一个独立行项目，这样在 markdown 中它会被渲染成一个列表。
- 示例格式：
  [1] 来源标题: URL
  [2] 来源标题: URL
- 引用非常重要。请确保包含这些内容，并特别注意确保其正确性。用户通常会使用这些引文来查找更多信息。
</引用规则>
</report_instructions>

你可以使用一些工具。

## `internet_search`

使用此工具对给定的查询进行网络搜索。你可以指定结果数量、主题以及是否包含原始内容。
"""


class DeepAgent(BaseAgent):
    name = "深度分析智能体"
    description = "具备规划、深度分析和子智能体协作能力的智能体，可以处理复杂的多步骤任务"
    context_schema = DeepContext
    capabilities = [
        "file_upload",
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph = None
        self.checkpointer = None

    def get_tools(self):
        """返回 Deep Agent 的专用工具"""
        tools = [search]
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
            system_prompt=context.system_prompt,
            tools=self.get_tools(),
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
