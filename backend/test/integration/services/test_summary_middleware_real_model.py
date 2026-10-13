from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, get_buffer_string
from yuxi.modules.agents.runtime.middlewares.summary import YuxiSummarizationMiddleware
from yuxi.modules.models.chat import load_chat_model
from yuxi.modules.models.providers.builtin import BUILTIN_PROVIDERS
from yuxi.modules.models.providers.cache import ModelInfo
from yuxi.modules.workspace.runtime_paths import workdir_runtime_paths

VIRTUAL_PATH_LARGE_TOOL_RESULTS, VIRTUAL_PATH_CONVERSATION_HISTORY = workdir_runtime_paths(
    "/home/gem/user-data/projects/11111111-1111-4111-8111-111111111111"
)

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.getenv("RUN_MODEL_PROVIDER_CONNECTIVITY") != "1",
        reason="Set RUN_MODEL_PROVIDER_CONNECTIVITY=1 to call real provider model APIs.",
    ),
]


class _MemoryBackend:
    def __init__(self) -> None:
        self.writes: list[tuple[str, str]] = []

    def download_files(self, paths: list[str]) -> list[SimpleNamespace]:
        return [SimpleNamespace(content=None, error="file_not_found") for _ in paths]

    def write(self, path: str, content: str) -> SimpleNamespace:
        self.writes.append((path, content))
        return SimpleNamespace(error=None)

    def edit(self, path: str, old_string: str, new_string: str) -> SimpleNamespace:
        self.writes.append((path, new_string))
        return SimpleNamespace(error=None)

    async def adownload_files(self, paths: list[str]) -> list[SimpleNamespace]:
        return self.download_files(paths)

    async def awrite(self, path: str, content: str) -> SimpleNamespace:
        return self.write(path, content)

    async def aedit(self, path: str, old_string: str, new_string: str) -> SimpleNamespace:
        return self.edit(path, old_string, new_string)


def _content_char_counter(messages, **_kwargs) -> int:
    total = 0
    for message in messages:
        if message is None:
            continue
        content = getattr(message, "content", "")
        if isinstance(content, list):
            total += sum(len(str(item)) for item in content)
        else:
            total += len(str(content))
    return total


def _load_provider_config() -> dict[str, Any]:
    provider_id = os.getenv("TEST_MODEL_PROVIDER_ID", "siliconflow-cn")
    for provider in BUILTIN_PROVIDERS:
        if provider.get("provider_id") == provider_id:
            return provider
    pytest.skip(f"Builtin provider {provider_id} is not configured.")


def _select_enabled_chat_model(provider: dict[str, Any]) -> dict[str, Any]:
    preferred_model_id = os.getenv("TEST_PROVIDER_CHAT_MODEL")
    for model in provider.get("enabled_models") or []:
        if model.get("type") != "chat":
            continue
        if preferred_model_id and model.get("id") != preferred_model_id:
            continue
        return model
    if preferred_model_id:
        pytest.skip(f"{provider['provider_id']} does not expose {preferred_model_id} as chat.")
    pytest.skip(f"{provider['provider_id']} has no enabled chat model.")


async def test_compacted_messages_call_real_chat_model(monkeypatch: pytest.MonkeyPatch):
    provider = _load_provider_config()
    model_config = _select_enabled_chat_model(provider)
    api_key_env = provider.get("api_key_env")
    api_key = os.getenv(api_key_env or "") if api_key_env else None
    if not api_key:
        pytest.skip(f"{provider['provider_id']} requires {api_key_env} for connectivity testing.")

    model_spec = f"{provider['provider_id']}:{model_config['id']}"
    info = ModelInfo(
        provider_id=provider["provider_id"],
        model_id=model_config["id"],
        model_type="chat",
        display_name=model_config.get("display_name") or model_config["id"],
        api_key=api_key,
        base_url=model_config.get("base_url_override") or provider["base_url"],
        provider_type=provider.get("provider_type") or "openai",
        extra=dict(provider.get("extra_json") or {}),
    )

    def get_model_info(current: str):
        return info if current == model_spec else None

    monkeypatch.setattr("yuxi.modules.models.chat.model_cache.get_model_info", get_model_info)

    model_params = (model_config.get("extra") or {}).get("parameters") or {}
    real_model = load_chat_model(model_spec, **model_params)
    backend = _MemoryBackend()
    large_result = "BEGIN\n" + ("raw tool result payload\n" * 200) + "END"
    messages = [
        HumanMessage(content="请读取工具结果后继续。"),
        AIMessage(content="", tool_calls=[{"id": "call-1", "name": "query_kb", "args": {}}]),
        ToolMessage(content=large_result, tool_call_id="call-1", name="query_kb"),
        HumanMessage(content="请只回答 OK。"),
    ]
    middleware = YuxiSummarizationMiddleware(
        model=real_model,
        backend=backend,
        trigger=("tokens", 2000),
        keep=("messages", 2),
        token_counter=_content_char_counter,
        trim_tokens_to_summarize=None,
    )
    middleware._history_path_prefix = VIRTUAL_PATH_CONVERSATION_HISTORY
    middleware._large_tool_results_prefix = VIRTUAL_PATH_LARGE_TOOL_RESULTS
    captured_messages: list | None = None

    async def handler(request: ModelRequest) -> ModelResponse:
        nonlocal captured_messages
        captured_messages = request.messages
        response = await request.model.ainvoke(request.messages)
        return ModelResponse(result=[response])

    request = ModelRequest(
        model=real_model,
        messages=messages,
        system_message=None,
        tools=[],
        runtime=SimpleNamespace(context={}, config={}),
        state={"messages": messages},
    )
    result = await middleware.awrap_model_call(request, handler)

    assert isinstance(result, ModelResponse)
    assert result.result[0].text.strip()
    assert captured_messages is not None
    formatted = get_buffer_string(captured_messages)
    assert "[Tool result saved]" in formatted
    assert "END" not in formatted
    assert messages[2].content == large_result
    assert any(path.startswith(VIRTUAL_PATH_LARGE_TOOL_RESULTS) and content == large_result for path, content in backend.writes)
