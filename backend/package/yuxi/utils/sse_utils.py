"""Shared helpers and timing settings for server-sent event streams."""

from __future__ import annotations

import json
import os

SSE_HEARTBEAT_SECONDS = int(os.getenv("RUN_SSE_HEARTBEAT_SECONDS", "15"))
# Compose limits development-server graceful shutdown separately, so a live
# stream cannot block hot reload for this full connection lifetime.
SSE_MAX_CONNECTION_MINUTES = int(os.getenv("RUN_SSE_MAX_CONNECTION_MINUTES", "30"))
SSE_POLL_INTERVAL_SECONDS = float(os.getenv("RUN_SSE_POLL_INTERVAL_SECONDS", "0.5"))
# SSE 阻塞读取 Redis Stream 的单次挂起上限(毫秒)。有事件立即返回，无事件挂起
# 最多这么久再检查 heartbeat/终止态，把流式延迟从轮询间隔降到毫秒级。
SSE_STREAM_BLOCK_MS = int(os.getenv("RUN_SSE_STREAM_BLOCK_MS", "1000"))


def format_sse(data: dict, event: str, event_id: str | None = None) -> str:
    lines = [f"event: {event}", f"data: {json.dumps(data, ensure_ascii=False)}"]
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append("")
    return "\n".join(lines) + "\n"


def format_heartbeat() -> str:
    return ": heartbeat\n\n"
