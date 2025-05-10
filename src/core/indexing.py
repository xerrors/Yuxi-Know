import os
import asyncio
from pathlib import Path
from llama_index.core import Document
from llama_index.core.node_parser import SimpleFileNodeParser
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import FlatReader, DocxReader

from src.utils import hashstr, logger


def chunk(text_or_path, params=None):
    """
    将文本或文件切分成固定大小的块

    Args:
        text_or_path: 文本或文件路径
        params: 参数
            chunk_size: 块大小
            chunk_overlap: 块重叠大小
            use_parser: 是否使用文件解析器
    Returns:
        nodes: 节点列表
    """
    params = params or {}
    chunk_size = int(params.get("chunk_size", 500))
    chunk_overlap = int(params.get("chunk_overlap", 100))
    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    # 如果文件存在，并且是当前目录下的文件，则使用文件解析器
    if os.path.isfile(text_or_path) and os.path.exists(text_or_path) and os.path.abspath(text_or_path).startswith(os.getcwd()):
        parser = SimpleFileNodeParser()
        file_type = Path(text_or_path).suffix.lower()
        if file_type in [".txt", ".json", ".md"]:
            docs = FlatReader().load_data(Path(text_or_path))
        elif file_type in [".docx"]:
            docs = DocxReader().load_data(Path(text_or_path))
        else:
            raise ValueError(f"Unsupported file type `{file_type}`")

        if params.get("use_parser"):
            nodes = parser.get_nodes_from_documents(docs)
        else:
            nodes = splitter.get_nodes_from_documents(docs)

    else:
        docs = [Document(id_=hashstr(text_or_path), text=text_or_path)]
        nodes = splitter.get_nodes_from_documents(docs)

    return nodes



def pdfreader(file_path):
    """读取PDF文件并返回text文本"""
    assert os.path.exists(file_path), "File not found"
    assert file_path.endswith(".pdf"), "File format not supported"

    from llama_index.readers.file import PDFReader
    doc = PDFReader().load_data(file=Path(file_path))

    # 简单的拼接起来之后返回纯文本
    text = "\n\n".join([d.get_content() for d in doc])
    return text

def plainreader(file_path):
    """读取普通文本文件并返回text文本"""
    assert os.path.exists(file_path), "File not found"

    with open(file_path, "r") as f:
        text = f.read()
    return text

def read_text(file, params=None):
    support_format = [".pdf", ".txt", ".md"]
    assert os.path.exists(file), "File not found"
    logger.info(f"Try to read file {file}")

    if not os.path.isfile(file):
        logger.error(f"Directory not supported now!")
        raise NotImplementedError("Directory not supported now!")

    if file.endswith(".pdf"):
        from src.plugins import ocr
        return ocr.process_pdf(file)

    elif file.endswith(".txt") or file.endswith(".md"):
        return plainreader(file)

    else:
        logger.error(f"File format not supported, only support {support_format}")
        raise Exception(f"File format not supported, only support {support_format}")


async def read_text_async(file):
    return await asyncio.to_thread(read_text, file)
