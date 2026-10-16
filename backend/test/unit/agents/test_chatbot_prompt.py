from types import SimpleNamespace

from yuxi.modules.agents.runtime.agent_backends.chatbot.prompt import PROMPT, build_prompt_with_context


def test_chatbot_prompt_prefers_complete_explanatory_paragraphs():
    assert "减少 bullet points" in PROMPT
    assert "完整的句子和段落" in PROMPT
    assert "详细的解释和背景信息" in PROMPT


def test_chatbot_prompt_declares_workspace_visibility_and_default_write_boundary():
    prompt = build_prompt_with_context(
        SimpleNamespace(
            workdir_path="/home/user/workspace/projects/11111111-1111-4111-8111-111111111111",
            system_prompt="",
        )
    )

    assert "可以读取其他 Project 目录作为参考" in prompt
    assert "未经用户明确要求，不得在当前 Project Workdir 之外" in prompt
    assert "/home/user/workspace/agents/skills/" in prompt
    assert "html:preview" not in prompt


def test_chatbot_prompt_selects_web_tools_and_inline_image_component():
    """拼装输入区分搜索、浏览器操作与图片展示路径。"""
    prompt = build_prompt_with_context(
        SimpleNamespace(
            workdir_path="/home/user/workspace/projects/11111111-1111-4111-8111-111111111111",
            system_prompt="请简洁回答。",
        )
    )

    assert "网页事实或时效查询使用 web_search" in prompt
    assert "简单问题最多搜索一次，结果不足就说明未确认" in prompt
    assert "复杂调研再比较多源" in prompt
    assert "读取已安装的 agent-browser 或 playwright-cli Skill" in prompt
    assert "未安装时提示从 Skills 推荐安装" in prompt
    assert "稳定常识、写作、计算和本地资料不浏览" in prompt
    assert "展示图片时读取 chat-widgets" in prompt
    assert "下载或交付文件才用 present_artifacts" in prompt
    assert "只报告实际核验结果" in prompt
    assert prompt.endswith("请简洁回答。")
