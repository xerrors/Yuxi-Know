import os

from pathlib import Path

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

