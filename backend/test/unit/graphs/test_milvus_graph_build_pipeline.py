from __future__ import annotations

import pytest


import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from yuxi.modules.knowledge.graphs.extractors import GraphExtractorFactory, normalize_extraction_result
from yuxi.modules.knowledge.graphs.service import KnowledgeGraphService
from yuxi.modules.knowledge.graphs.milvus_graph_vector_store import MilvusGraphVectorStore

pytestmark = pytest.mark.usefixtures("milvus_graph_projection_lock")


class _FakeChunkRepository:
    """为图构建测试保留同一批 chunk 的状态变化。"""

    def __init__(self, chunks):
        self.chunks = chunks

    async def count_graph_pending_by_kb_id(self, kb_id):
        """统计尚未完成图索引的 chunk。"""
        return sum(not getattr(chunk, "graph_indexed", False) for chunk in self.chunks)

    async def count_graph_indexed_by_kb_id(self, kb_id):
        """统计已经完成图索引的 chunk。"""
        return sum(getattr(chunk, "graph_indexed", False) for chunk in self.chunks)

    async def count_graph_extraction_statuses_by_kb_id(self, kb_id):
        """按提取状态统计当前测试数据。"""
        counts = {"pending": 0, "succeeded": 0, "failed": 0}
        for chunk in self.chunks:
            details = getattr(chunk, "graph_extraction_details", None) or {}
            status = details.get("status", "succeeded" if chunk.extraction_result is not None else "pending")
            counts[status] += 1
        return counts

    async def list_graph_pending_by_kb_id(self, kb_id, limit, *, after_id=0):
        """返回游标后的待处理 chunk。"""
        return [chunk for chunk in self.chunks if chunk.id > after_id and not getattr(chunk, "graph_indexed", False)][:limit]

    async def update_extraction_result(self, chunk_id, extraction_result, attempt_count=1):
        """保存提取结果并标记为成功。"""
        chunk = await self.get_by_chunk_id(chunk_id)
        chunk.extraction_result = extraction_result
        chunk.graph_extraction_details = {"status": "succeeded", "attempt_count": attempt_count}

    async def mark_graph_extraction_pending(self, chunk_id):
        """将提取状态恢复为待处理。"""
        chunk = await self.get_by_chunk_id(chunk_id)
        chunk.graph_extraction_details = {"status": "pending", "attempt_count": 0}

    async def mark_graph_extraction_failed(self, chunk_id, attempt_count, error):
        """保存失败次数和错误文本。"""
        chunk = await self.get_by_chunk_id(chunk_id)
        chunk.graph_extraction_details = {"status": "failed", "attempt_count": attempt_count, "last_error": error}

    async def get_by_chunk_id(self, chunk_id):
        """按稳定 chunk id 返回同一条替身记录。"""
        return next(chunk for chunk in self.chunks if chunk.chunk_id == chunk_id)

    async def mark_graph_structure_indexed(self, chunk_id, ent_ids=None):
        """标记 chunk 的结构写入已完成。"""
        chunk = await self.get_by_chunk_id(chunk_id)
        chunk.graph_structure_indexed = True


def _milvus_graph_kb(concurrency_count: int = 1) -> SimpleNamespace:
    """创建图构建配置一致的知识库替身。"""
    return SimpleNamespace(
        kb_type="milvus",
        embedding_model_spec="test/embedding",
        additional_params={
            "graph_build_config": {
                "locked": True,
                "extractor_type": "llm",
                "extractor_options": {"model_spec": "test/model", "concurrency_count": concurrency_count},
            }
        },
    )


