from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import yuxi.modules.knowledge.repositories.chunks as repo_module
from yuxi.modules.knowledge.repositories.chunks import KnowledgeChunkRepository, SQL_IN_BATCH_SIZE


def _extract_id_batch(statement) -> list[str]:
    id_batches = [value for value in statement.compile().params.values() if isinstance(value, list | tuple) and value]
    assert len(id_batches) == 1
    return list(id_batches[0])


@pytest.mark.asyncio
async def test_list_by_chunk_ids_splits_large_inputs_and_preserves_order(monkeypatch):
    chunk_ids = [
        *(f"chunk-b-{index:05d}" for index in range(SQL_IN_BATCH_SIZE)),
        *(f"chunk-a-{index:05d}" for index in range(5)),
    ]
    batch_lengths: list[int] = []

    class FakeScalarResult:
        def __init__(self, chunks: list[SimpleNamespace]):
            self.chunks = chunks

        def all(self):
            return self.chunks

    class FakeResult:
        def __init__(self, chunks: list[SimpleNamespace]):
            self.chunks = chunks

        def scalars(self):
            return FakeScalarResult(self.chunks)

    class FakeSession:
        async def execute(self, statement):
            batch = _extract_id_batch(statement)
            batch_lengths.append(len(batch))
            return FakeResult([SimpleNamespace(chunk_id=chunk_id) for chunk_id in batch])

    @asynccontextmanager
    async def fake_session_context():
        yield FakeSession()

    monkeypatch.setattr(repo_module.pg_manager, "get_async_session_context", fake_session_context)

    chunks = await KnowledgeChunkRepository().list_by_chunk_ids(chunk_ids)

    assert batch_lengths == [SQL_IN_BATCH_SIZE, 5]
    assert [chunk.chunk_id for chunk in chunks] == chunk_ids
