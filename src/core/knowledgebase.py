import os

from src.models.embedding import EmbeddingModel
from pymilvus import MilvusClient
from src.utils import setup_logger, hashstr
logger = setup_logger("KnowledgeBase")


class KnowledgeBase:

    def __init__(self, config=None, embed_model=None) -> None:
        self.config = config
        self._init_config(config)

        assert embed_model, "embed_model=None"
        self.embed_model = embed_model

        self.client = MilvusClient(self.milvus_path)

    def _init_config(self, config):
        self.vector_dim = 1024  # 暂时不知道这个和 embedding model 的 embedding 大小有什么关系
        self.milvus_path = os.path.join(config.save_dir, "data/vector_base/milvus.db")
        os.makedirs(os.path.dirname(self.milvus_path), exist_ok=True)

    def get_collection_names(self):
        return self.client.list_collections()

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

    def add_documents(self, docs, collection_name, **kwargs):
        """添加已经分块之后的文本"""
        # 检查 collection 是否存在
        import random
        if not self.client.has_collection(collection_name=collection_name):
            logger.warning(f"Collection {collection_name} not found, create it")
            self.add_collection(collection_name)

        vectors = self.embed_model.encode(docs)

        data = [{
            "id": int(random.random() * 1e12),
            "vector": vectors[i],
            "text": docs[i],
            "hash": hashstr(docs[i] + str(random.random())),
            **kwargs} for i in range(len(vectors))]

        res = self.client.insert(collection_name=collection_name, data=data)
        return res

    def search(self, query, collection_name, limit=3):

        query_vectors = self.embed_model.encode_queries([query])
        return self.search_by_vector(query_vectors[0], collection_name, limit)

    def search_by_vector(self, vector, collection_name, limit=3):
        res = self.client.search(
            collection_name=collection_name,  # target collection
            data=[vector],  # query vectors
            limit=limit,  # number of returned entities
            output_fields=["text", "file_id"],  # specifies fields to be returned
        )

        return res[0]

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
