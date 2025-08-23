"""通用工具函数"""

from sqlalchemy.orm import Session
from fastapi import Request
from server.models.user_model import User, OperationLog


def log_operation(db: Session, user_id: int, operation: str, details: str = None, request: Request = None):
    """记录用户操作日志"""
    ip_address = None
    if request:
        ip_address = request.client.host if request.client else None

    log = OperationLog(
        user_id=user_id,
        operation=operation,
        details=details,
        ip_address=ip_address
    )
    db.add(log)
    db.commit()


def get_user_dict(user: User, include_password: bool = False) -> dict:
    """获取用户字典表示"""
    return user.to_dict(include_password)
