import asyncio

from deepagents.backends import CompositeBackend, StateBackend

from yuxi.agents.middlewares.skills_middleware import normalize_selected_skills

from .sandbox import get_sandbox_provider
from .skills_backend import SelectedSkillsReadonlyBackend


def _get_visible_skills_from_runtime(runtime) -> list[str]:
    """获取运行时可见的 skills 列表"""
    context = getattr(runtime, "context", None)
    selected = getattr(context, "skills", None) or []
    return normalize_selected_skills(selected)


def create_agent_composite_backend(runtime, *, sandbox_backend=None) -> CompositeBackend:
    """为 agent 构建 backend：默认 State/Sandbox backend + /skills 路由只读 backend。"""
    visible_skills = _get_visible_skills_from_runtime(runtime)
    return CompositeBackend(
        default=sandbox_backend or StateBackend(runtime),
        routes={
            "/mnt/skills/": SelectedSkillsReadonlyBackend(selected_slugs=visible_skills),
        },
    )


def resolve_sandbox_backend(thread_id: str | None):
    """按 thread_id 获取沙盒 backend，失败时返回 None。"""
    if not thread_id:
        return None

    try:
        provider = get_sandbox_provider()
        return provider.acquire(str(thread_id))
    except Exception:
        return None


async def resolve_sandbox_backend_async(thread_id: str | None):
    """异步包装沙盒 backend 获取逻辑，失败时返回 None。"""
    if not thread_id:
        return None

    try:
        provider = get_sandbox_provider()
        return await asyncio.to_thread(provider.acquire, str(thread_id))
    except Exception:
        return None
