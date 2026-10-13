"""共享范围写入的身份校验。"""

from sqlalchemy import select
from yuxi.modules.identity.models import User
from yuxi.modules.identity.permissions import normalize_permission_config


async def validate_shared_grants(db, share_config: dict) -> dict:
    """校验范围包含关系和指定管理者的当前角色。"""
    config = normalize_permission_config(share_config, strict=True)
    scope = config["manage_scope"]
    if scope and scope["access_level"] == "user":
        result = await db.execute(
            select(User.uid)
            .where(
                User.uid.in_(scope["user_uids"]),
                User.role.in_(("admin", "superadmin")),
                User.is_deleted == 0,
                User.user_kind == "human",
            )
            .with_for_update(read=True)
        )
        if set(result.scalars()) != set(scope["user_uids"]):
            raise ValueError("指定管理用户必须是有效管理员")
    return config
