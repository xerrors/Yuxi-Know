"""知识库 MCP 的短期凭据与当前身份验证。"""

import os
from datetime import timedelta
from typing import Any

import jwt

from yuxi.modules.identity.repositories.users import UserRepository
from yuxi.modules.identity.security import JWT_ALGORITHM, require_configured_jwt_secret
from yuxi.shared.datetime import utc_now

KNOWLEDGE_MCP_AUDIENCE = "yuxi-knowledge-mcp"
KNOWLEDGE_MCP_PURPOSE = "agent-knowledge-read"
KNOWLEDGE_DELEGATION_SECONDS = 300


def create_knowledge_token(*, uid: str, selection: str | list[str]) -> str:
    """仅供可信运行上下文签发五分钟知识库只读委托。"""
    if not uid or not _valid_knowledge_selection(selection):
        raise ValueError("知识库委托缺少用户或有效选择范围")
    secret, issuer = require_knowledge_delegation_config()
    now = utc_now()
    return jwt.encode(
        {
            "sub": uid,
            "iss": issuer,
            "aud": KNOWLEDGE_MCP_AUDIENCE,
            "purpose": KNOWLEDGE_MCP_PURPOSE,
            "selection": selection,
            "iat": now,
            "exp": now + timedelta(seconds=KNOWLEDGE_DELEGATION_SECONDS),
        },
        secret,
        algorithm=JWT_ALGORITHM,
    )


def verify_knowledge_token(token: str) -> dict[str, Any]:
    """拒绝登录 Token、其他用途和不合法委托范围。"""
    secret, issuer = require_knowledge_delegation_config()
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            issuer=issuer,
            audience=KNOWLEDGE_MCP_AUDIENCE,
            options={"require": ["sub", "iss", "aud", "purpose", "selection", "iat", "exp"]},
        )
        if (
            payload["purpose"] != KNOWLEDGE_MCP_PURPOSE
            or not payload["sub"]
            or not _valid_knowledge_selection(payload["selection"])
            or not 0 < payload["exp"] - payload["iat"] <= KNOWLEDGE_DELEGATION_SECONDS
        ):
            raise ValueError("无效的知识库委托")
        return payload
    except (jwt.PyJWTError, TypeError, KeyError) as exc:
        raise ValueError("无效或过期的知识库委托") from exc


def require_knowledge_delegation_config() -> tuple[str, str]:
    """委托跨进程使用部署密钥和实例标识，禁止隐式随机配置。"""
    secret = require_configured_jwt_secret()
    instance_id = os.environ.get("YUXI_INSTANCE_ID", "").strip()
    if not instance_id:
        raise ValueError("Knowledge MCP 委托需要配置共享 YUXI_INSTANCE_ID")
    return secret, f"yuxi-know:{instance_id}"


async def authenticate_knowledge_delegate(token: str, db):
    """验证签名范围并复核账号，终端用户保留数据库内的 APP 身份。"""
    payload = verify_knowledge_token(token)
    repo = UserRepository()
    user = await repo.get_by_uid_with_db(db, payload["sub"])
    if user is None or user.is_deleted or user.is_login_locked():
        raise ValueError("知识库委托用户不可用")
    if user.user_kind == "human" and not user.department_id:
        raise ValueError("知识库委托用户未绑定部门")
    if user.user_kind == "end_user":
        owner = await repo.get_by_id_with_db(db, user.owner_user_id)
        if not user.app_id or owner is None or owner.is_deleted or owner.is_login_locked():
            raise ValueError("知识库委托用户不可用")
    return user, payload["selection"]


def _valid_knowledge_selection(selection: object) -> bool:
    """接受 all 或全为非空字符串的列表，显式空列表保持空范围。"""
    if selection == "all":
        return True
    return isinstance(selection, list) and all(isinstance(item, str) and item.strip() for item in selection)
