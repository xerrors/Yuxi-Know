from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from yuxi.knowledge.read_models import KnowledgeBaseDetail
from yuxi.knowledge.utils import sample_question_utils as sq


def _database_detail(files: dict | None = None, *, name: str = "测试知识库") -> KnowledgeBaseDetail:
    return KnowledgeBaseDetail(
        kb_id="kb_1",
        name=name,
        description=None,
        kb_type="milvus",
        embedding_model_spec=None,
        llm_model_spec=None,
        query_params={},
        additional_params={},
        share_config={"version": 2, "read_scope": None, "manage_scope": None},
        created_by=None,
        created_at=None,
        files=files,
    )


def test_parse_sample_questions_content_strips_json_fence():
    questions = sq.parse_sample_questions_content('```json\n{"questions": ["什么是测试？"]}\n```')

    assert questions == ["什么是测试？"]


def test_parse_sample_questions_content_rejects_invalid_payload():
    with pytest.raises(ValueError, match="问题格式"):
        sq.parse_sample_questions_content('{"items": []}')


@pytest.mark.asyncio
async def test_generate_database_sample_questions_rejects_empty_files(monkeypatch):
    class FakeKnowledgeBase:
        async def get_database_info(self, kb_id: str, include_files: bool = False) -> KnowledgeBaseDetail:
            return _database_detail({}, name="空知识库")

    monkeypatch.setattr(sq, "knowledge_base", FakeKnowledgeBase())
    monkeypatch.setattr(
        sq.KnowledgeBaseFactory,
        "get_kb_class",
        lambda _kb_type: SimpleNamespace(supports_documents=True),
    )

    with pytest.raises(HTTPException) as exc_info:
        await sq.generate_database_sample_questions("kb_1")

    assert exc_info.value.status_code == 400
    assert "没有文件" in exc_info.value.detail


@pytest.mark.asyncio
async def test_generate_database_sample_questions_saves_and_returns_questions(monkeypatch):
    saved: dict = {}

    class FakeKnowledgeBase:
        async def get_database_info(self, kb_id: str, include_files: bool = False) -> KnowledgeBaseDetail:
            return _database_detail({"file_1": {"filename": "demo.md", "file_type": "md"}})

    class FakeModel:
        async def call(self, messages, stream: bool = False):
            assert messages[0]["role"] == "system"
            assert "demo.md" in messages[1]["content"]
            return SimpleNamespace(content='{"questions": ["如何使用 demo？"]}')

    class FakeRepository:
        async def update(self, kb_id: str, data: dict) -> None:
            saved[kb_id] = data["sample_questions"]

        async def get_by_kb_id(self, kb_id: str):
            return SimpleNamespace(name="测试知识库", sample_questions=saved.get(kb_id))

    monkeypatch.setattr(sq, "knowledge_base", FakeKnowledgeBase())
    monkeypatch.setattr(
        sq.KnowledgeBaseFactory,
        "get_kb_class",
        lambda _kb_type: SimpleNamespace(supports_documents=True),
    )
    monkeypatch.setattr(sq, "select_model", lambda model_spec: FakeModel())
    monkeypatch.setattr(sq, "KnowledgeBaseRepository", lambda: FakeRepository())

    generated = await sq.generate_database_sample_questions("kb_1", count=1)
    stored = await sq.get_database_sample_questions("kb_1")

    assert generated["questions"] == ["如何使用 demo？"]
    assert generated["count"] == 1
    assert stored["questions"] == ["如何使用 demo？"]


@pytest.mark.asyncio
async def test_generate_database_sample_questions_maps_invalid_json(monkeypatch):
    class FakeKnowledgeBase:
        async def get_database_info(self, kb_id: str, include_files: bool = False) -> KnowledgeBaseDetail:
            return _database_detail({"file_1": {"filename": "demo.md", "file_type": "md"}})

    class FakeModel:
        async def call(self, messages, stream: bool = False):
            return SimpleNamespace(content="not json")

    monkeypatch.setattr(sq, "knowledge_base", FakeKnowledgeBase())
    monkeypatch.setattr(
        sq.KnowledgeBaseFactory,
        "get_kb_class",
        lambda _kb_type: SimpleNamespace(supports_documents=True),
    )
    monkeypatch.setattr(sq, "select_model", lambda model_spec: FakeModel())

    with pytest.raises(HTTPException) as exc_info:
        await sq.generate_database_sample_questions("kb_1")

    assert exc_info.value.status_code == 500
    assert "AI返回格式错误" in exc_info.value.detail
