import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from yuxi.knowledge.eval import benchmark_generation
from yuxi.knowledge.eval.benchmark_generation import (
    build_benchmark_generation_prompt,
    clamp_neighbors_count,
    collect_kb_chunks,
    iter_generated_benchmark_items,
    select_neighbor_chunks_by_kb_query,
)


class FakeKnowledgeBase:
    files_meta = {
        "file_a": {"database_id": "db_1"},
        "file_b": {"database_id": "db_2"},
    }

    async def get_file_content(self, db_id, fid):
        return {
            "lines": [
                {"id": f"{fid}_chunk", "content": "内容", "chunk_order_index": 0},
            ]
        }


class FakeGenerationKnowledgeBase:
    files_meta = {"file_a": {"database_id": "db_1"}}

    def __init__(self, query_results=None):
        self.query_results = query_results or []
        self.query_calls = []

    async def get_file_content(self, db_id, fid):
        return {
            "lines": [
                {"id": "anchor_chunk", "content": "anchor content", "chunk_order_index": 0},
            ]
        }

    async def aquery(self, query_text, db_id, **kwargs):
        self.query_calls.append({"query_text": query_text, "db_id": db_id, **kwargs})
        return self.query_results


class FakeLlm:
    def __init__(self, gold_chunk_id="anchor_chunk"):
        self.gold_chunk_id = gold_chunk_id
        self.prompts = []

    async def call(self, prompt, stream):
        self.prompts.append(prompt)
        return SimpleNamespace(
            content=('{"query":"问题","gold_answer":"答案","gold_chunk_ids":["' + self.gold_chunk_id + '"]}')
        )


class NoQueryKnowledgeBase(FakeGenerationKnowledgeBase):
    async def aquery(self, query_text, db_id, **kwargs):
        raise AssertionError("neighbors_count=1 时不应调用 aquery")


def test_clamp_neighbors_count():
    assert clamp_neighbors_count(-1) == 0
    assert clamp_neighbors_count(3) == 3
    assert clamp_neighbors_count(11) == 10


def test_build_benchmark_generation_prompt_contains_required_schema():
    prompt = build_benchmark_generation_prompt([("chunk_1", "片段内容")])

    assert "片段ID=chunk_1" in prompt
    assert "query、gold_answer、gold_chunk_ids" in prompt


@pytest.mark.asyncio
async def test_collect_kb_chunks_filters_database_id():
    chunks = await collect_kb_chunks(FakeKnowledgeBase(), "db_1")

    assert chunks == [{"id": "file_a_chunk", "content": "内容", "file_id": "file_a", "chunk_index": 0}]


@pytest.mark.asyncio
async def test_iter_generated_benchmark_items_with_one_chunk_does_not_query(monkeypatch):
    fake_llm = FakeLlm()
    monkeypatch.setattr(benchmark_generation, "select_model", lambda model_spec: fake_llm)

    items = [
        item
        async for item in iter_generated_benchmark_items(
            kb_instance=NoQueryKnowledgeBase(),
            db_id="db_1",
            count=1,
            neighbors_count=1,
            llm_model_spec="test-model",
        )
    ]

    assert items == [{"query": "问题", "gold_chunk_ids": ["anchor_chunk"], "gold_answer": "答案"}]
    assert "片段ID=anchor_chunk" in fake_llm.prompts[0]


@pytest.mark.asyncio
async def test_select_neighbor_chunks_by_kb_query_filters_anchor():
    kb = FakeGenerationKnowledgeBase(
        query_results=[
            {
                "content": "anchor content",
                "metadata": {"chunk_id": "anchor_chunk", "file_id": "file_a", "chunk_index": 0},
            },
            {
                "content": "neighbor content",
                "metadata": {"chunk_id": "neighbor_chunk", "file_id": "file_a", "chunk_index": 1},
            },
        ]
    )

    chunks = await select_neighbor_chunks_by_kb_query(
        kb_instance=kb,
        db_id="db_1",
        anchor_chunk={"id": "anchor_chunk", "content": "anchor content", "file_id": "file_a", "chunk_index": 0},
        neighbors_count=1,
    )

    assert chunks == [{"id": "neighbor_chunk", "content": "neighbor content", "file_id": "file_a", "chunk_index": 1}]
    assert kb.query_calls == [
        {
            "query_text": "anchor content",
            "db_id": "db_1",
            "search_mode": "vector",
            "final_top_k": 4,
            "use_reranker": False,
            "similarity_threshold": 0.0,
        }
    ]


@pytest.mark.asyncio
async def test_iter_generated_benchmark_items_uses_query_neighbor(monkeypatch):
    fake_llm = FakeLlm(gold_chunk_id="neighbor_chunk")
    monkeypatch.setattr(benchmark_generation, "select_model", lambda model_spec: fake_llm)
    kb = FakeGenerationKnowledgeBase(
        query_results=[
            {
                "content": "neighbor content",
                "metadata": {"chunk_id": "neighbor_chunk", "file_id": "file_a", "chunk_index": 1},
            }
        ]
    )

    items = [
        item
        async for item in iter_generated_benchmark_items(
            kb_instance=kb,
            db_id="db_1",
            count=1,
            neighbors_count=2,
            llm_model_spec="test-model",
        )
    ]

    assert items == [{"query": "问题", "gold_chunk_ids": ["neighbor_chunk"], "gold_answer": "答案"}]
    assert kb.query_calls[0]["query_text"] == "anchor content"
    assert kb.query_calls[0]["search_mode"] == "vector"
    assert "片段ID=neighbor_chunk" in fake_llm.prompts[0]


@pytest.mark.asyncio
async def test_iter_generated_benchmark_items_falls_back_to_anchor_when_query_empty(monkeypatch):
    fake_llm = FakeLlm()
    monkeypatch.setattr(benchmark_generation, "select_model", lambda model_spec: fake_llm)

    items = [
        item
        async for item in iter_generated_benchmark_items(
            kb_instance=FakeGenerationKnowledgeBase(query_results=[]),
            db_id="db_1",
            count=1,
            neighbors_count=2,
            llm_model_spec="test-model",
        )
    ]

    assert items == [{"query": "问题", "gold_chunk_ids": ["anchor_chunk"], "gold_answer": "答案"}]
    assert "片段ID=anchor_chunk" in fake_llm.prompts[0]