@pytest.mark.asyncio
async def test_graph_vector_delete_waits_for_sibling_io_after_first_failure(monkeypatch):
    """一个删除失败后也等另一个 SDK 线程结束，避免释放锁后的晚删。"""
    store = object.__new__(MilvusGraphVectorStore)
    slow_started, fast_failed, release = threading.Event(), threading.Event(), threading.Event()
    finished = []

    def delete_ids(collection_name, ids):
        """模拟一快一慢两个外部删除。"""
        if ids == ["entity"]:
            fast_failed.set()
            raise RuntimeError("first delete failed")
        slow_started.set()
        assert release.wait(10)
        finished.append("triple deleted")

    monkeypatch.setattr(store, "_delete_ids", delete_ids)
    deleting = asyncio.create_task(store.delete_graph_records("kb-test", entity_ids=["entity"], triple_ids=["triple"]))
    try:
        async with asyncio.timeout(5):
            while not (slow_started.is_set() and fast_failed.is_set()):
                await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        assert not deleting.done()
        release.set()
        with pytest.raises(RuntimeError, match="first delete failed"):
            await deleting
        assert finished == ["triple deleted"]
    finally:
        release.set()
        await asyncio.gather(deleting, return_exceptions=True)


@pytest.mark.asyncio
async def test_graph_build_keeps_extraction_concurrency_full_while_writes_are_blocked(monkeypatch):
    chunks = [
        SimpleNamespace(
            id=index,
            chunk_id=f"chunk_{index}",
            file_id="file_1",
            kb_id="kb_test",
            chunk_index=index,
            content=f"content {index}",
            start_char_pos=0,
            end_char_pos=10,
            extraction_result=None,
            graph_extraction_details={"status": "pending", "attempt_count": 0},
            graph_indexed=False,
        )
        for index in range(1, 7)
    ]
    chunks[0].extraction_result = {"entities": [], "relations": []}
    chunks[0].graph_extraction_details = {"status": "succeeded"}
    kb = _milvus_graph_kb(concurrency_count=2)
    all_extractions_finished = asyncio.Event()
    release_writes = asyncio.Event()

    class Repo:
        async def get_by_kb_id(self, kb_id):
            return kb

    chunk_repo = _FakeChunkRepository(chunks)

    class Extractor:
        extractor_type = "llm"
        active = 0
        max_active = 0
        calls = 0
        completed = 0

        async def extract(self, text, *, chunk_metadata=None):
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                await asyncio.sleep(0.01)
                if text == "content 6":
                    raise RuntimeError("extract failed")
                return {"entities": [], "relations": []}
            finally:
                self.active -= 1
                self.completed += 1
                if self.completed == 7:
                    all_extractions_finished.set()

    extractor = Extractor()
    monkeypatch.setattr(GraphExtractorFactory, "create", lambda extractor_type, options: extractor)
    monkeypatch.setattr(
        "yuxi.modules.knowledge.graphs.service.GRAPH_EXTRACTION_RETRY_DELAYS_SECONDS",
        (0, 0),
    )

    async def wait_for_writes(**kwargs):
        await release_writes.wait()

    class GraphRepo:
        upsert_chunk_graph = AsyncMock(side_effect=wait_for_writes)

        async def claim_vector_records(self, **kwargs):
            return "token", []

        async def count_vector_statuses_by_kb_id(self, kb_id):
            return {"pending": 0, "processing": 0, "indexed": 0, "failed": 0}

        async def finalize_graph_indexed_chunks(self, kb_id):
            finalized = 0
            for chunk in chunks:
                if getattr(chunk, "graph_structure_indexed", False) and not chunk.graph_indexed:
                    chunk.graph_indexed = True
                    finalized += 1
            return finalized

    graph_repo = GraphRepo()
    graph_vector_store = SimpleNamespace(upsert_graph_records=AsyncMock())
    service = KnowledgeGraphService(
        kb_repo=Repo(),
        chunk_repo=chunk_repo,
        graph_repo=graph_repo,
        graph_vector_store=graph_vector_store,
    )
    monkeypatch.setattr(service, "write_chunk_graph", lambda kb_id, chunk, result: ([], []))

    build_job = asyncio.create_task(service.build_pending_chunks("kb_test"))
    await asyncio.wait_for(all_extractions_finished.wait(), timeout=1)

    assert extractor.max_active == 2
    assert extractor.calls == 7
    assert not build_job.done()

    release_writes.set()
    result = await asyncio.wait_for(build_job, timeout=1)

    assert result["success"] == 5
    assert result["extraction_failed"] == 1
    assert result["remaining"] == 1
    assert chunks[-1].graph_extraction_details["status"] == "failed"
    assert chunks[-1].graph_extraction_details["attempt_count"] == 3


