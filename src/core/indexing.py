import os
from pathlib import Path
from llama_index.core import Document
from llama_index.core.node_parser import SimpleFileNodeParser
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import FlatReader, DocxReader

from src.utils import hashstr

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

    if os.path.isfile(text_or_path) and "uploads" in text_or_path:
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
