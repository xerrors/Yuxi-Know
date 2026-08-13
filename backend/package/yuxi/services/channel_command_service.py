"""解析纯文本 Channel 的最小 slash command。"""

from __future__ import annotations

import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    """一个已规范化的 slash command。"""

    name: str
    args: tuple[str, ...] = ()


def parse_slash_command(text: str) -> SlashCommand | None:
    """解析以 ``/`` 开头的命令；普通文本返回 ``None``。"""
    normalized = str(text or "").strip()
    if not normalized.startswith("/"):
        return None

    try:
        parts = shlex.split(normalized)
    except ValueError as exc:
        raise ValueError("slash command 格式无效") from exc
    if not parts or not parts[0].startswith("/"):
        return None

    name = parts[0][1:].strip().lower()
    if not name:
        raise ValueError("slash command 不能为空")
    return SlashCommand(name=name, args=tuple(parts[1:]))
