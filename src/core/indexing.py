import os
from pathlib import Path
from llama_index.core.node_parser import SimpleFileNodeParser
from llama_index.readers.file import FlatReader

from src.utils import hashstr

def chunk_text(text, params=None):
    params = params or {}
    from llama_index.core import Document
    from llama_index.core.node_parser import SentenceSplitter
    chunk_size = int(params.get("chunk_size", 500))
    chunk_overlap = int(params.get("chunk_overlap", 20))
    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    doc = Document(id_=hashstr(text), text=text)
    nodes = splitter.get_nodes_from_documents([doc])
    return nodes

def chunk_file(file, params=None):
    parser = SimpleFileNodeParser()
    if file.endswith(".txt"):
        from llama_index.readers.file import FlatReader
        docs = FlatReader().load_data(Path(file))
    elif file.endswith(".docx"):
        from llama_index.readers.file import DocxReader
        docs = DocxReader().load_data(Path(file))
    elif file.endswith(".md"):
        from llama_index.readers.file import MarkdownReader
        docs = MarkdownReader().load_data(Path(file))
    else:
        raise ValueError("Unsupported file type")

    nodes = parser.get_nodes_from_documents(docs)
    return nodes  # 返回节点