@pytest.mark.asyncio
async def test_graph_build_cancellation_stops_backpressured_extraction_queue(monkeypatch):
    chunks = [
        SimpleNamespace(
            id=index,
            chunk_id=f"chunk_{index}",
            file_id="file_1",
            kb_id="kb_test",
            chunk_index=index,
            content=f"content {index}",
            extraction_result=None,
            graph_indexed=False,
        )
        for index in range(1, 10)
    ]
    kb = _milvus_graph_kb(concurrency_count=1)
    extraction_started = asyncio.Event()
    never_finish = asyncio.Event()

    class Repo:
        async def get_by_kb_id(self, kb_id):
            return kb

    chunk_repo = _FakeChunkRepository(chunks)

    class Extractor:
        extractor_type = "llm"

        async def extract(self, text, *, chunk_metadata=None):
            extraction_started.set()
            await never_finish.wait()

    class Context:
        cancel_requested = False

        async def raise_if_cancelled(self):
            if self.cancel_requested:
                raise asyncio.CancelledError

        async def set_progress(self, progress, message):
            return None

    context = Context()
    monkeypatch.setattr(GraphExtractorFactory, "create", lambda extractor_type, options: Extractor())
    service = KnowledgeGraphService(
        kb_repo=Repo(),
        chunk_repo=chunk_repo,
        graph_repo=SimpleNamespace(),
        graph_vector_store=SimpleNamespace(),
    )

    build_job = asyncio.create_task(service.build_pending_chunks("kb_test", context=context))
    await asyncio.wait_for(extraction_started.wait(), timeout=1)
    context.cancel_requested = True

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(build_job, timeout=1.5)


@pytest.mark.asyncio
async def test_graph_build_indexes_vectors_after_structure_write(monkeypatch):
    chunk = SimpleNamespace(
        id=1,
        chunk_id="chunk_1",
        file_id="file_1",
        kb_id="kb_test",
        chunk_index=1,
        content="张三任职于公司",
        start_char_pos=0,
        end_char_pos=8,
        extraction_result=normalize_extraction_result(
            {
                "relations": [
                    {
                        "source": {"text": "张三", "label": "Person"},
                        "target": {"text": "公司", "label": "Organization"},
                        "text": "任职于",
                        "label": "WORKS_AT",
                    }
                ]
            },
            "llm",
        ),
        graph_structure_indexed=False,
        graph_indexed=False,
    )
    kb = _milvus_graph_kb(concurrency_count=2)

    chunk_repo = _FakeChunkRepository([chunk])

    class GraphRepo:
        def __init__(self):
            self.pending = False
            self.indexed = False

        async def upsert_chunk_graph(self, **kwargs):
            self.pending = True

        async def claim_vector_records(self, *, record_type, **kwargs):
            if record_type == "entity" and self.pending:
                self.pending = False
                return "token", [{"id": "entity_1", "content": "张三"}]
            return "token", []

        async def mark_vector_records_indexed(self, **kwargs):
            self.indexed = True

        async def mark_vector_records_failed(self, **kwargs):
            raise AssertionError("vector indexing should succeed")

        async def count_vector_statuses_by_kb_id(self, kb_id):
            return {
                "pending": int(self.pending),
                "processing": 0,
                "indexed": int(self.indexed),
                "failed": 0,
            }

        async def finalize_graph_indexed_chunks(self, kb_id):
            if chunk.graph_structure_indexed and self.indexed:
                chunk.graph_indexed = True
                return 1
            return 0

    graph_repo = GraphRepo()
    vector_store = SimpleNamespace(upsert_graph_records=AsyncMock())
    service = KnowledgeGraphService(
        kb_repo=SimpleNamespace(get_by_kb_id=AsyncMock(return_value=kb)),
        chunk_repo=chunk_repo,
        graph_repo=graph_repo,
        graph_vector_store=vector_store,
    )
    monkeypatch.setattr(
        service,
        "write_chunk_graph",
        lambda kb_id, chunk, result: ([{"entity_id": "entity_1"}], []),
    )

    result = await service.build_pending_chunks("kb_test")

    assert result == {
        "kb_id": "kb_test",
        "success": 1,
        "failed": 0,
        "extraction_failed": 0,
        "write_failed": 0,
        "remaining": 0,
        "vector_failed": 0,
    }
    vector_store.upsert_graph_records.assert_awaited_once()
    assert chunk.graph_structure_indexed is True
    assert chunk.graph_indexed is True


