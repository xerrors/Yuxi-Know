"""聊天搜索的纯文本摘要。"""

MESSAGE_SEARCH_SNIPPET_RADIUS = 72
MESSAGE_SEARCH_SNIPPET_MAX_LENGTH = 180


def build_message_search_snippet(content: str, query: str) -> str:
    """保留关键词附近的紧凑文本预览。"""
    normalized = " ".join(str(content or "").split())
    if not normalized:
        return ""

    match_index = normalized.lower().find(query.lower())
    if match_index < 0:
        return normalized[:MESSAGE_SEARCH_SNIPPET_MAX_LENGTH]

    start = max(0, match_index - MESSAGE_SEARCH_SNIPPET_RADIUS)
    end = min(len(normalized), match_index + len(query) + MESSAGE_SEARCH_SNIPPET_RADIUS)
    snippet = normalized[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(normalized):
        snippet = f"{snippet}..."
    return snippet[:MESSAGE_SEARCH_SNIPPET_MAX_LENGTH]
