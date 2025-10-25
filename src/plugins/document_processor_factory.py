"""
文档处理器工厂

提供统一的文档处理器创建和管理接口
"""

from typing import Any

from src.plugins.document_processor_base import BaseDocumentProcessor
from src.plugins.mineru_official_parser import MinerUOfficialParser
from src.plugins.mineru_parser import MinerUParser
from src.plugins.paddlex_parser import PaddleXDocumentParser
from src.plugins.rapid_ocr_processor import RapidOCRProcessor
from src.utils import logger

# 处理器实例缓存
_PROCESSOR_CACHE: dict[str, BaseDocumentProcessor] = {}


class DocumentProcessorFactory:
    """文档处理器工厂"""

    # 处理器类型映射
    PROCESSOR_TYPES = {
        "onnx_rapid_ocr": RapidOCRProcessor,
        "mineru_ocr": MinerUParser,
        "mineru_official": MinerUOfficialParser,
        "paddlex_ocr": PaddleXDocumentParser,
    }

    @classmethod
    def get_processor(cls, processor_type: str, **kwargs) -> BaseDocumentProcessor:
        """
        获取文档处理器实例 (单例模式)

        Args:
            processor_type: 处理器类型
                - "onnx_rapid_ocr": RapidOCR 本地 OCR
                - "mineru_ocr": MinerU HTTP API 文档解析
                - "mineru_official": MinerU 官方云服务 API 文档解析
                - "paddlex_ocr": PaddleX 版面解析
            **kwargs: 处理器初始化参数

        Returns:
            BaseDocumentProcessor: 处理器实例

        Raises:
            ValueError: 不支持的处理器类型
        """
        if processor_type not in cls.PROCESSOR_TYPES:
            raise ValueError(f"不支持的处理器类型: {processor_type}. 支持的类型: {list(cls.PROCESSOR_TYPES.keys())}")

        # 使用缓存避免重复创建
        cache_key = f"{processor_type}_{hash(frozenset(kwargs.items()))}"
        if cache_key not in _PROCESSOR_CACHE:
            processor_class = cls.PROCESSOR_TYPES[processor_type]
            _PROCESSOR_CACHE[cache_key] = processor_class(**kwargs)
            logger.debug(f"创建文档处理器: {processor_type}")

        return _PROCESSOR_CACHE[cache_key]

    @classmethod
    def process_file(cls, processor_type: str, file_path: str, params: dict | None = None) -> str:
        """
        使用指定处理器处理文件 (便捷方法)

        Args:
            processor_type: 处理器类型
            file_path: 文件路径
            params: 处理参数

        Returns:
            str: 提取的文本

        Raises:
            DocumentProcessorException: 处理失败
        """
        processor = cls.get_processor(processor_type)
        return processor.process_file(file_path, params)

    @classmethod
    def check_health(cls, processor_type: str) -> dict[str, Any]:
        """
        检查指定处理器的健康状态

        Args:
            processor_type: 处理器类型

        Returns:
            dict: 健康状态信息
        """
        try:
            processor = cls.get_processor(processor_type)
            return processor.check_health()
        except Exception as e:
            return {
                "status": "error",
                "message": f"健康检查失败: {str(e)}",
                "details": {"error": str(e)},
            }

    @classmethod
    def check_all_health(cls) -> dict[str, dict[str, Any]]:
        """
        检查所有处理器的健康状态

        Returns:
            dict: 各处理器的健康状态
        """
        health_status = {}
        for processor_type in cls.PROCESSOR_TYPES:
            health_status[processor_type] = cls.check_health(processor_type)
        return health_status

    @classmethod
    def get_available_processors(cls) -> list[str]:
        """返回所有可用的处理器类型"""
        return list(cls.PROCESSOR_TYPES.keys())

    @classmethod
    def clear_cache(cls):
        """清除处理器缓存"""
        _PROCESSOR_CACHE.clear()
        logger.debug("文档处理器缓存已清除")