@pytest.mark.asyncio
async def test_graph_build_fails_after_three_vector_attempts(monkeypatch):
    chunk = SimpleNamespace(
        id=1,
        chunk_id="chunk_1",
        file_id="file_1",
        kb_id="kb_test",
        chunk_index=1,
        content="content",
        start_char_pos=0,
        end_char_pos=7,
        extraction_result={"entities": [], "relations": [], "metadata": {"extractor_type": "llm"}},
        graph_structure_indexed=False,
        graph_indexed=False,
    )
    kb = _milvus_graph_kb(concurrency_count=1)

    chunk_repo = _FakeChunkRepository([chunk])

    class GraphRepo:
        attempts = 0
        status = "pending"

        async def upsert_chunk_graph(self, **kwargs):
            return None

        async def claim_vector_records(self, *, record_type, **kwargs):
            if record_type != "entity" or self.status != "pending":
                return "token", []
            self.status = "processing"
            self.attempts += 1
            return "token", [{"id": "entity_1", "content": "entity"}]

        async def mark_vector_records_indexed(self, **kwargs):
            raise AssertionError("vector indexing should fail")

        async def mark_vector_records_failed(self, **kwargs):
            self.status = "failed" if self.attempts >= 3 else "pending"

        async def count_vector_statuses_by_kb_id(self, kb_id):
            return {
                "pending": int(self.status == "pending"),
                "processing": int(self.status == "processing"),
                "indexed": 0,
                "failed": int(self.status == "failed"),
            }

        async def finalize_graph_indexed_chunks(self, kb_id):
            return 0

    graph_repo = GraphRepo()
    service = KnowledgeGraphService(
        kb_repo=SimpleNamespace(get_by_kb_id=AsyncMock(return_value=kb)),
        chunk_repo=chunk_repo,
        graph_repo=graph_repo,
        graph_vector_store=SimpleNamespace(upsert_graph_records=AsyncMock(side_effect=RuntimeError("embed failed"))),
    )
    monkeypatch.setattr(service, "write_chunk_graph", lambda kb_id, chunk, result: ([{"entity_id": "e"}], []))

    with pytest.raises(RuntimeError, match="vector_failed=1"):
        await service.build_pending_chunks("kb_test")

    assert graph_repo.attempts == 3


