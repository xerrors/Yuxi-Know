"""工具装配缺失和未知来源不能通过当前授权边界。"""

from dataclasses import fields
from types import SimpleNamespace

import pytest

from yuxi.modules.agents.runtime.context import BaseContext
from yuxi.modules.agents.runtime.middlewares.authorization import tool_allowed


@pytest.fixture
def context():
    """分别声明已注册本地、框架和 MCP 工具。"""
    return SimpleNamespace(
        tools=["local"],
        mcps=["server"],
        registered_builtin_tool_names={"local", "gated"},
        middleware_tool_names={"read_file"},
        mcp_tool_servers={"remote": "server"},
        disabled_mcp_tools={"server": set()},
        skill_runtime_snapshot={"effective_skills": [], "preloaded_skills": [], "runtime_skills": {}},
    )


def test_only_registered_and_currently_authorized_tools_are_accepted(context):
    """合法框架工具继续可用，未配置和未注册工具拒绝。"""
    assert tool_allowed(context, "local", {})
    assert tool_allowed(context, "read_file", {})
    assert tool_allowed(context, "remote", {})
    assert not tool_allowed(context, "gated", {})
    assert not tool_allowed(context, "unknown", {})
    context.disabled_mcp_tools["server"].add("remote")
    assert not tool_allowed(context, "remote", {})


@pytest.mark.parametrize("name", ["registered_builtin_tool_names", "mcp_tool_servers", "skill_runtime_snapshot"])
def test_missing_or_unprepared_tool_assembly_cannot_authorize(context, name):
    """替代 Context 的缺失或未初始化状态均不能放行。"""
    setattr(context, name, None)
    assert not tool_allowed(context, "read_file", {})
    delattr(context, name)
    assert not tool_allowed(context, "local", {})


def test_runtime_fields_are_declared_and_excluded_from_user_configuration():
    """运行身份与授权派生内容不能由持久配置伪造。"""
    names = {"skill_runtime_snapshot", "mcp_tool_servers", "registered_builtin_tool_names", "middleware_tool_names", "disabled_mcp_tools"}
    schema = {item.name: item for item in fields(BaseContext)}
    assert names <= schema.keys()
    assert all(schema[name].metadata["configurable"] is False for name in names)
    assert not names & BaseContext.get_configurable_items().keys()
    context = BaseContext()
    context.update_config({name: {"forged": "value"} for name in names})
    assert context.skill_runtime_snapshot is None
    assert context.mcp_tool_servers is None
    assert context.registered_builtin_tool_names is None
    assert context.middleware_tool_names == set()


@pytest.mark.asyncio
async def test_dynamic_mcp_loading_requires_prior_tool_source_assembly():
    """Skill 动态建连不能在缺失来源记录时开始。"""
    from yuxi.modules.agents.runtime.middlewares.skills import SkillsMiddleware

    with pytest.raises(RuntimeError, match="来源尚未装配"):
        await SkillsMiddleware()._get_mcp_tools_from_context(BaseContext(), extra_mcps=["server"])
