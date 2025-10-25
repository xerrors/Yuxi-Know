# 新的统一文档处理器接口
from src.plugins.document_processor_factory import DocumentProcessorFactory
from src.plugins.mineru_official_parser import MinerUOfficialParser
from src.plugins.mineru_parser import MinerUParser
from src.plugins.paddlex_parser import PaddleXDocumentParser
from src.plugins.rapid_ocr_processor import RapidOCRProcessor

__all__ = [
    "DocumentProcessorFactory",  # 推荐使用
    "RapidOCRProcessor",
    "MinerUParser",
    "MinerUOfficialParser",
    "PaddleXDocumentParser",
]
