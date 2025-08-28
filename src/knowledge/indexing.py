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
    if isinstance(file_path, str):
        file_path = Path(file_path)

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
            return ocr.process_pdf(file, params=params)

        elif opt_ocr == "mineru_ocr":
            from src.plugins import ocr
            return ocr.process_file_mineru(file, params=params)

        elif opt_ocr == "paddlex_ocr":
            from src.plugins import ocr
            return ocr.process_file_paddlex(file, params=params)

        else:
            raise ValueError(f"不支持的OCR方式: {opt_ocr}")

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


def parse_image(file, params=None):
    """
    解析图像文件，支持多种OCR方式
    """
    from src.plugins._ocr import OCRServiceException

    params = params or {}
    opt_ocr = params.get("enable_ocr", "disable")

    if opt_ocr == "disable":
        logger.warning(f"OCR is disabled for image file: {file}, Using `onnx_rapid_ocr` instead")
        opt_ocr = "onnx_rapid_ocr"

    try:
        if opt_ocr == "onnx_rapid_ocr":
            from src.plugins import ocr
            return ocr.process_image(file, params=params)

        elif opt_ocr == "mineru_ocr":
            from src.plugins import ocr
            return ocr.process_file_mineru(file, params=params)

        elif opt_ocr == "paddlex_ocr":
            from src.plugins import ocr
            return ocr.process_file_paddlex(file, params=params)

        else:
            raise ValueError(f"不支持的OCR方式: {opt_ocr}")

    except OCRServiceException as e:
        logger.error(f"OCR service failed: {e.service_name} - {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Image parsing failed: {str(e)}")
        raise OCRServiceException(
            f"Image解析失败: {str(e)}",
            opt_ocr,
            "parsing_failed"
        )

async def parse_pdf_async(file, params=None):
    return await asyncio.to_thread(parse_pdf, file, params=params)

async def parse_image_async(file, params=None):
    return await asyncio.to_thread(parse_image, file, params=params)

async def process_file_to_markdown(file_path: str, params: dict | None = None) -> str:
    """
    将不同类型的文件转换为markdown格式

    Args:
        file_path: 文件路径
        params: 处理参数

    Returns:
        markdown格式内容
    """
    file_path_obj = Path(file_path)
    file_ext = file_path_obj.suffix.lower()

    if file_ext == '.pdf':
        # 使用 OCR 处理 PDF
        text = await parse_pdf_async(str(file_path_obj), params=params)
        return f"# {file_path_obj.name}\n\n{text}"

    elif file_ext in ['.txt', '.md']:
        # 直接读取文本文件
        with open(file_path_obj, encoding='utf-8') as f:
            content = f.read()
        return f"# {file_path_obj.name}\n\n{content}"

    elif file_ext in ['.doc', '.docx']:
        # 处理 Word 文档
        from docx import Document  # type: ignore
        doc = Document(file_path_obj)
        text = '\n'.join([para.text for para in doc.paragraphs])
        return f"# {file_path_obj.name}\n\n{text}"

    elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
        # 使用 OCR 处理图片
        text = await parse_image_async(str(file_path_obj), params=params)
        return f"# {file_path_obj.name}\n\n{text}"

    elif file_ext in ['.html', '.htm']:
        # 使用 BeautifulSoup 处理 HTML 文件
        from markdownify import markdownify as md
        with open(file_path_obj, encoding='utf-8') as f:
            content = f.read()
        text = md(content, heading_style="ATX")
        return f"# {file_path_obj.name}\n\n{text}"

    elif file_ext == '.csv':
        # 处理 CSV 文件
        import pandas as pd
        df = pd.read_csv(file_path_obj)
        # 将每一行数据与表头组合成独立的表格
        markdown_content = f"# {file_path_obj.name}\n\n"

        for index, row in df.iterrows():
            # 创建包含表头和当前行的小表格
            row_df = pd.DataFrame([row], columns=df.columns)
            markdown_table = row_df.to_markdown(index=False)
            markdown_content += f"{markdown_table}\n\n"

        return markdown_content.strip()

    elif file_ext in ['.xls', '.xlsx']:
        # 处理 Excel 文件
        import pandas as pd
        # 读取所有工作表
        excel_file = pd.ExcelFile(file_path_obj)
        markdown_content = f"# {file_path_obj.name}\n\n"

        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(file_path_obj, sheet_name=sheet_name)
            markdown_content += f"## {sheet_name}\n\n"

            # 将每一行数据与表头组合成独立的表格
            for index, row in df.iterrows():
                # 创建包含表头和当前行的小表格
                row_df = pd.DataFrame([row], columns=df.columns)
                markdown_table = row_df.to_markdown(index=False)
                markdown_content += f"{markdown_table}\n\n"

        return markdown_content.strip()

    elif file_ext == '.json':
        # 处理 JSON 文件
        import json
        with open(file_path_obj, encoding='utf-8') as f:
            data = json.load(f)
        # 将 JSON 数据格式化为 markdown 代码块
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        return f"# {file_path_obj.name}\n\n```json\n{json_str}\n```"

    else:
        # 尝试作为文本文件读取
        raise ValueError(f"Unsupported file type: {file_ext}")

async def process_url_to_markdown(url: str, params: dict | None = None) -> str:
    """
    将URL转换为markdown格式

    Args:
        url: URL地址
        params: 处理参数

    Returns:
        markdown格式内容
    """
    import requests
    from bs4 import BeautifulSoup

    try:
        response = requests.get(url, timeout=30)
        soup = BeautifulSoup(response.content, 'html.parser')
        text_content = soup.get_text()
        return f"# {url}\n\n{text_content}"
    except Exception as e:
        logger.error(f"Failed to process URL {url}: {e}")
        return f"# {url}\n\nFailed to process URL: {e}"

