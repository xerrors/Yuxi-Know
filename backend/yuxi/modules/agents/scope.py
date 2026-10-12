"""Agent 对话用例使用的已认证资源作用域。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActorScope:
    """在认证边界固定用户、APP 与凭据来源。"""

    uid: str
    app_id: str | None
    api_key_id: int | None = None
    is_superadmin: bool = False
