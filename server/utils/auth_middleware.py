from typing import Optional, List, Callable
from fastapi import Depends, HTTPException, status, APIRouter
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
import re

from server.db_manager import db_manager
from server.models.user_model import User
from server.utils.auth_utils import AuthUtils

# 定义OAuth2密码承载器，指定token URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

# 公开路径列表，无需登录即可访问
PUBLIC_PATHS = [
    r"^/api/auth/token$",            # 登录
    r"^/api/auth/check-first-run$",  # 检查是否首次运行
    r"^/api/auth/initialize$",       # 初始化系统
    r"^/api$",                      # Health Check
    r"^/api/login$",                # 登录页面
]

# 获取数据库会话
def get_db():
    db = db_manager.get_session()
    try:
        yield db
    finally:
        db.close()

# 获取当前用户
async def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 允许无token访问公开路径
    if token is None:
        return None

    try:
        # 验证token
        payload = AuthUtils.verify_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    except ValueError as e:
        # 捕获AuthUtils.verify_access_token可能抛出的ValueError
        # 例如令牌过期或无效
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),  # 将错误信息直接传递给客户端
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 查找用户
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    return user

# 获取已登录用户（抛出401如果未登录）
async def get_required_user(user: Optional[User] = Depends(get_current_user)):
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请登录后再访问",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

# 获取管理员用户
async def get_admin_user(current_user: User = Depends(get_required_user)):
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user

# 获取超级管理员用户
async def get_superadmin_user(current_user: User = Depends(get_required_user)):
    if current_user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限",
        )
    return current_user

# 检查路径是否为公开路径
def is_public_path(path: str) -> bool:
    path = path.rstrip('/')  # 去除尾部斜杠以便于匹配
    for pattern in PUBLIC_PATHS:
        if re.match(pattern, path):
            return True
    return False
