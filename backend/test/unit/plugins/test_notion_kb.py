from __future__ import annotations

import pytest

from yuxi.knowledge.implementations.notion import NOTION_DEFAULT_VERSION, NotionAPIError, NotionKB
from yuxi.knowledge.read_models import KnowledgeBaseConfig


PAGE_ID = "page-1"
DATA_SOURCE_ID = "ds-1"


PAGE = {
    "object": "page",
    "id": PAGE_ID,
    "url": "https://www.notion.so/page-1",
    "created_time": "2026-01-01T00:00:00.000Z",
    "last_edited_time": "2026-01-02T00:00:00.000Z",
    "parent": {"type": "data_source_id", "data_source_id": DATA_SOURCE_ID},
    "properties": {
        "Name": {"type": "title", "title": [{"plain_text": "Reasoning Paper"}]},
        "Abstract": {"type": "rich_text", "rich_text": [{"plain_text": "Chain of thought reasoning"}]},
    },
}


BLOCKS = {
    PAGE_ID: [
        {
            "object": "block",
            "id": "block-1",
            "type": "paragraph",
            "has_children": False,
            "paragraph": {"rich_text": [{"plain_text": "This page discusses reasoning models."}]},
        },
        {
            "object": "block",
            "id": "block-2",
            "type": "heading_2",
            "has_children": False,
            "heading_2": {"rich_text": [{"plain_text": "Evaluation"}]},
        },
    ]
}


class _FakeNotionClient:
    def __init__(self, token: str, notion_version: str) -> None:
        self.token = token
        self.notion_version = notion_version

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def search_pages(self, query_text: str, limit: int) -> list[dict]:
        del query_text, limit
        return [PAGE]

    async def query_data_source(self, data_source_id: str, limit: int) -> list[dict]:
        del limit
        assert data_source_id == DATA_SOURCE_ID
        return [PAGE]

    async def retrieve_page(self, page_id: str) -> dict:
        assert page_id == PAGE_ID
        return PAGE

    async def retrieve_block_children(self, block_id: str, limit: int) -> list[dict]:
        del limit
        return BLOCKS.get(block_id, [])


class _FailingNotionClient(_FakeNotionClient):
    async def search_pages(self, query_text: str, limit: int) -> list[dict]:
        del query_text, limit
        raise NotionAPIError("boom")


class _UnknownParentNotionClient(_FakeNotionClient):
    async def retrieve_page(self, page_id: str) -> dict:
        page = await super().retrieve_page(page_id)
        return {**page, "parent": {"type": "page_id", "page_id": "other-page"}}


@pytest.fixture
def notion_kb(tmp_path):
    kb = NotionKB(str(tmp_path))
    additional_params = {
        "notion_token": "token",
        "notion_data_source_id": DATA_SOURCE_ID,
        "notion_version": NOTION_DEFAULT_VERSION,
    }
    config = KnowledgeBaseConfig(
        kb_id="kb_notion",
        kb_type="notion",
        query_params={"options": {}},
        additional_params=additional_params,
    )
    return kb, config


def test_notion_create_params_config_and_validation(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_API_KEY", raising=False)

    config = NotionKB.get_create_params_config()
    keys = [option["key"] for option in config["options"]]
    assert keys == ["notion_token", "notion_data_source_id", "notion_version"]

    params = NotionKB.normalize_additional_params(
        {
            "notion_token": " token ",
            "notion_data_source_id": " ds-1 ",
            "notion_version": " 2026-03-11 ",
        }
    )
    assert params == {
        "notion_token": "token",
        "notion_data_source_id": DATA_SOURCE_ID,
        "notion_version": NOTION_DEFAULT_VERSION,
    }
    assert "chunk_preset_id" not in params


def test_notion_validation_accepts_env_token(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "env-token")
    params = NotionKB.normalize_additional_params({"notion_data_source_id": DATA_SOURCE_ID})
    assert params["notion_token"] == ""
    assert params["notion_data_source_id"] == DATA_SOURCE_ID


def test_notion_validation_rejects_missing_params(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_API_KEY", raising=False)

    with pytest.raises(ValueError, match="notion_data_source_id"):
        NotionKB.normalize_additional_params({"notion_token": "token"})

    with pytest.raises(ValueError, match="notion_token"):
        NotionKB.normalize_additional_params({"notion_data_source_id": DATA_SOURCE_ID})


@pytest.mark.asyncio
async def test_notion_kb_aquery_maps_pages(monkeypatch, notion_kb):
    kb, config = notion_kb
    monkeypatch.setattr("yuxi.knowledge.implementations.notion._NotionClient", _FakeNotionClient)

    result = await kb.aquery(
        "reasoning",
        "kb_notion",
        config=config,
    )

    assert len(result) == 1
    assert "reasoning" in result[0]["content"].lower()
    assert result[0]["score"] > 0
    assert result[0]["metadata"]["source"] == "Reasoning Paper"
    assert result[0]["metadata"]["file_id"] == PAGE_ID
    assert result[0]["metadata"]["chunk_id"].startswith(f"{PAGE_ID}:")
    assert result[0]["metadata"]["notion_url"] == "https://www.notion.so/page-1"


@pytest.mark.asyncio
async def test_notion_open_file_content_uses_page_markdown(monkeypatch, notion_kb):
    kb, config = notion_kb
    monkeypatch.setattr("yuxi.knowledge.implementations.notion._NotionClient", _FakeNotionClient)

    result = await kb.open_file_content(
        "kb_notion",
        PAGE_ID,
        offset=0,
        limit=3,
        additional_params=config.additional_params,
    )

    assert result["start_line"] == 1
    assert result["end_line"] == 3
    assert result["has_more_after"] is True
    assert "Reasoning Paper" in result["content"]


@pytest.mark.asyncio
async def test_notion_find_file_content_uses_page_markdown(monkeypatch, notion_kb):
    kb, config = notion_kb
    monkeypatch.setattr("yuxi.knowledge.implementations.notion._NotionClient", _FakeNotionClient)

    result = await kb.find_file_content(
        "kb_notion",
        PAGE_ID,
        ["models"],
        window_size=4,
        additional_params=config.additional_params,
    )

    assert result["match_mode"] == "keyword"
    assert result["total_matches"] == 1
    assert result["windows"]
    assert "reasoning models" in result["windows"][0]["content"]


@pytest.mark.asyncio
async def test_notion_open_file_content_rejects_unknown_parent(monkeypatch, notion_kb):
    kb, config = notion_kb
    monkeypatch.setattr("yuxi.knowledge.implementations.notion._NotionClient", _UnknownParentNotionClient)

    with pytest.raises(ValueError, match="不属于当前 Data Source"):
        await kb.open_file_content("kb_notion", PAGE_ID, additional_params=config.additional_params)


@pytest.mark.asyncio
async def test_notion_kb_aquery_error_returns_empty(monkeypatch, notion_kb):
    kb, config = notion_kb
    monkeypatch.setattr("yuxi.knowledge.implementations.notion._NotionClient", _FailingNotionClient)

    result = await kb.aquery(
        "reasoning",
        "kb_notion",
        config=config,
    )

    assert result == []
