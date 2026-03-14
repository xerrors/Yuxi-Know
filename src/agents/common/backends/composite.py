from __future__ import annotations

from deepagents.backends import CompositeBackend

from src.sandbox import ProvisionerSandboxBackend
from src.agents.common.middlewares.skills_middleware import normalize_selected_skills

from .skills_backend import SelectedSkillsReadonlyBackend


def _get_visible_skills_from_runtime(runtime) -> list[str]:
    """获取运行时可见的 skills 列表"""
    context = getattr(runtime, "context", None)
    selected = getattr(context, "skills", None) or []
    return normalize_selected_skills(selected)


def _extract_thread_id(runtime) -> str:
    config = getattr(runtime, "config", None)
    if isinstance(config, dict):
        configurable = config.get("configurable", {})
        if isinstance(configurable, dict):
            thread_id = configurable.get("thread_id")
            if isinstance(thread_id, str) and thread_id.strip():
                return thread_id.strip()

    context = getattr(runtime, "context", None)
    thread_id = getattr(context, "thread_id", None)
    if isinstance(thread_id, str) and thread_id.strip():
        return thread_id.strip()

    raise ValueError("thread_id is required in runtime configurable context")


def create_agent_composite_backend(runtime) -> CompositeBackend:
    visible_skills = _get_visible_skills_from_runtime(runtime)
    thread_id = _extract_thread_id(runtime)
    return CompositeBackend(
        default=ProvisionerSandboxBackend(thread_id=thread_id),
        routes={
            "/skills/": SelectedSkillsReadonlyBackend(selected_slugs=visible_skills),
        },
    )
