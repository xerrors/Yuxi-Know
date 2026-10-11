import pytest

from test.unit.support.knowledge import FakeKnowledgeBase, make_knowledge_file_record as make_file_record


@pytest.mark.asyncio
async def test_base_export_is_explicitly_unsupported(tmp_path):
    kb = FakeKnowledgeBase(str(tmp_path))

    with pytest.raises(NotImplementedError, match="不支持数据导出"):
        await kb.export_data("db", format="csv")


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
    monkeypatch.setattr("yuxi.modules.knowledge.repositories.files.KnowledgeFileRepository", lambda: file_repo)

    await kb.update_file_params(
        "db",
        "file-1",
        {"chunk_preset_id": "qa"},
        operator_id="user-2",
        additional_params=additional_params,
    )

    assert len(file_repo.updated) == 1
    file_id, kb_id, update_data = file_repo.updated[0]
    assert file_id == "file-1"
    assert kb_id == "db"
    assert update_data["processing_params"]["chunk_preset_id"] == "qa"
    assert update_data["processing_params"]["ocr_engine"] == "disable"
    assert update_data["updated_by"] == "user-2"
