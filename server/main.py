import uvicorn

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from server.routers import router
from server.utils.auth_middleware import is_public_path
from server.utils.common_utils import setup_logging

# 设置日志配置
setup_logging()

app = FastAPI()
app.include_router(router, prefix="/api")

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

        if not path.startswith("/api"):
            # 非API路径，可能是前端路由或静态资源
            return await call_next(request)

        # # 提取Authorization头
        # auth_header = request.headers.get("Authorization")
        # if not auth_header or not auth_header.startswith("Bearer "):
        #     return JSONResponse(
        #         status_code=status.HTTP_401_UNAUTHORIZED,
        #         content={"detail": f"请先登录。Path: {path}"},
        #         headers={"WWW-Authenticate": "Bearer"}
        #     )

        # # 获取token
        # token = auth_header.split("Bearer ")[1]

        # # 添加token到请求状态，后续路由可以直接使用
        # request.state.token = token

        # 继续处理请求
        return await call_next(request)

# 添加鉴权中间件
app.add_middleware(AuthMiddleware)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5050, threads=10, workers=10, reload=True)

