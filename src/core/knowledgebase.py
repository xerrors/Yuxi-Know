import os

from models.embedding import EmbeddingModel
from pymilvus import MilvusClient
from utils import setup_logger, hashstr
from core.filereader import pdfreader, plainreader

logger = setup_logger("KnowledgeBase")


class KnowledgeBase:

    def __init__(self, config=None) -> None:
        self.config = config
        self._init_config(config)

        self.embed_model = EmbeddingModel(config)
        self.client = MilvusClient(config.milvus_local_path)

    def _init_config(self, config):
        self.vector_dim = 1024  # 暂时不知道这个和 embedding model 的 embedding 大小有什么关系

    def get_collections(self):
        collections_name = self.client.list_collections()
        collections = []
        for collection_name in collections_name:
            collection = self.get_collection_info(collection_name)
            collections.append(collection)

        return collections

    def get_collection_info(self, collection_name):
        collection = self.client.describe_collection(collection_name)
        collection.update(self.client.get_collection_stats(collection_name))
        # collection["id"] = hashstr(collection_name)
        return collection

    def add_collection(self, collection_name):
        if self.client.has_collection(collection_name=collection_name):
            logger.warning(f"Collection {collection_name} already exists, drop it")
            self.client.drop_collection(collection_name=collection_name)

        self.client.create_collection(
            collection_name=collection_name,
            dimension=self.vector_dim,  # The vectors we will use in this demo has 768 dimensions
        )

    def add_file(self, file, collection_name):
        """添加文件到数据库"""

        # 检查 collection 是否存在
        if not self.client.has_collection(collection_name=collection_name):
            logger.warning(f"Collection {collection_name} not found, create it")
            self.add_collection(collection_name)

        text = self.read_text(file)
        chunks = self.chunking(text)

        self.add_documents(chunks, collection_name, filename=file)

    def add_text(self, text, collection_name):
        """添加文本到数据库"""
        chunks = self.chunking(text)
        self.add_documents(chunks, collection_name)

    def add_documents(self, docs, collection_name, filename=None):
        """添加已经分块之后的文本"""
        vectors = self.embed_model.encode(docs)

        data = [
            {"id": i, "vector": vectors[i], "text": docs[i], "filename": filename}
            for i in range(len(vectors))
        ]

        res = self.client.insert(collection_name=collection_name, data=data)
        return res

    def search(self, query, collection_name, limit=None):
        limit = limit or self.default_query_limit

        query_vectors = self.embed_model.encode_queries([query])

        res = self.client.search(
            collection_name=collection_name,  # target collection
            data=query_vectors,  # query vectors
            limit=limit,  # number of returned entities
            output_fields=["text", "subject"],  # specifies fields to be returned
        )

        return res[0]  # 因为 query 只有一个

    def examples(self, collection_name, limit=20):
        res = self.client.query(
            collection_name=collection_name,
            limit=10,
            output_fields=["id", "text"],
        )
        return res

    def search_by_id(self, collection_name, id, output_fields=["id", "text"]):
        res = self.client.get(collection_name, id, output_fields=output_fields)
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
