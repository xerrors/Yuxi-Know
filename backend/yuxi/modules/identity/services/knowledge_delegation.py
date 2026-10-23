"""知识库 MCP 委托的实时身份验证。"""

from yuxi.modules.identity.repositories.users import UserRepository
from yuxi.modules.identity.security import verify_knowledge_token


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
