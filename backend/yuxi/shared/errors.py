"""供领域用例与非 HTTP 调用方共享的失败契约。"""


class DomainError(Exception):
    """保存业务消息及可选业务标识，由入口选择协议表达。"""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class InvalidOperationError(DomainError):
    """请求的操作不适用于当前对象或内容。"""


class PermissionDeniedError(DomainError):
    """当前身份无权访问或修改目标。"""


class ResourceNotFoundError(DomainError):
    """目标不存在或不在当前可见范围。"""


class StateConflictError(DomainError):
    """当前状态或既有意图与请求冲突。"""


class ContentTooLargeError(DomainError):
    """内容超过当前操作的处理预算。"""


class InvalidInputError(DomainError):
    """输入字段不满足用例约束。"""


class OperationFailedError(DomainError):
    """领域操作未能产生有效结果。"""


class UpstreamError(DomainError):
    """上游调用失败或返回无效结果。"""


class OperationTimeoutError(DomainError):
    """操作未能在允许时间内完成。"""
