from types import SimpleNamespace

import pytest

from yuxi.modules.agents.runtime.agent_backends.chatbot.prompt import PROMPT, build_prompt_with_context


@pytest.mark.parametrize("custom_prompt", ["", "用户补充规则\n保留第二行"])
def test_chatbot_prompt_preserves_base_workdir_and_custom_context(custom_prompt):
    """动态上下文进入拼装结果，且自定义规则保留在末尾。"""
    workdir = "/home/user/workspace/projects/prompt-test"
    prompt = build_prompt_with_context(SimpleNamespace(workdir_path=f"{workdir}/", system_prompt=custom_prompt))

    assert PROMPT.strip() in prompt
    assert f"{workdir}/uploads/" in prompt
    assert f"{workdir}//" not in prompt
    if custom_prompt:
        assert prompt.endswith(custom_prompt)


@pytest.mark.parametrize("workdir", [None, "", "/"])
def test_chatbot_prompt_rejects_missing_workdir(workdir):
    """没有当前工作目录时拒绝拼装。"""
    with pytest.raises(ValueError, match="缺少当前 Workdir"):
        build_prompt_with_context(SimpleNamespace(workdir_path=workdir, system_prompt=""))
