from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from server.routers import knowledge_router
from yuxi.knowledge.base import FileStatus
from yuxi.knowledge.implementations import lightrag as lightrag_module
from yuxi.knowledge.implementations.lightrag import LightRagKB


pytestmark = pytest.mark.asyncio


def _build_kb_file(path: str) -> dict:
    return {
        "status": FileStatus.PARSED,
        "markdown_file": "mock://parsed.md",
        "path": path,
        "filename": path.rsplit("/", 1)[-1],
        "processing_params": {},
    }


class _FakeDocStatus:
    async def get_by_id(self, _file_id: str) -> dict:
        return {"status": "processed"}


@pytest.fixture
def light_rag_kb(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> LightRagKB:
    kb = LightRagKB(str(tmp_path))
    monkeypatch.setattr(kb, "_save_metadata", _async_noop)
    monkeypatch.setattr(kb, "_persist_file", _async_noop)
    monkeypatch.setattr(kb, "_read_markdown_from_minio", _fake_read_markdown)
    monkeypatch.setattr(kb, "delete_file_chunks_only", _async_noop)
    monkeypatch.setattr(
        lightrag_module,
        "chunk_markdown",
        lambda markdown, file_id, filename, params: [{"content": markdown or f"{file_id}:{filename}:{params}"}],
    )
    return kb


async def _async_noop(*_args, **_kwargs) -> None:
    return None


async def _fake_read_markdown(*_args, **_kwargs) -> str:
    return "mock markdown"


async def test_index_file_serializes_writes_within_same_database(
    light_rag_kb: LightRagKB,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_id = "kb_same"
    light_rag_kb.databases_meta[db_id] = {"metadata": {}}
    light_rag_kb.files_meta["file-1"] = _build_kb_file("/tmp/file-1.md")
    light_rag_kb.files_meta["file-2"] = _build_kb_file("/tmp/file-2.md")

    started_first = asyncio.Event()
    release_first = asyncio.Event()
    started_second = asyncio.Event()
    call_order: list[str] = []

    async def fake_ainsert(*, ids: str, **_kwargs) -> None:
        if ids == "file-1":
            call_order.append("start:file-1")
            started_first.set()
            await release_first.wait()
            call_order.append("end:file-1")
            return
        call_order.append("start:file-2")
        started_second.set()
        call_order.append("end:file-2")

    rag = SimpleNamespace(ainsert=fake_ainsert, doc_status=_FakeDocStatus())
    monkeypatch.setattr(light_rag_kb, "_get_lightrag_instance", _make_async_return(rag))

    task1 = asyncio.create_task(light_rag_kb.index_file(db_id, "file-1"))
    await asyncio.wait_for(started_first.wait(), timeout=1)

    task2 = asyncio.create_task(light_rag_kb.index_file(db_id, "file-2"))
    await asyncio.sleep(0.05)
    assert not started_second.is_set()

    release_first.set()
    await asyncio.gather(task1, task2)

    assert call_order == ["start:file-1", "end:file-1", "start:file-2", "end:file-2"]


async def test_index_file_allows_parallel_writes_for_different_databases(
    light_rag_kb: LightRagKB,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    light_rag_kb.databases_meta["kb_a"] = {"metadata": {}}
    light_rag_kb.databases_meta["kb_b"] = {"metadata": {}}
    light_rag_kb.files_meta["file-a"] = _build_kb_file("/tmp/file-a.md")
    light_rag_kb.files_meta["file-b"] = _build_kb_file("/tmp/file-b.md")

    started_a = asyncio.Event()
    started_b = asyncio.Event()
    release_both = asyncio.Event()

    async def fake_ainsert(*, ids: str, **_kwargs) -> None:
        if ids == "file-a":
            started_a.set()
        elif ids == "file-b":
            started_b.set()
        await release_both.wait()

    rag = SimpleNamespace(ainsert=fake_ainsert, doc_status=_FakeDocStatus())
    monkeypatch.setattr(light_rag_kb, "_get_lightrag_instance", _make_async_return(rag))

    task_a = asyncio.create_task(light_rag_kb.index_file("kb_a", "file-a"))
    task_b = asyncio.create_task(light_rag_kb.index_file("kb_b", "file-b"))

    await asyncio.wait_for(started_a.wait(), timeout=1)
    await asyncio.wait_for(started_b.wait(), timeout=1)

    release_both.set()
    await asyncio.gather(task_a, task_b)


async def test_add_documents_auto_index_uses_latest_parsed_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeKnowledgeBase:
        async def get_database_info(self, _db_id: str) -> dict:
            return {"name": "pytest-db"}

        async def add_file_record(
            self,
            _db_id: str,
            _item: str,
            params: dict | None = None,
            operator_id: str | None = None,
        ) -> dict:
            return {"file_id": "file-1", "status": FileStatus.UPLOADED, "params": params, "operator_id": operator_id}

        async def parse_file(self, _db_id: str, file_id: str, operator_id: str | None = None) -> dict:
            calls.append(("parse", file_id))
            return {"file_id": file_id, "status": FileStatus.PARSED, "operator_id": operator_id}

        async def update_file_params(
            self, _db_id: str, file_id: str, params: dict, operator_id: str | None = None
        ) -> None:
            calls.append(("update_params", file_id))

        async def index_file(self, _db_id: str, file_id: str, operator_id: str | None = None) -> dict:
            calls.append(("index", file_id))
            return {"file_id": file_id, "status": FileStatus.INDEXED, "operator_id": operator_id}

    class FakeTaskContext:
        async def set_message(self, _message: str) -> None:
            return None

        async def set_progress(self, _progress: float, _message: str | None = None) -> None:
            return None

        async def set_result(self, _result) -> None:
            return None

        async def raise_if_cancelled(self) -> None:
            return None

    class FakeTasker:
        async def enqueue(self, *, coroutine, **_kwargs):
            await coroutine(FakeTaskContext())
            return SimpleNamespace(id="task-1")

    async def fake_ensure_database_not_dify(_db_id: str, _operation: str) -> None:
        return None

    monkeypatch.setattr("yuxi.knowledge.utils.kb_utils.validate_file_path", lambda _item, _db_id: None)
    monkeypatch.setattr(knowledge_router, "knowledge_base", FakeKnowledgeBase())
    monkeypatch.setattr(knowledge_router, "tasker", FakeTasker())
    monkeypatch.setattr(knowledge_router, "_ensure_database_not_dify", fake_ensure_database_not_dify)

    current_user = SimpleNamespace(user_id="user-1", id="user-1")
    result = await knowledge_router.add_documents(
        "kb_auto_index",
        items=["/tmp/example.md"],
        params={"content_type": "file", "auto_index": True},
        current_user=current_user,
    )

    assert result["status"] == "queued"
    assert calls == [("parse", "file-1"), ("update_params", "file-1"), ("index", "file-1")]


def _make_async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
