"""Define the state structures for the agent."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain.agents import AgentState


def merge_artifacts(existing: list[str | dict] | None, new: list[str | dict] | None) -> list[str]:
    """按路径保序去重，并读取旧 checkpoint 的交付物对象。"""
    return list(dict.fromkeys(item if isinstance(item, str) else item["path"] for item in (existing or []) + (new or [])))


class BaseState(AgentState):
    """Shared state fields for Yuxi agents."""

    artifacts: Annotated[list[str], merge_artifacts]


class AgentStatePayload(TypedDict):
    """Serialized agent state payload consumed by the frontend."""

    todos: list
    artifacts: list[str]
    token_usage: dict | None
