from typing import Optional, List
from fastapi import Depends, HTTPException, status
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
    r"^/auth/token$",            # 登录
    r"^/auth/check-first-run$",  # 检查是否首次运行
    r"^/auth/initialize$",       # 初始化系统
    r"^/docs$", r"^/redoc$", r"^/openapi.json$",  # API文档
    r"^/static/.*$",                # 静态资源
    r"^/assets/.*$",                # 前端资源文件
    r"^/$",                         # 根路径（登录页）
    r"^/login$",                    # 登录页面
    r"^/home$",                     # 首页
    r"^/home/.*$",                  # 首页下的所有路径
    r"^/favicon\.ico$",             # 网站图标
    r"^/_nuxt/.*$",                 # Nuxt.js生成的资源文件
    r"^/js/.*$",                    # JavaScript文件
    r"^/css/.*$",                   # CSS文件
    r"^/img/.*$"                    # 图片文件
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

# 路径是否需要管理员权限
ADMIN_PATHS = [
    r"^/admin/.*$",              # 管理员接口
    r"^/data/.*$",               # 数据操作接口，所有数据操作都需要管理员权限
    r"^/chat/set_default_agent$", # 设置默认智能体
    r"^/chat/models/update$",     # 更新模型列表
    r"^/auth/users.*$",           # 用户管理相关API
    r"^/config$"                  # 系统配置API
]

# 路径是否需要超级管理员权限
SUPERADMIN_PATHS = [
    r"^/restart$",                # 系统重启
    r"^/auth/users/\d+/role$"     # 修改用户角色（仅超级管理员可操作）
]

# 检查路径是否需要管理员权限
def is_admin_path(path: str) -> bool:
    path = path.rstrip('/')  # 去除尾部斜杠以便于匹配
    for pattern in ADMIN_PATHS:
        if re.match(pattern, path):
            return True
    return False

# 检查路径是否需要超级管理员权限
def is_superadmin_path(path: str) -> bool:
    path = path.rstrip('/')  # 去除尾部斜杠以便于匹配
    for pattern in SUPERADMIN_PATHS:
        if re.match(pattern, path):
            return True
    return False