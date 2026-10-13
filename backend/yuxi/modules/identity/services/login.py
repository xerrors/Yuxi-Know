"""各登录方式共用的令牌与身份结果。"""

from yuxi.modules.identity.models import User


def login_result(user: User, access_token: str, department_name: str | None = None) -> dict:
    """固定登录公开字段，沿用用户投影的头像地址规范。"""
    profile = user.to_dict()
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "uid": user.uid,
        "phone_number": user.phone_number,
        "avatar": profile["avatar"],
        "role": user.role,
        "department_id": user.department_id,
        "department_name": department_name,
    }
