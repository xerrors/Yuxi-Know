"""通用工具函数"""

import logging
from sqlalchemy.orm import Session
from fastapi import Request
from server.models.user_model import User, OperationLog


def setup_logging():
    """配置应用程序日志格式"""
    # 配置日志格式
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True
    )

    # 确保uvicorn的日志也使用相同格式
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_access_logger = logging.getLogger("uvicorn.access")

    # 创建格式化器
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%m-%d %H:%M:%S"
    )

    # 为所有处理器设置格式化器
    for handler in uvicorn_logger.handlers:
        handler.setFormatter(formatter)
    for handler in uvicorn_access_logger.handlers:
        handler.setFormatter(formatter)


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
