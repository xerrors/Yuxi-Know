import uvicorn

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from server.routers import router
from server.utils.auth_middleware import get_current_user, is_public_path, is_admin_path
from server.models.user_model import User
from src.utils.logging_config import logger


app = FastAPI()
app.include_router(router)

# CORS 设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 鉴权中间件
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 获取请求路径
        path = request.url.path

        # 检查是否为公开路径，公开路径无需身份验证
        if is_public_path(path):
            return await call_next(request)

        # 注意：前端代理已经去掉了 /api 前缀，例如 /api/chat 变成了 /chat
        # 判断是否需要验证的API请求，包括聊天、数据、工具等
        is_api_path = (
            path.startswith("/chat") or
            path.startswith("/data") or
            path.startswith("/admin") or
            path.startswith("/auth") and not is_public_path(path)
        )

        if not is_api_path:
            # 非API路径，可能是前端路由或静态资源
            return await call_next(request)

        # 提取Authorization头
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "请先登录"},
                headers={"WWW-Authenticate": "Bearer"}
            )

        # 获取token
        token = auth_header.split("Bearer ")[1]

        # 添加token到请求状态，后续路由可以直接使用
        request.state.token = token

        # 检查是否需要管理员权限
        if is_admin_path(path):
            # 尝试获取数据库会话
            try:
                from server.db_manager import db_manager
                from server.utils.auth_utils import AuthUtils

                db = db_manager.get_session()
                try:
                    # 验证token并获取用户信息
                    payload = AuthUtils.verify_access_token(token)
                    user_id = payload.get("sub")

                    if not user_id:
                        return JSONResponse(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            content={"detail": "无效的用户标识"},
                            headers={"WWW-Authenticate": "Bearer"}
                        )

                    # 查询用户信息
                    from server.models.user_model import User
                    user = db.query(User).filter(User.id == user_id).first()

                    if not user:
                        return JSONResponse(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            content={"detail": "用户不存在"},
                            headers={"WWW-Authenticate": "Bearer"}
                        )

                    # 检查管理员权限
                    if user.role not in ["admin", "superadmin"]:
                        return JSONResponse(
                            status_code=status.HTTP_403_FORBIDDEN,
                            content={"detail": "需要管理员权限"}
                        )

                    # 将用户信息添加到请求状态
                    request.state.user = user

                finally:
                    db.close()

            except Exception as e:
                logger.error(f"验证管理员权限出错: {e}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "验证用户权限出错"},
                    headers={"WWW-Authenticate": "Bearer"}
                )

        # 继续处理请求
        return await call_next(request)

# 添加鉴权中间件
app.add_middleware(AuthMiddleware)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5050, threads=10, workers=10, reload=True)