@pytest.mark.asyncio
async def test_graph_reconcile_skips_completed_structure(monkeypatch):
    chunk = SimpleNamespace(
        id=1,
        chunk_id="chunk_1",
        graph_structure_indexed=True,
        graph_indexed=False,
        extraction_result={"entities": [], "relations": []},
    )
    kb = _milvus_graph_kb(concurrency_count=1)

    chunk_repo = _FakeChunkRepository([chunk])

    class GraphRepo:
        pending = True

        async def upsert_chunk_graph(self, **kwargs):
            raise AssertionError("reconcile must not rewrite graph structure")

        async def claim_vector_records(self, *, record_type, **kwargs):
            if record_type == "entity" and self.pending:
                self.pending = False
                return "token", [{"id": "entity_1", "content": "entity"}]
            return "token", []

        async def mark_vector_records_indexed(self, **kwargs):
            return None

        async def mark_vector_records_failed(self, **kwargs):
            raise AssertionError("vector indexing should succeed")

        async def count_vector_statuses_by_kb_id(self, kb_id):
            return {"pending": int(self.pending), "processing": 0, "indexed": 1, "failed": 0}

        async def finalize_graph_indexed_chunks(self, kb_id):
            chunk.graph_indexed = True
            return 1

    service = KnowledgeGraphService(
        kb_repo=SimpleNamespace(get_by_kb_id=AsyncMock(return_value=kb)),
        chunk_repo=chunk_repo,
        graph_repo=GraphRepo(),
        graph_vector_store=SimpleNamespace(upsert_graph_records=AsyncMock()),
    )
    monkeypatch.setattr(service, "write_chunk_graph", MagicMock(side_effect=AssertionError("must not write")))

    result = await service.build_pending_chunks("kb_test")

    assert result["success"] == 1
    service.write_chunk_graph.assert_not_called()


@pytest.mark.asyncio
async def test_milvus_graph_service_configure_rejects_spacy():
    kb = SimpleNamespace(kb_type="milvus", additional_params={})

    class Repo:
        async def get_by_kb_id(self, kb_id):
            return kb

        async def update(self, kb_id, data):
            raise AssertionError("unsupported extractor should not be persisted")

    service = KnowledgeGraphService(kb_repo=Repo())

    with pytest.raises(ValueError, match="不支持的图谱抽取器类型"):
        await service.configure(
            "kb_test",
            extractor_type="spacy",
            extractor_options={"model": "zh_core_web_sm"},
            created_by="user_1",
        )


@pytest.mark.asyncio
async def test_milvus_graph_service_configure_persists_updated_concurrency():
    kb = SimpleNamespace(
        kb_type="milvus",
        additional_params={
            "graph_build_config": {
                "locked": True,
                "extractor_type": "llm",
                "extractor_options": {"model_spec": "test/model", "concurrency_count": 5},
            }
        },
    )

    class Repo:
        async def get_by_kb_id(self, kb_id):
            return kb

        async def update(self, kb_id, data):
            kb.additional_params = data["additional_params"]
            return kb

    chunk_repo = SimpleNamespace(
        count_by_kb_id=AsyncMock(return_value=0),
        count_graph_pending_by_kb_id=AsyncMock(return_value=0),
        count_graph_indexed_by_kb_id=AsyncMock(return_value=0),
        count_graph_structure_indexed_by_kb_id=AsyncMock(return_value=0),
        count_graph_extraction_statuses_by_kb_id=AsyncMock(return_value={"pending": 0, "succeeded": 0, "failed": 0}),
    )
    graph_repo = SimpleNamespace(
        count_by_kb_id=AsyncMock(return_value=(3, 2)),
        count_vector_statuses_by_kb_id=AsyncMock(return_value={"pending": 0, "processing": 0, "indexed": 5, "failed": 0}),
    )
    service = KnowledgeGraphService(kb_repo=Repo(), chunk_repo=chunk_repo, graph_repo=graph_repo)

    await service.configure(
        "kb_test",
        extractor_type="llm",
        extractor_options={"model_spec": "test/model", "concurrency_count": 9},
        created_by="user_1",
    )
    status = await service.get_status("kb_test")

    assert status["config"]["extractor_options"]["concurrency_count"] == 9
    assert status["entity_count"] == 3
    assert status["relationship_count"] == 2


