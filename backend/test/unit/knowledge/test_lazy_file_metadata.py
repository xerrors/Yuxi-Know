from types import SimpleNamespace

import pytest

from yuxi.knowledge.base import KnowledgeBase


class FakeKnowledgeBase(KnowledgeBase):
    @property
    def kb_type(self) -> str:
        return "fake"

    async def _create_kb_instance(self, kb_id: str, embedding_model_spec: str | None):
        return None

    async def _initialize_kb_instance(self, instance) -> None:
        pass

    async def index_file(self, kb_id: str, file_id: str, operator_id: str | None = None) -> dict:
        return {}

    async def update_content(self, kb_id: str, file_ids: list[str], params: dict | None = None) -> list[dict]:
        return []

    async def aquery(self, query_text: str, kb_id: str, **kwargs) -> list[dict]:
        return []

    def get_query_params_config(self, kb_id: str, **kwargs) -> dict:
        return {"options": []}

    async def delete_file(self, kb_id: str, file_id: str) -> None:
        pass

    async def get_file_basic_info(self, kb_id: str, file_id: str) -> dict:
        return {}

    async def get_file_content(self, kb_id: str, file_id: str) -> dict:
        return {}

    async def get_file_info(self, kb_id: str, file_id: str) -> dict:
        return {}


def make_file_record(**overrides):
    data = {
        "file_id": "file-1",
        "kb_id": "db",
        "parent_id": None,
        "filename": "demo.md",
        "file_type": "md",
        "path": "minio://knowledgebases/db/upload/demo.md",
        "markdown_file": None,
        "status": "uploaded",
        "content_hash": "hash",
        "file_size": 123,
        "chunk_count": 0,
        "token_count": 0,
        "content_type": "file",
        "processing_params": {"ocr_engine": "disable"},
        "is_folder": False,
        "error_message": None,
        "created_by": "user",
        "updated_by": None,
        "created_at": None,
        "updated_at": None,
        "original_filename": None,
        "minio_url": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_update_file_params_lazy_loads_single_file(monkeypatch, tmp_path):
    kb = FakeKnowledgeBase(str(tmp_path))
    additional_params = {"chunk_preset_id": "general"}

    class FakeFileRepo:
        def __init__(self):
            self.updated = []

        async def get_by_file_id(self, file_id: str):
            assert file_id == "file-1"
            return make_file_record()

        async def update_fields(self, *, file_id: str, kb_id: str | None = None, data: dict):
            self.updated.append((file_id, kb_id, data))
            return make_file_record(
                processing_params=data["processing_params"],
                updated_by=data.get("updated_by"),
            )

    file_repo = FakeFileRepo()
    monkeypatch.setattr("yuxi.repositories.knowledge_file_repository.KnowledgeFileRepository", lambda: file_repo)

    await kb.update_file_params(
        "db",
        "file-1",
        {"chunk_preset_id": "qa"},
        operator_id="user-2",
        additional_params=additional_params,
    )

    assert not hasattr(kb, "files_meta")
    assert len(file_repo.updated) == 1
    file_id, kb_id, update_data = file_repo.updated[0]
    assert file_id == "file-1"
    assert kb_id == "db"
    assert update_data["processing_params"]["chunk_preset_id"] == "qa"
    assert update_data["processing_params"]["ocr_engine"] == "disable"
    assert update_data["updated_by"] == "user-2"
