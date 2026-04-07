from pymilvus import CollectionSchema, DataType, FieldSchema, Function, FunctionType

from yuxi.knowledge.implementations.milvus import CONTENT_ANALYZER_PARAMS, CONTENT_SPARSE_FIELD, MilvusKB


class FakeHit:
    def __init__(self, content: str, distance: float):
        self.distance = distance
        self.entity = {
            "content": content,
            "source": "demo.md",
            "chunk_id": "chunk-1",
            "file_id": "file-1",
            "chunk_index": 0,
        }


class FakeCollection:
    def __init__(self, distance: float = 0.8):
        self.search_calls = []
        self.hybrid_calls = []
        self.distance = distance

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return [[FakeHit("BM25 result", self.distance)]]

    def hybrid_search(self, **kwargs):
        self.hybrid_calls.append(kwargs)
        return [[FakeHit("Hybrid result", self.distance)]]


def make_kb(collection: FakeCollection) -> MilvusKB:
    kb = MilvusKB.__new__(MilvusKB)
    kb.databases_meta = {"db": {"embed_info": {}}}
    kb._get_query_params = lambda db_id: {}
    kb._get_embedding_function = lambda embed_info: lambda texts: [[0.1, 0.2] for _ in texts]

    async def get_collection(db_id: str):
        return collection

    kb._get_milvus_collection = get_collection
    return kb


async def test_keyword_mode_uses_milvus_bm25_search():
    collection = FakeCollection()
    kb = make_kb(collection)

    chunks = await kb.aquery(
        "alpha beta",
        "db",
        search_mode="keyword",
        bm25_top_k=7,
        bm25_drop_ratio_search=0.2,
    )

    assert chunks[0]["content"] == "BM25 result"
    assert chunks[0]["bm25_score"] == 0.8
    search_call = collection.search_calls[0]
    assert search_call["data"] == ["alpha beta"]
    assert search_call["anns_field"] == CONTENT_SPARSE_FIELD
    assert search_call["param"] == {
        "metric_type": "BM25",
        "params": {"drop_ratio_search": 0.2},
    }
    assert search_call["limit"] == 7


async def test_hybrid_mode_uses_milvus_native_hybrid_search():
    collection = FakeCollection()
    kb = make_kb(collection)

    chunks = await kb.aquery(
        "hybrid query",
        "db",
        search_mode="hybrid",
        final_top_k=3,
        bm25_top_k=8,
        vector_weight=0.6,
        bm25_weight=0.4,
    )

    assert chunks[0]["content"] == "Hybrid result"
    assert chunks[0]["hybrid_score"] == 0.8
    hybrid_call = collection.hybrid_calls[0]
    assert hybrid_call["limit"] == 3
    assert hybrid_call["rerank"]._weights == [0.6, 0.4]

    vector_request, bm25_request = hybrid_call["reqs"]
    assert vector_request.anns_field == "embedding"
    assert vector_request.data == [[0.1, 0.2]]
    assert bm25_request.anns_field == CONTENT_SPARSE_FIELD
    assert bm25_request.data == ["hybrid query"]
    assert bm25_request.limit == 8
    assert bm25_request.param["metric_type"] == "BM25"


async def test_hybrid_mode_filters_scores_below_similarity_threshold():
    collection = FakeCollection(distance=0.1)
    kb = make_kb(collection)

    chunks = await kb.aquery(
        "hybrid query",
        "db",
        search_mode="hybrid",
        final_top_k=3,
        similarity_threshold=0.2,
    )

    assert chunks == []


def test_query_params_config_uses_bm25_parameters():
    kb = MilvusKB.__new__(MilvusKB)

    config = kb.get_query_params_config("db")

    option_keys = {option["key"] for option in config["options"]}
    assert "keyword_top_k" not in option_keys
    assert {
        "bm25_top_k",
        "vector_weight",
        "bm25_weight",
        "bm25_drop_ratio_search",
    } <= option_keys

    search_mode = next(option for option in config["options"] if option["key"] == "search_mode")
    descriptions = {option["value"]: option["description"] for option in search_mode["options"]}
    assert "BM25" in descriptions["keyword"]
    assert "BM25" in descriptions["hybrid"]


def test_collection_supports_bm25_requires_analyzed_content_sparse_field_and_function():
    kb = MilvusKB.__new__(MilvusKB)
    schema = CollectionSchema(
        fields=[
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
            FieldSchema(
                name="content",
                dtype=DataType.VARCHAR,
                max_length=65535,
                enable_analyzer=True,
                analyzer_params=CONTENT_ANALYZER_PARAMS,
            ),
            FieldSchema(name=CONTENT_SPARSE_FIELD, dtype=DataType.SPARSE_FLOAT_VECTOR),
        ],
        functions=[
            Function(
                name="content_bm25",
                input_field_names=["content"],
                output_field_names=[CONTENT_SPARSE_FIELD],
                function_type=FunctionType.BM25,
            )
        ],
    )

    collection = type("Collection", (), {"schema": schema})()

    assert kb._collection_supports_bm25(collection)
