"""用户 Agent 环境配置的校验、读取与提交用例。"""

import re
from typing import Any

from yuxi.modules.agents.repositories.environment import AgentEnvRepository, AgentEnvWriteResult
from yuxi.shared.datetime import utc_now
from yuxi.shared.errors import InvalidOperationError

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
