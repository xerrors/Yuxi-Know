"""
Unit tests for MiniMax provider configuration and model selection.

These tests validate MiniMax integration without requiring Docker services.
Run with: uv run python -m pytest test/test_minimax_provider.py -v
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# ============================================================
# Helpers: Import static models module directly (bypass src.__init__)
# ============================================================

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_static_models():
    """Load src/config/static/models.py directly, bypassing src.__init__.py."""
    models_path = _PROJECT_ROOT / "src" / "config" / "static" / "models.py"
    spec = importlib.util.spec_from_file_location("_static_models", models_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_models_mod = _load_static_models()
DEFAULT_CHAT_MODEL_PROVIDERS = _models_mod.DEFAULT_CHAT_MODEL_PROVIDERS
ChatModelProvider = _models_mod.ChatModelProvider


# ============================================================
# Unit Tests: Provider Configuration
# ============================================================


class TestMiniMaxProviderConfig:
    """Verify MiniMax is correctly registered in default providers."""

    def test_minimax_in_default_providers(self):
        assert "minimax" in DEFAULT_CHAT_MODEL_PROVIDERS

    def test_minimax_provider_type(self):
        assert isinstance(DEFAULT_CHAT_MODEL_PROVIDERS["minimax"], ChatModelProvider)

    def test_minimax_name(self):
        assert DEFAULT_CHAT_MODEL_PROVIDERS["minimax"].name == "MiniMax"

    def test_minimax_base_url(self):
        assert DEFAULT_CHAT_MODEL_PROVIDERS["minimax"].base_url == "https://api.minimax.io/v1"

    def test_minimax_env_var(self):
        assert DEFAULT_CHAT_MODEL_PROVIDERS["minimax"].env == "MINIMAX_API_KEY"

    def test_minimax_default_model(self):
        assert DEFAULT_CHAT_MODEL_PROVIDERS["minimax"].default == "MiniMax-M2.7"

    def test_minimax_models_list(self):
        expected = ["MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.5-highspeed"]
        assert DEFAULT_CHAT_MODEL_PROVIDERS["minimax"].models == expected

    def test_minimax_not_custom(self):
        assert DEFAULT_CHAT_MODEL_PROVIDERS["minimax"].custom is False

    def test_minimax_has_documentation_url(self):
        assert DEFAULT_CHAT_MODEL_PROVIDERS["minimax"].url.startswith("https://")

    def test_minimax_all_models_have_minimax_prefix(self):
        for model in DEFAULT_CHAT_MODEL_PROVIDERS["minimax"].models:
            assert model.startswith("MiniMax-"), f"Model {model} should start with 'MiniMax-'"


# ============================================================
# Unit Tests: Provider Serialization
# ============================================================


class TestMiniMaxProviderSerialization:
    """Test that MiniMax provider config serializes correctly."""

    def test_minimax_model_dump(self):
        dumped = DEFAULT_CHAT_MODEL_PROVIDERS["minimax"].model_dump()
        assert dumped["name"] == "MiniMax"
        assert dumped["base_url"] == "https://api.minimax.io/v1"
        assert dumped["env"] == "MINIMAX_API_KEY"
        assert dumped["default"] == "MiniMax-M2.7"
        assert len(dumped["models"]) == 4
        assert dumped["custom"] is False

    def test_minimax_model_dump_round_trip(self):
        provider = DEFAULT_CHAT_MODEL_PROVIDERS["minimax"]
        restored = ChatModelProvider(**provider.model_dump())
        assert restored == provider

    def test_minimax_model_dump_keys(self):
        dumped = DEFAULT_CHAT_MODEL_PROVIDERS["minimax"].model_dump()
        assert set(dumped.keys()) == {"name", "url", "base_url", "default", "env", "models", "custom"}


# ============================================================
# Unit Tests: Model Selection (standalone, no Docker deps)
# ============================================================


class TestMiniMaxModelSelection:
    """Test model selection logic with MiniMax provider."""

    def _build_select_model(self, providers_dict):
        """Build a standalone select_model function mirroring src/models/chat.py."""

        class _Model:
            def __init__(self, api_key, base_url, model_name):
                self.api_key = api_key
                self.base_url = base_url
                self.model_name = model_name

        def select_model(model_provider=None, model_name=None, model_spec=None):
            if model_spec:
                parts = model_spec.split("/", 1)
                model_provider = model_provider or parts[0]
                model_name = model_name or (parts[1] if len(parts) > 1 else "")

            assert model_provider, "Model provider not specified"
            info = providers_dict.get(model_provider)
            if not info:
                raise ValueError(f"Unknown model provider: {model_provider}")
            model_name = model_name or info.default
            return _Model(
                api_key=os.environ.get(info.env, info.env),
                base_url=info.base_url,
                model_name=model_name,
            )

        return select_model

    def test_select_model_minimax_default(self):
        select_model = self._build_select_model({"minimax": DEFAULT_CHAT_MODEL_PROVIDERS["minimax"]})
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key-123"}):
            model = select_model("minimax", "MiniMax-M2.7")
        assert model.model_name == "MiniMax-M2.7"
        assert model.base_url == "https://api.minimax.io/v1"

    def test_select_model_minimax_highspeed(self):
        select_model = self._build_select_model({"minimax": DEFAULT_CHAT_MODEL_PROVIDERS["minimax"]})
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key-123"}):
            model = select_model("minimax", "MiniMax-M2.7-highspeed")
        assert model.model_name == "MiniMax-M2.7-highspeed"

    def test_select_model_minimax_uses_default(self):
        select_model = self._build_select_model({"minimax": DEFAULT_CHAT_MODEL_PROVIDERS["minimax"]})
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key-123"}):
            model = select_model("minimax")
        assert model.model_name == "MiniMax-M2.7"

    def test_select_model_minimax_from_spec(self):
        select_model = self._build_select_model({"minimax": DEFAULT_CHAT_MODEL_PROVIDERS["minimax"]})
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key-123"}):
            model = select_model(model_spec="minimax/MiniMax-M2.5")
        assert model.model_name == "MiniMax-M2.5"
        assert model.base_url == "https://api.minimax.io/v1"

    def test_select_model_minimax_api_key_from_env(self):
        select_model = self._build_select_model({"minimax": DEFAULT_CHAT_MODEL_PROVIDERS["minimax"]})
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "my-secret-key"}):
            model = select_model("minimax", "MiniMax-M2.7")
        assert model.api_key == "my-secret-key"

    def test_select_model_unknown_provider_raises(self):
        select_model = self._build_select_model({"minimax": DEFAULT_CHAT_MODEL_PROVIDERS["minimax"]})
        with pytest.raises(ValueError, match="Unknown model provider"):
            select_model("nonexistent", "some-model")


# ============================================================
# Unit Tests: LangChain OpenAI-compat Loading
# ============================================================


class TestMiniMaxLangChainLoading:
    """Test ChatOpenAI instantiation for MiniMax (OpenAI-compat)."""

    def test_langchain_openai_compat_for_minimax(self):
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        minimax = DEFAULT_CHAT_MODEL_PROVIDERS["minimax"]
        model = ChatOpenAI(
            model="MiniMax-M2.7",
            api_key=SecretStr("test-key-123"),
            base_url=minimax.base_url,
            stream_usage=True,
        )
        assert isinstance(model, ChatOpenAI)
        assert model.model_name == "MiniMax-M2.7"

    def test_langchain_minimax_highspeed(self):
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        minimax = DEFAULT_CHAT_MODEL_PROVIDERS["minimax"]
        model = ChatOpenAI(
            model="MiniMax-M2.5-highspeed",
            api_key=SecretStr("test-key-123"),
            base_url=minimax.base_url,
        )
        assert isinstance(model, ChatOpenAI)
        assert model.model_name == "MiniMax-M2.5-highspeed"

    def test_langchain_minimax_base_url_correct(self):
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        minimax = DEFAULT_CHAT_MODEL_PROVIDERS["minimax"]
        model = ChatOpenAI(
            model="MiniMax-M2.7",
            api_key=SecretStr("test-key-123"),
            base_url=minimax.base_url,
        )
        assert str(model.openai_api_base) == "https://api.minimax.io/v1"


# ============================================================
# Integration Tests: MiniMax API Connectivity
# ============================================================


@pytest.mark.integration
class TestMiniMaxIntegration:
    """Integration tests that verify MiniMax API connectivity.

    Require MINIMAX_API_KEY env var and network access to api.minimax.io.
    Run with: uv run python -m pytest test/test_minimax_provider.py -m integration -v
    """

    @pytest.fixture(autouse=True)
    def skip_without_api_key(self):
        if not os.environ.get("MINIMAX_API_KEY"):
            pytest.skip("MINIMAX_API_KEY not set")

    @pytest.mark.asyncio
    async def test_minimax_chat_completion(self):
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=os.environ["MINIMAX_API_KEY"], base_url="https://api.minimax.io/v1")
        response = await client.chat.completions.create(
            model="MiniMax-M2.7", messages=[{"role": "user", "content": "Say 1."}]
        )
        assert response.choices[0].message.content is not None

    @pytest.mark.asyncio
    async def test_minimax_streaming(self):
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=os.environ["MINIMAX_API_KEY"], base_url="https://api.minimax.io/v1")
        chunks = []
        response = await client.chat.completions.create(
            model="MiniMax-M2.7", messages=[{"role": "user", "content": "Say hi."}], stream=True
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                chunks.append(chunk.choices[0].delta.content)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_minimax_highspeed_model(self):
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=os.environ["MINIMAX_API_KEY"], base_url="https://api.minimax.io/v1")
        response = await client.chat.completions.create(
            model="MiniMax-M2.7-highspeed", messages=[{"role": "user", "content": "Say 1."}]
        )
        assert response.choices[0].message.content is not None
