# Read Chunking Embedding and save it to Vector Database
import os

from pathlib import Path
from llama_index.readers.file import PDFReader

from models.embedding import EmbeddingModel
from utils.logging_config import setup_logger

from pymilvus import MilvusClient


logger = setup_logger("PreRetrival")

def pdfreader(file_path):
    """读取PDF文件并返回text文本"""
    assert os.path.exists(file_path), "File not found"
    assert file_path.endswith(".pdf"), "File format not supported"

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


class PreRetrival:

    def __init__(self, config):
        self.config = config
        self._init_config(config)

        self.embed_model = EmbeddingModel(config)
        self.client = MilvusClient(config.milvus_local_path)

    def _init_config(self, config):
        self.vector_dim = 1024  # 暂时不知道这个和 embedding model 的 embedding 大小有什么关系
        self.default_query_limit = 2
        self.default_collection_name = "default"

    def add_file(self, file, collection_name=None):
        """添加文件到数据库"""
        collection_name = collection_name or self.default_collection_name
        text = self.read_text(file)
        chunks = self.chunking(text)

        self.add_documents(chunks, collection_name)

    def add_documents(self, docs, collection_name):
        """添加已经分块之后的文本"""
        vectors = self.embed_model.encode(docs)

        data = [
            {"id": i, "vector": vectors[i], "text": docs[i], "subject": "history"}
            for i in range(len(vectors))
        ]

        # for testing, we drop the collection if it already exists
        # if self.client.has_collection(collection_name=collection_name):
        #     self.client.drop_collection(collection_name=collection_name)

        self.client.create_collection(
            collection_name=collection_name,
            dimension=self.vector_dim,  # The vectors we will use in this demo has 768 dimensions
        )

        res = self.client.insert(collection_name=collection_name, data=data)
        return res

    def search(self, query, collection_name=None, limit=None):
        collection_name = collection_name or self.default_collection_name
        limit = limit or self.default_query_limit

        query_vectors = self.embed_model.encode_queries([query])

        res = self.client.search(
            collection_name=collection_name,  # target collection
            data=query_vectors,  # query vectors
            limit=limit,  # number of returned entities
            output_fields=["text", "subject"],  # specifies fields to be returned
        )

        return res

    def read_text(self, file):
        support_format = [".pdf", ".txt", "*.md"]
        assert os.path.exists(file), "File not found"
        logger.info(f"Try to read file {file}")
        if os.path.isfile(file):
            if file.endswith(".pdf"):
                return pdfreader(file)
            elif file.endswith(".txt") or file.endswith(".md"):
                return plainreader(file)
            else:
                logger.error(f"File format not supported, only support {support_format}")
                raise Exception(f"File format not supported, only support {support_format}")
        else:
            logger.error(f"Directory not supported now!")
            raise NotImplementedError("Directory not supported now!")

    def chunking(self, text, chunk_size=1024):
        """将文本切分成固定大小的块"""
        chunks = []
        for i in range(0, len(text), chunk_size):
            chunks.append(text[i:i + chunk_size])
        return chunks