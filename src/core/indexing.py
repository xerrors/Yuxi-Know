import os
import asyncio
from pathlib import Path
from langchain.schema.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    Docx2txtLoader,
    UnstructuredMarkdownLoader,
    UnstructuredHTMLLoader,
    CSVLoader,
    JSONLoader
)

from src.utils import hashstr, logger


def chunk_with_parser(file_path, params=None):
    """
    使用文件解析器将文件切分成固定大小的块

    Args:
        file_path: 文件路径
        params: 参数
    """
    params = params or {}
    chunk_size = int(params.get("chunk_size", 500))
    chunk_overlap = int(params.get("chunk_overlap", 100))

    file_type = Path(file_path).suffix.lower()

    # 选择合适的加载器
    if file_type in ['.txt']:
        loader = TextLoader(file_path)

    elif file_type in ['.md']:
        loader = UnstructuredMarkdownLoader(file_path)

    elif file_type in ['.docx', '.doc']:
        loader = Docx2txtLoader(file_path)

    elif file_type in ['.html', '.htm']:
        loader = UnstructuredHTMLLoader(file_path)

    elif file_type in ['.json']:
        loader = JSONLoader(file_path, jq_schema=".")

    elif file_type in ['.csv']:
        loader = CSVLoader(file_path)

    else:
        raise ValueError(f"不支持的文件类型: {file_type}")

    # 加载文档
    docs = loader.load()

    # 创建文本分割器
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    # 分割文档
    nodes = text_splitter.split_documents(docs)

    # 添加序号信息到metadata
    for i, node in enumerate(nodes):
        if node.metadata is None:
            node.metadata = {}
        node.metadata["chunk_idx"] = i

    return nodes

def chunk_text(text, params=None):
    """
    将文本切分成固定大小的块
    """
    params = params or {}
    chunk_size = int(params.get("chunk_size", 500))
    chunk_overlap = int(params.get("chunk_overlap", 100))

    # 创建文本分割器
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""]
    )

    # 分割文档
    nodes = text_splitter.split_text(text)

    # 添加序号信息到metadata
    nodes = [{"text": node, "metadata": {"chunk_idx": i}} for i, node in enumerate(nodes)]
    return nodes

def chunk(text_or_path, params=None):
    raise NotImplementedError("chunk is deprecated, use chunk_with_parser or chunk_text instead")

def pdfreader(file_path, params=None):
    """读取PDF文件并返回text文本"""
    assert file_path.exists(), "File not found"
    assert file_path.suffix.lower() == ".pdf", "File format not supported"

    # 使用LangChain的PDF加载器
    loader = PyPDFLoader(str(file_path))
    docs = loader.load()

    # 简单的拼接起来之后返回纯文本
    text = "\n\n".join([d.page_content for d in docs])
    return text

def plainreader(file_path):
    """读取普通文本文件并返回text文本"""
    assert os.path.exists(file_path), "File not found"

    # 使用LangChain的文本加载器
    loader = TextLoader(str(file_path))
    docs = loader.load()
    text = "\n\n".join([d.page_content for d in docs])
    return text

def parse_pdf(file, params=None):
    """
    解析PDF文件，支持多种OCR方式

    Args:
        file: PDF文件路径
        params: 参数字典，包含enable_ocr设置

    Returns:
        str: 解析得到的文本

    Raises:
        OCRServiceException: OCR服务不可用时抛出
    """
    from src.plugins._ocr import OCRServiceException

    params = params or {}
    opt_ocr = params.get("enable_ocr", "disable")

    if opt_ocr == "disable":
        return pdfreader(file, params=params)

    try:
        if opt_ocr == "onnx_rapid_ocr":
            from src.plugins import ocr
            return ocr.process_pdf(file)

        elif opt_ocr == "mineru_ocr":
            from src.plugins import ocr
            return ocr.process_pdf_mineru(file)

        elif opt_ocr == "paddlex_ocr":
            from src.plugins import ocr
            return ocr.process_pdf_paddlex(file)

        else:
            return pdfreader(file, params=params)

    except OCRServiceException as e:
        logger.error(f"OCR service failed: {e.service_name} - {str(e)}")
        raise
    except Exception as e:
        logger.error(f"PDF parsing failed: {str(e)}")
        raise OCRServiceException(
            f"PDF解析失败: {str(e)}",
            opt_ocr,
            "parsing_failed"
        )

async def parse_pdf_async(file, params=None):
    return await asyncio.to_thread(parse_pdf, file, params=params)
