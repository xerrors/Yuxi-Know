from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.types import Command

import src.agents.common.middlewares.runtime_config_middleware as runtime_middleware
from src.agents.common.middlewares.runtime_config_middleware import RuntimeConfigMiddleware


@dataclass
class _FakeTool:
    name: str


@dataclass
class _FakeRequest:
    runtime: Any
    tools: list[Any]
    system_message: SystemMessage
    state: dict[str, Any]

    def override(self, **kwargs):
        return _FakeRequest(
            runtime=kwargs.get("runtime", self.runtime),
            tools=kwargs.get("tools", self.tools),
            system_message=kwargs.get("system_message", self.system_message),
            state=kwargs.get("state", self.state),
        )


@dataclass
class _FakeToolCallRequest:
    tool_call: dict[str, Any]
    runtime: Any
    state: dict[str, Any]


async def _echo_handler(request):
    return request


def _build_request(
    *,
    skills: list[str],
    tools: list[str],
    system_prompt: str = "你是助手",
    state: dict[str, Any] | None = None,
    skill_snapshot: dict[str, Any] | None = None,
) -> _FakeRequest:
    context = SimpleNamespace(
        system_prompt=system_prompt,
        skills=skills,
        tools=[],
        knowledges=[],
        mcps=[],
    )
    if skill_snapshot is not None:
        context.skill_session_snapshot = skill_snapshot
    runtime = SimpleNamespace(context=context)
    return _FakeRequest(
        runtime=runtime,
        tools=[_FakeTool(name=name) for name in tools],
        system_message=SystemMessage(content=[{"type": "text", "text": "base"}]),
        state=state or {},
    )


def _build_tool_request(*, skills: list[str], visible_skills: list[str], file_path: str) -> _FakeToolCallRequest:
    return _FakeToolCallRequest(
        tool_call={"name": "read_file", "args": {"file_path": file_path}},
        runtime=SimpleNamespace(
            context=SimpleNamespace(
                skills=skills,
                skill_session_snapshot=_build_snapshot(selected=skills, visible=visible_skills),
            )
        ),
        state={},
    )


def _extract_appended_prompt(request: _FakeRequest) -> str:
    return request.system_message.content_blocks[-1]["text"]


def _build_middleware() -> RuntimeConfigMiddleware:
    return RuntimeConfigMiddleware(
        enable_model_override=False,
        enable_tools_override=False,
        enable_system_prompt_override=True,
        enable_skills_prompt_override=True,
    )


def _build_snapshot(
    selected: list[str],
    visible: list[str] | None = None,
    metadata: dict[str, dict[str, str]] | None = None,
    dependency_map: dict[str, dict[str, list[str]]] | None = None,
) -> dict[str, Any]:
    return {
        "selected_skills": selected,
        "visible_skills": visible if visible is not None else selected,
        "prompt_metadata": metadata or {},
        "dependency_map": dependency_map or {},
    }


@pytest.mark.asyncio
async def test_abefore_agent_resolves_visible_skills_and_preinjects_prompt(monkeypatch: pytest.MonkeyPatch):
    async def fake_resolve(selected):
        assert selected == ["deliver-prd"]
        return _build_snapshot(
            selected=["deliver-prd"],
            visible=["deliver-prd", "brainstorming"],
            metadata={
                "deliver-prd": {
                    "name": "deliver-prd",
                    "description": "deliver prd",
                    "path": "/skills/deliver-prd/SKILL.md",
                },
                "brainstorming": {
                    "name": "brainstorming",
                    "description": "brainstorming desc",
                    "path": "/skills/brainstorming/SKILL.md",
                },
            },
            dependency_map={
                "deliver-prd": {"tools": [], "mcps": [], "skills": ["brainstorming"]},
                "brainstorming": {"tools": [], "mcps": [], "skills": []},
            },
        )

    monkeypatch.setattr(runtime_middleware, "resolve_session_snapshot", fake_resolve)
    middleware = _build_middleware()
    request = _build_request(skills=["deliver-prd"], tools=["read_file"], system_prompt="你是助手")

    await middleware.abefore_agent(request.state, request.runtime)

    snapshot = request.runtime.context.skill_session_snapshot
    assert snapshot["selected_skills"] == ["deliver-prd"]
    assert snapshot["visible_skills"] == ["deliver-prd", "brainstorming"]
    assert snapshot["dependency_map"]["deliver-prd"]["skills"] == ["brainstorming"]
    assert request.runtime.context._skills_prompt_injected is True
    assert "## Skills System" in request.runtime.context.system_prompt
    assert "- **deliver-prd**: deliver prd" in request.runtime.context.system_prompt
    assert "- **brainstorming**: brainstorming desc" in request.runtime.context.system_prompt


