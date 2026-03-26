from __future__ import annotations

from yuxi.repositories.conversation_repository import ConversationRepository, MAX_CONVERSATION_TITLE_LENGTH


def test_normalize_title_truncates_when_too_long():
    repo = ConversationRepository(None)  # type: ignore[arg-type]
    raw = "a" * (MAX_CONVERSATION_TITLE_LENGTH + 50)

    normalized = repo._normalize_title(raw)

    assert normalized is not None
    assert len(normalized) == MAX_CONVERSATION_TITLE_LENGTH
    assert normalized == "a" * MAX_CONVERSATION_TITLE_LENGTH


def test_normalize_title_trims_spaces():
    repo = ConversationRepository(None)  # type: ignore[arg-type]

    normalized = repo._normalize_title("   hello world   ")

    assert normalized == "hello world"


def test_normalize_agent_config_id_casts_to_int():
    repo = ConversationRepository(None)  # type: ignore[arg-type]

    normalized = repo._normalize_agent_config_id("12")  # type: ignore[arg-type]

    assert normalized == 12


def test_normalize_agent_config_id_allows_none():
    repo = ConversationRepository(None)  # type: ignore[arg-type]

    normalized = repo._normalize_agent_config_id(None)

    assert normalized is None
