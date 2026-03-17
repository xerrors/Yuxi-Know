"""访问日志中间件 - 记录请求处理时间"""

import time
import logging
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# 创建专用的访问日志记录器
access_logger = logging.getLogger("access_logger")

# 设置访问日志记录器
if not access_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(fmt="%(asctime)s %(levelname)s: %(message)s", datefmt="%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    access_logger.addHandler(handler)
    access_logger.setLevel(logging.INFO)
    # 避免传播到根日志记录器，防止重复日志
    access_logger.propagate = False


def _extract_client_ip(request: Request) -> str:
    """提取客户端IP地址"""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class AccessLogMiddleware(BaseHTTPMiddleware):
    """访问日志中间件 - 记录请求处理时间"""

    def __init__(self, app, logger: logging.Logger = None):
        super().__init__(app)
        self.logger = logger or access_logger

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理请求并记录访问日志"""
        # 记录请求开始时间
        start_time = time.perf_counter()

        # 获取客户端IP
        client_ip = _extract_client_ip(request)

        # 处理请求
        response = await call_next(request)

        # 计算处理时间
        process_time = time.perf_counter() - start_time
        process_time_ms = int(process_time * 1000)  # 转换为毫秒

        # 格式化日志消息，添加处理时间
        log_message = (
            f"{client_ip}:{request.client.port if request.client else 'unknown'} - "
            f'"{request.method} {request.url.path}{"?" + request.url.query if request.url.query else ""} '
            f'HTTP/{request.scope["http_version"]}" '
            f"{response.status_code} - {process_time_ms}ms"
        )

        # 记录日志
        self.logger.info(log_message)

        return response
