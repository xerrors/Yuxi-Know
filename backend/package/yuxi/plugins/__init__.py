# 新的统一文档处理器接口
from yuxi.plugins.document_processor_factory import DocumentProcessorFactory
from yuxi.plugins.mineru_official_parser import MinerUOfficialParser
from yuxi.plugins.mineru_parser import MinerUParser
from yuxi.plugins.paddlex_parser import PaddleXDocumentParser
from yuxi.plugins.rapid_ocr_processor import RapidOCRProcessor

__all__ = [
    "DocumentProcessorFactory",  # 推荐使用
    "RapidOCRProcessor",
    "MinerUParser",
    "MinerUOfficialParser",
    "PaddleXDocumentParser",
]
