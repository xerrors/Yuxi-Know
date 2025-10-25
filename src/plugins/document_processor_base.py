"""
文档处理器基础接口和异常定义

这个模块定义了统一的文档处理器接口,用于OCR和文档解析服务。
"""

from abc import ABC, abstractmethod
from typing import Any


class DocumentProcessorException(Exception):
    """文档处理异常基类"""

    def __init__(self, message: str, service_name: str = None, status_code: str = None):
        super().__init__(message)
        self.message = message
        self.service_name = service_name
        self.status_code = status_code

    def __str__(self):
        if self.service_name:
            return f"[{self.service_name}] {self.message}"
        return self.message


class OCRException(DocumentProcessorException):
    """OCR处理异常"""

    pass


class DocumentParserException(DocumentProcessorException):
    """文档解析异常"""

    pass


class ServiceHealthCheckException(DocumentProcessorException):
    """服务健康检查异常"""

    pass


class BaseDocumentProcessor(ABC):
    """文档处理器基类"""

    @abstractmethod
    def process_file(self, file_path: str, params: dict[str, Any] | None = None) -> str:
        """
        处理文件并返回提取的文本

        Args:
            file_path: 文件路径
            params: 处理参数

        Returns:
            str: 提取的文本内容

        Raises:
            DocumentProcessorException: 处理失败时抛出
        """
        pass

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        """
        检查服务健康状态

        Returns:
            dict: 健康状态信息
                {
                    "status": "healthy" | "unhealthy" | "unavailable" | "error",
                    "message": "状态描述",
                    "details": {...}  # 可选的详细信息
                }
        """
        pass

    @abstractmethod
    def get_service_name(self) -> str:
        """返回服务名称"""
        pass

    def supports_file_type(self, file_extension: str) -> bool:
        """
        检查是否支持指定的文件类型

        Args:
            file_extension: 文件扩展名 (包含点, 如 '.pdf')

        Returns:
            bool: 是否支持
        """
        return file_extension.lower() in self.get_supported_extensions()

    @abstractmethod
    def get_supported_extensions(self) -> list[str]:
        """返回支持的文件扩展名列表"""
        pass