@pytest.mark.asyncio
async def test_abefore_agent_injection_is_idempotent(monkeypatch: pytest.MonkeyPatch):
    async def fake_resolve(_selected):
        return _build_snapshot(
            selected=["alpha"],
            metadata={"alpha": {"name": "alpha", "description": "alpha desc", "path": "/skills/alpha/SKILL.md"}},
        )

    monkeypatch.setattr(runtime_middleware, "resolve_session_snapshot", fake_resolve)
    middleware = _build_middleware()
    request = _build_request(skills=["alpha"], tools=["read_file"], system_prompt="base prompt")

    await middleware.abefore_agent(request.state, request.runtime)
    await middleware.abefore_agent(request.state, request.runtime)

    assert request.runtime.context.system_prompt.count("## Skills System") == 1


@pytest.mark.asyncio
async def test_awrap_model_call_keeps_preinjected_skills_prompt(monkeypatch: pytest.MonkeyPatch):
    middleware = _build_middleware()
    request = _build_request(
        skills=["alpha"],
        tools=["read_file"],
        system_prompt="base prompt\n\n## Skills System\n- **alpha**: alpha desc",
    )

    def raise_if_called(_skills_meta):
        raise AssertionError("_build_skills_section should not be called in awrap_model_call")

    monkeypatch.setattr(middleware, "_build_skills_section", raise_if_called)
    result = await middleware.awrap_model_call(request, _echo_handler)
    prompt = _extract_appended_prompt(result)

    assert "当前时间：" in prompt
    assert "## Skills System" in prompt
    assert "- **alpha**: alpha desc" in prompt


@pytest.mark.asyncio
async def test_abefore_agent_degrades_when_resolver_fails(monkeypatch: pytest.MonkeyPatch):
    async def fake_resolve(_selected):
        raise RuntimeError("boom")

    monkeypatch.setattr(runtime_middleware, "resolve_session_snapshot", fake_resolve)
    middleware = _build_middleware()
    request = _build_request(skills=["alpha"], tools=["read_file"], system_prompt="base prompt")

    await middleware.abefore_agent(request.state, request.runtime)

    snapshot = request.runtime.context.skill_session_snapshot
    assert snapshot["selected_skills"] == ["alpha"]
    assert snapshot["visible_skills"] == []
    assert "## Skills System" not in request.runtime.context.system_prompt


@pytest.mark.asyncio
async def test_awrap_tool_call_activates_skill_when_visible_in_context():
    middleware = _build_middleware()
    request = _build_tool_request(
        skills=["deliver-prd"],
        visible_skills=["deliver-prd", "brainstorming"],
        file_path="/skills/brainstorming/SKILL.md",
    )

    async def _handler(_request):
        return ToolMessage(content="ok", tool_call_id="tc-1")

    result = await middleware.awrap_tool_call(request, _handler)
    assert isinstance(result, Command)
    assert result.update["activated_skills"] == ["brainstorming"]


@pytest.mark.asyncio
async def test_awrap_tool_call_denies_invisible_skill():
    middleware = _build_middleware()
    request = _build_tool_request(
        skills=["deliver-prd"],
        visible_skills=["deliver-prd"],
        file_path="/skills/brainstorming/SKILL.md",
    )

    async def _handler(_request):
        return ToolMessage(content="ok", tool_call_id="tc-1")

    result = await middleware.awrap_tool_call(request, _handler)
    assert isinstance(result, ToolMessage)


@pytest.mark.asyncio
async def test_model_call_injects_dependency_tools_and_mcps_after_activation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runtime_middleware, "get_kb_based_tools", lambda db_names=None: [])

    snapshot = _build_snapshot(
        selected=["alpha"],
        visible=["alpha", "beta"],
        dependency_map={"alpha": {"tools": ["dep-tool"], "mcps": ["mcp-a"], "skills": ["beta"]}},
    )

    def fake_build_dependency_bundle(received_snapshot, activated):
        assert received_snapshot == snapshot
        assert activated == ["alpha"]
        return {"tools": ["dep-tool"], "mcps": ["mcp-a"], "skills": ["alpha", "beta"]}

    monkeypatch.setattr(runtime_middleware, "build_dependency_bundle", fake_build_dependency_bundle)

    async def fake_get_enabled_mcp_tools(server_name: str):
        if server_name == "mcp-a":
            return [_FakeTool(name="mcp_tool")]
        return []

    monkeypatch.setattr(runtime_middleware, "get_enabled_mcp_tools", fake_get_enabled_mcp_tools)

    middleware = RuntimeConfigMiddleware(
        extra_tools=[_FakeTool(name="mcp_tool")],
        enable_model_override=False,
        enable_tools_override=True,
        enable_system_prompt_override=False,
        enable_skills_prompt_override=False,
    )

    request = _build_request(
        skills=["alpha"],
        tools=["calculator", "dep-tool", "mcp_tool", "read_file"],
        state={"activated_skills": ["alpha"]},
        skill_snapshot=snapshot,
    )

    result = await middleware.awrap_model_call(request, _echo_handler)
    tool_names = [t.name for t in result.tools]
    assert "dep-tool" in tool_names
    assert "mcp_tool" in tool_names
    assert "calculator" not in tool_names
