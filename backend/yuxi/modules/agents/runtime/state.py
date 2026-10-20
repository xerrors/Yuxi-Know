"""Define the state structures for the agent."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain.agents import AgentState


def merge_artifacts(existing: list[str] | None, new: list[str] | None) -> list[str]:
    """对交付物字符串路径保序去重。"""
    return list(dict.fromkeys((existing or []) + (new or [])))


class RuntimeWarning(TypedDict):
    """可持久化并直接展示的运行警告。"""

    code: str
    source: str
    message: str


class BaseState(AgentState):
    """Shared state fields for Yuxi agents."""

    artifacts: Annotated[list[str], merge_artifacts]
    warnings: list[RuntimeWarning]


class AgentStatePayload(TypedDict):
    """Serialized agent state payload consumed by the frontend."""

    warnings: list[RuntimeWarning]
    artifacts: list[str]
    token_usage: dict | None
