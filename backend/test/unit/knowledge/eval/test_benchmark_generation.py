import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from yuxi.knowledge.eval.benchmark_generation import (
    build_benchmark_generation_prompt,
    clamp_neighbors_count,
    collect_kb_chunks,
    cosine_similarity,
    select_neighbor_indices,
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


def test_clamp_neighbors_count():
    assert clamp_neighbors_count(-1) == 0
    assert clamp_neighbors_count(3) == 3
    assert clamp_neighbors_count(11) == 10


def test_select_neighbor_indices_orders_by_cosine_similarity():
    embeddings = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]]
    norms = [1.0, cosine_similarity(embeddings[1], embeddings[1], 1.0, 1.0) ** 0.5, 1.0]

    assert select_neighbor_indices(0, embeddings, norms, 1) == [1]


def test_build_benchmark_generation_prompt_contains_required_schema():
    prompt = build_benchmark_generation_prompt([("chunk_1", "片段内容")])

    assert "片段ID=chunk_1" in prompt
    assert "query、gold_answer、gold_chunk_ids" in prompt


@pytest.mark.asyncio
async def test_collect_kb_chunks_filters_database_id():
    chunks = await collect_kb_chunks(FakeKnowledgeBase(), "db_1")

    assert chunks == [{"id": "file_a_chunk", "content": "内容", "file_id": "file_a", "chunk_index": 0}]
