"""文档与图谱的 Milvus 公共装配契约。"""

from functools import partial

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, Function, FunctionType

from yuxi.modules.models.embed import select_embedding_model

CONTENT_SPARSE_FIELD = "content_sparse"
CONTENT_ANALYZER_PARAMS = {"type": "chinese"}
VECTOR_METRIC_TYPE = "COSINE"


def content_fields():
    """共享主键和中文可检索正文；字段顺序属于持久化契约。"""
    return [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
        FieldSchema(
            name="content",
            dtype=DataType.VARCHAR,
            max_length=65535,
            enable_analyzer=True,
            enable_match=True,
            analyzer_params=CONTENT_ANALYZER_PARAMS,
        ),
    ]


def embedding_field(dimension: int):
    """创建稠密向量字段。"""
    return FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension)


def create_collection(name: str, *, fields: list, description: str, using: str):
    """统一 BM25 函数与稠密、稀疏索引，保留调用方字段顺序。"""
    schema = CollectionSchema(
        fields=[*fields, FieldSchema(name=CONTENT_SPARSE_FIELD, dtype=DataType.SPARSE_FLOAT_VECTOR)],
        description=description,
        functions=[
            Function(
                name="content_bm25",
                input_field_names=["content"],
                output_field_names=[CONTENT_SPARSE_FIELD],
                function_type=FunctionType.BM25,
            )
        ],
    )
    collection = Collection(name=name, schema=schema, using=using)
    collection.create_index("embedding", {"metric_type": VECTOR_METRIC_TYPE, "index_type": "IVF_FLAT", "params": {"nlist": 1024}})
    collection.create_index(
        CONTENT_SPARSE_FIELD,
        {
            "metric_type": "BM25",
            "index_type": "SPARSE_INVERTED_INDEX",
            "params": {"inverted_index_algo": "DAAT_MAXSCORE"},
        },
    )
    return collection


def get_embedding_function(embedding_model_spec: str, *, sync: bool = False):
    """按模型配置的批量大小返回编码函数。"""
    model = select_embedding_model(embedding_model_spec)
    batch_size = int(getattr(model, "batch_size", 40) or 40)
    return partial(model.batch_encode if sync else model.abatch_encode, batch_size=batch_size)
