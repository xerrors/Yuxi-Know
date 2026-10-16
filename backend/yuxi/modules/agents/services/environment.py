"""用户 Agent 环境配置的校验、读取、提交与生效验证。"""

import asyncio
import json
import re
import shlex
from typing import Any

from yuxi.infrastructure.filesystem import await_io
from yuxi.modules.agents.repositories.environment import AgentEnvRepository, AgentEnvWriteResult
from yuxi.modules.agents.runtime.sandbox.provider import get_sandbox_provider
from yuxi.modules.workspace.runtime_paths import WORKSPACE_PATH
from yuxi.shared.datetime import format_utc_datetime, utc_now
from yuxi.shared.errors import InvalidOperationError, StateConflictError, UpstreamError

ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_ENV_COUNT = 200
MAX_ENV_KEY_LENGTH = 128
MAX_ENV_VALUE_LENGTH = 32768


async def read_agent_env(db, *, uid: str) -> AgentEnvWriteResult:
    """读取当前用户配置，不存在时返回空环境。"""
    item = await AgentEnvRepository(db).get_by_uid(uid)
    return (
        AgentEnvWriteResult(env=item.env or {}, updated_at=item.updated_at)
        if item is not None
        else AgentEnvWriteResult(env={}, updated_at=None)
    )


async def write_agent_env(db, *, uid: str, env: dict[str, Any]) -> AgentEnvWriteResult:
    """内容变化时提交，重复相同值保持原时间且不空提交。"""
    normalized = validate_agent_env(env)
    try:
        result = await AgentEnvRepository(db).upsert(uid=uid, env=normalized, updated_at=utc_now())
        if result.changed:
            await db.commit()
        return result
    except Exception:
        await db.rollback()
        raise


async def verify_agent_env(db, *, uid: str) -> dict:
    """以真实新命令核对已保存变量，只返回键名与匹配结果。"""
    saved = await read_agent_env(db, uid=uid)
    matches = {}
    if saved.env:
        expected = json.dumps(saved.env, ensure_ascii=False).encode()
        # 密钥通过 stdin 传入，避免进入命令参数和错误输出。
        code = f"""import json
import os
import sys

expected = json.loads(sys.stdin.buffer.read({len(expected)}))
matches = {{key: os.environ.get(key) == value for key, value in expected.items()}}
print(json.dumps(matches))
"""
        try:
            output, exit_code, truncated = await await_io(
                asyncio.to_thread(
                    get_sandbox_provider().execute,
                    uid,
                    "/usr/bin/python3 -I -c " + shlex.quote(code),
                    WORKSPACE_PATH,
                    30,
                    stdin_data=expected,
                )
            )
            matches = json.loads(output)
            if exit_code != 0 or truncated or not isinstance(matches, dict):
                raise ValueError("验证命令未正常完成")
            if matches.keys() != saved.env.keys() or any(type(value) is not bool for value in matches.values()):
                raise ValueError("验证结果无效")
        except Exception as exc:
            raise UpstreamError("环境变量验证失败，请检查环境状态和 shell 启动配置后重试") from exc
    current = await read_agent_env(db, uid=uid)
    if current.updated_at != saved.updated_at or current.env != saved.env:
        raise StateConflictError("验证期间环境变量已修改，请刷新配置后重新验证")
    return {
        "updated_at": format_utc_datetime(saved.updated_at),
        "verified_at": format_utc_datetime(utc_now()),
        "variables": [{"key": key, "matches": matches[key]} for key in saved.env],
    }


def validate_agent_env(env: dict[str, Any]) -> dict[str, str]:
    """规范化用户环境键值并保留当前限额。"""
    if len(env) > MAX_ENV_COUNT:
        raise InvalidOperationError(f"环境变量数量不能超过 {MAX_ENV_COUNT} 个")

    normalized: dict[str, str] = {}
    for key, value in env.items():
        if not isinstance(key, str):
            raise InvalidOperationError("环境变量名必须是字符串")
        name = key.strip()
        if not name:
            raise InvalidOperationError("环境变量名不能为空")
        if len(name) > MAX_ENV_KEY_LENGTH:
            raise InvalidOperationError(f"环境变量名长度不能超过 {MAX_ENV_KEY_LENGTH}")
        if not ENV_KEY_PATTERN.match(name):
            raise InvalidOperationError(f"环境变量名 {name} 格式不正确")
        if name in normalized:
            raise InvalidOperationError(f"环境变量名 {name} 重复")
        if not isinstance(value, str):
            raise InvalidOperationError(f"环境变量 {name} 的值必须是字符串")
        if len(value) > MAX_ENV_VALUE_LENGTH:
            raise InvalidOperationError(f"环境变量 {name} 的值过长")
        normalized[name] = value
    return normalized
