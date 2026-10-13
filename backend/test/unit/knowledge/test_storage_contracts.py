"""共享存储装配、并发容量和配置边界的独立证据。"""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.modules.knowledge.graphs.extractors.llm import LLMGraphExtractor
from yuxi.modules.knowledge.graphs.milvus_graph_vector_store import MilvusGraphVectorStore
from yuxi.modules.knowledge.graphs.service import KnowledgeGraphService
from yuxi.modules.knowledge.implementations.milvus import MilvusKB
from yuxi.modules.knowledge.storage import milvus
from yuxi.modules.knowledge.storage.offload import BoundedOffload
from yuxi.modules.knowledge.chunking.ragflow_like.parsers import semantic


@pytest.mark.parametrize("kind", ["document", "entity", "triple"])
def test_collection_contract_has_fixed_common_fields_and_indexes(monkeypatch, kind):
    """三个调用入口都必须产生独立固定的公共存储契约。"""
    collections = []

    class Collection:
        """保留实际 schema 对象与索引定义以供固定断言。"""

        def __init__(self, **kwargs):
            self.schema = kwargs["schema"]
            self.indexes = {}
            collections.append(self)

        def create_index(self, name, params):
            """保存实际装配结果。"""
            self.indexes[name] = params

    monkeypatch.setattr(milvus, "Collection", Collection)
    monkeypatch.setattr("yuxi.modules.knowledge.graphs.milvus_graph_vector_store.utility.has_collection", lambda *a, **k: False)
    info = SimpleNamespace(dimension=4, model_id="fixed")
    if kind == "document":
        executor = MilvusKB.__new__(MilvusKB)
        executor.connection_alias = "fixed"
        executor._create_new_collection("kb", info, "kb")
    else:
        executor = MilvusGraphVectorStore.__new__(MilvusGraphVectorStore)
        executor.connection_alias = "fixed"
        getattr(executor, f"_get_or_create_{kind}_collection")("kb", info)
    collection = collections[0]
    fields = {field.name: field for field in collection.schema.fields}
    assert fields["content"].params == {
        "max_length": 65535,
        "enable_analyzer": True,
        "enable_match": True,
        "analyzer_params": '{"type":"chinese"}',
    }
    assert fields["embedding"].params == {"dim": 4}
    assert fields["id"].is_primary
    assert collection.schema.functions[0].input_field_names == ["content"]
    assert collection.schema.functions[0].output_field_names == ["content_sparse"]
    assert collection.indexes == {
        "embedding": {"metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 1024}},
        "content_sparse": {
            "metric_type": "BM25",
            "index_type": "SPARSE_INVERTED_INDEX",
            "params": {"inverted_index_algo": "DAAT_MAXSCORE"},
        },
    }


@pytest.mark.asyncio
async def test_cancelled_waiter_keeps_thread_capacity_until_io_finishes():
    """取消等待后，第二个线程必须等首个实际退出才能写入结果。"""
    offload = BoundedOffload(1)
    started = threading.Event()
    release = threading.Event()
    results = []

    def blocked():
        """保持真实线程运行，证明取消不会提前释放容量。"""
        started.set()
        release.wait(3)
        results.append("first")

    first = asyncio.create_task(offload(blocked))
    await asyncio.wait_for(asyncio.to_thread(started.wait), 1)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(offload(results.append, "second"))
    try:
        await asyncio.sleep(0.05)
        assert results == []
        assert not second.done()
    finally:
        release.set()
    await asyncio.wait_for(second, 1)
    assert results == ["first", "second"]


@pytest.mark.asyncio
async def test_graph_store_concurrent_acquisition_constructs_once(monkeypatch):
    """并发查询共享同一客户端，构造 RPC 只发生在首次取得时。"""
    stores = []

    def construct():
        """每次构造产生独立身份，便于识别重复客户端。"""
        value = object()
        stores.append(value)
        return value

    monkeypatch.setattr("yuxi.modules.knowledge.graphs.service.MilvusGraphVectorStore", construct)
    service = KnowledgeGraphService()
    clients = await asyncio.gather(*(service.get_graph_vector_store() for _ in range(40)))
    assert stores == [clients[0]]
    assert all(client is clients[0] for client in clients)


@pytest.mark.asyncio
async def test_extraction_reuses_model_and_preserves_each_chunk(monkeypatch):
    """并发分块复用模型，结果仍来自各自输入。"""
    clients = []

    def model(**kwargs):
        """记录模型身份并回显当前 prompt。"""
        client = SimpleNamespace(call=AsyncMock(return_value=SimpleNamespace(content='{"entities": []}')))
        clients.append(client)
        return client

    monkeypatch.setattr("yuxi.modules.knowledge.graphs.extractors.llm.select_model", model)
    extractor = LLMGraphExtractor({"model_spec": "fixed:model"})
    results = await asyncio.gather(*(extractor.extract(f"chunk-{i}") for i in range(30)))
    assert results == [{"entities": []}] * 30
    assert len(clients) == 1
    assert [call.args[0].split("文本：\n")[1] for call in clients[0].call.await_args_list] == [f"chunk-{i}" for i in range(30)]


def test_semantic_missing_or_unavailable_model_fails_explicitly(monkeypatch):
    """模型配置缺失和装配故障都不能产生伪装成功的普通切分。"""
    with pytest.raises(ValueError, match="embed_model_id"):
        semantic.chunk_markdown("fixed input", {})

    def unavailable(spec):
        """注入明确的模型装配故障。"""
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("yuxi.modules.models.embed.select_embedding_model", unavailable)
    with pytest.raises(RuntimeError, match="model unavailable"):
        semantic.chunk_markdown("fixed input", {"embed_model_id": "fixed:model"})


@pytest.mark.asyncio
async def test_cancelled_first_graph_waiter_does_not_duplicate_constructor(monkeypatch):
    """首个等待者取消后仍复用实际构造完成的客户端。"""
    started = threading.Event()
    release = threading.Event()
    stores = []

    def construct():
        """用阻塞构造复现取消与第二请求重叠。"""
        value = object()
        stores.append(value)
        started.set()
        release.wait(3)
        return value

    monkeypatch.setattr("yuxi.modules.knowledge.graphs.service.MilvusGraphVectorStore", construct)
    service = KnowledgeGraphService()
    first = asyncio.create_task(service.get_graph_vector_store())
    await asyncio.wait_for(asyncio.to_thread(started.wait), 1)
    first.cancel()
    second = asyncio.create_task(service.get_graph_vector_store())
    try:
        await asyncio.sleep(0.05)
        assert len(stores) == 1
        assert not second.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert await asyncio.wait_for(second, 1) is stores[0]
    assert len(stores) == 1