@pytest.mark.asyncio
async def test_graph_status_reports_latest_successful_run_as_completed():
    kb = SimpleNamespace(
        kb_type="milvus",
        additional_params={
            "graph_build_config": {
                "locked": True,
                "extractor_type": "llm",
                "extractor_options": {"model_spec": "test/model", "concurrency_count": 5},
            }
        },
    )

    class Repo:
        async def get_by_kb_id(self, kb_id):
            return kb

    class JobTracker:
        async def find_job_by_payload(self, *, job_type, payload_match, statuses):
            assert statuses is None
            return SimpleNamespace(status="success", progress=100)

    chunk_repo = SimpleNamespace(
        count_by_kb_id=AsyncMock(return_value=10),
        count_graph_pending_by_kb_id=AsyncMock(return_value=0),
        count_graph_indexed_by_kb_id=AsyncMock(return_value=10),
        count_graph_structure_indexed_by_kb_id=AsyncMock(return_value=10),
        count_graph_extraction_statuses_by_kb_id=AsyncMock(return_value={"pending": 0, "succeeded": 10, "failed": 0}),
    )
    graph_repo = SimpleNamespace(
        count_by_kb_id=AsyncMock(return_value=(3, 2)),
        count_vector_statuses_by_kb_id=AsyncMock(return_value={"pending": 0, "processing": 0, "indexed": 5, "failed": 0}),
    )
    service = KnowledgeGraphService(kb_repo=Repo(), chunk_repo=chunk_repo, graph_repo=graph_repo)

    status = await service.get_status("kb_test", job_tracker=JobTracker())

    assert status["build_job_status"] == "completed"
    assert status["build_job_progress"] == 100


def test_milvus_graph_service_writes_chunk_entity_and_relation():
    tx = MagicMock()
    session = MagicMock()
    session.__enter__.return_value = session
    session.execute_write.side_effect = lambda func: func(tx)
    driver = MagicMock()
    driver.session.return_value = session
    connection = SimpleNamespace(driver=driver)
    service = KnowledgeGraphService(neo4j_connection=connection)
    chunk = SimpleNamespace(
        chunk_id="chunk_1",
        file_id="file_1",
        kb_id="kb_test",
        chunk_index=1,
        content="张三任职于公司",
        start_char_pos=0,
        end_char_pos=8,
    )

    entities, triples = service.write_chunk_graph(
        "kb_test",
        chunk,
        normalize_extraction_result(
            {
                "relations": [
                    {
                        "source": {
                            "text": "张三",
                            "label": "Person",
                            "attributes": [{"text": "工程师", "label": "Occupation"}],
                        },
                        "target": {"text": "公司", "label": "Organization"},
                        "text": "任职于",
                        "label": "WORKS_AT",
                    }
                ],
            },
            "llm",
        ),
    )

    assert [entity["name"] for entity in entities] == ["张三", "公司"]
    assert {entity["label"] for entity in entities} == {"Person", "Organization"}
    assert triples[0]["relation_type"] == "WORKS_AT"
    queries = [call.args[0] for call in tx.run.call_args_list]
    assert any("MERGE (c:Chunk:MilvusKB:`kb_test`" in query for query in queries)
    assert any("MERGE (e:Entity:MilvusKB:`kb_test`" in query for query in queries)
    assert any("MERGE (source)-[r:RELATION" in query for query in queries)
    entity_call = next(call for call in tx.run.call_args_list if "MERGE (e:Entity" in call.args[0])
    assert entity_call.kwargs["attributes"] == '[{"text": "工程师", "label": "Occupation"}]'


def test_graph_vector_store_uses_idempotent_upsert():
    collection = MagicMock()
    store = MilvusGraphVectorStore.__new__(MilvusGraphVectorStore)

    store._upsert_entities(
        collection,
        [{"id": "entity_1", "content": "entity"}],
        [[0.1, 0.2]],
    )

    collection.upsert.assert_called_once_with([["entity_1"], ["entity"], [[0.1, 0.2]]])
    collection.insert.assert_not_called()
