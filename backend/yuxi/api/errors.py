"""将已知领域失败适配为现有 HTTP 错误响应。"""

from fastapi import Request
from fastapi.responses import JSONResponse

from yuxi.shared.errors import (
    ContentTooLargeError,
    DomainError,
    InvalidInputError,
    InvalidOperationError,
    OperationFailedError,
    OperationTimeoutError,
    PermissionDeniedError,
    ResourceNotFoundError,
    StateConflictError,
    UpstreamError,
)

_DOMAIN_HTTP_STATUS = {
    InvalidOperationError: 400,
    PermissionDeniedError: 403,
    ResourceNotFoundError: 404,
    StateConflictError: 409,
    ContentTooLargeError: 413,
    InvalidInputError: 422,
    OperationFailedError: 500,
    UpstreamError: 502,
    OperationTimeoutError: 504,
}


async def domain_error_handler(_request: Request, error: DomainError) -> JSONResponse:
    """保留公开状态与正文，领域异常本身不携带 HTTP 属性。"""
    status_code = next((status for error_type, status in _DOMAIN_HTTP_STATUS.items() if isinstance(error, error_type)), 500)
    detail = error.message if error.code is None else {"code": error.code, "message": error.message}
    return JSONResponse(status_code=status_code, content={"detail": detail})
