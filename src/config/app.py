"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import tomli
import tomli_w
from pydantic import BaseModel, Field, PrivateAttr

from src.config.static.models import (
    DEFAULT_CHAT_MODEL_PROVIDERS,
    DEFAULT_EMBED_MODELS,
    DEFAULT_RERANKERS,
    ChatModelProvider,
    EmbedModelInfo,
    RerankerInfo,
)
from src.utils.logging_config import logger


class Config(BaseModel):
    save_dir: str = Field(default="saves", description="Storage root directory")
    model_dir: str = Field(default="", description="Local model directory")

    enable_reranker: bool = Field(default=False)
    enable_content_guard: bool = Field(default=False)
    enable_content_guard_llm: bool = Field(default=False)
    enable_web_search: bool = Field(default=False)

    default_model: str = Field(default="siliconflow/deepseek-ai/DeepSeek-V3.2")
    fast_model: str = Field(default="siliconflow/THUDM/GLM-4-9B-0414")
    embed_model: str = Field(default="siliconflow/BAAI/bge-m3")
    reranker: str = Field(default="siliconflow/BAAI/bge-reranker-v2-m3")
    content_guard_llm_model: str = Field(default="siliconflow/Qwen/Qwen3-235B-A22B-Instruct-2507")

    default_agent_id: str = Field(default="")

    sandbox_provider: str = Field(default="provisioner")
    sandbox_provisioner_url: str = Field(default="http://sandbox-provisioner:8002")
    sandbox_virtual_path_prefix: str = Field(default="/mnt/user-data")
    sandbox_exec_timeout_seconds: int = Field(default=180)
    sandbox_max_output_bytes: int = Field(default=262144)
    sandbox_keepalive_interval_seconds: int = Field(default=30)

    model_names: dict[str, ChatModelProvider] = Field(
        default_factory=lambda: DEFAULT_CHAT_MODEL_PROVIDERS.copy(),
        exclude=True,
    )
    embed_model_names: dict[str, EmbedModelInfo] = Field(
        default_factory=lambda: DEFAULT_EMBED_MODELS.copy(),
        exclude=True,
    )
    reranker_names: dict[str, RerankerInfo] = Field(
        default_factory=lambda: DEFAULT_RERANKERS.copy(),
        exclude=True,
    )

    model_provider_status: dict[str, bool] = Field(default_factory=dict, exclude=True)
    valuable_model_provider: list[str] = Field(default_factory=list, exclude=True)

    _config_file: Path | None = PrivateAttr(default=None)
    _user_modified_fields: set[str] = PrivateAttr(default_factory=set)
    _modified_providers: set[str] = PrivateAttr(default_factory=set)

    model_config = {"arbitrary_types_allowed": True, "extra": "allow"}

    def __init__(self, **data):
        super().__init__(**data)
        self._setup_paths()
        self._load_user_config()
        self._load_custom_providers()
        self._handle_environment()

    def _setup_paths(self) -> None:
        self.save_dir = os.getenv("SAVE_DIR") or self.save_dir
        self._config_file = Path(self.save_dir) / "config" / "base.toml"
        self._config_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_user_config(self) -> None:
        if not self._config_file or not self._config_file.exists():
            logger.info(f"Config file not found, using defaults: {self._config_file}")
            return

        try:
            with self._config_file.open("rb") as file:
                user_config = tomli.load(file)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to load config from {self._config_file}: {exc}")
            return

        self._user_modified_fields = set(user_config.keys())
        for key, value in user_config.items():
            if key == "model_names":
                self._load_model_names(value)
            elif key in self.model_fields:
                setattr(self, key, value)
            else:
                logger.warning(f"Unknown config key: {key}")

    def _load_model_names(self, model_names_data: dict[str, Any]) -> None:
        for provider, provider_data in (model_names_data or {}).items():
            try:
                if provider in self.model_names:
                    merged = self.model_names[provider].model_dump() | dict(provider_data or {})
                    self.model_names[provider] = ChatModelProvider(**merged)
                else:
                    self.model_names[provider] = ChatModelProvider(**provider_data)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Skip invalid model provider config {provider}: {exc}")

    def _load_custom_providers(self) -> None:
        if not self._config_file:
            return
        custom_config_file = self._config_file.parent / "custom_providers.toml"
        if not custom_config_file.exists():
            return

        try:
            with custom_config_file.open("rb") as file:
                custom_config = tomli.load(file)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to load custom providers from {custom_config_file}: {exc}")
            return

        model_names = custom_config.get("model_names") or {}
        self._load_custom_model_providers(model_names)

    def _load_custom_model_providers(self, providers_data: dict[str, Any]) -> None:
        for provider, provider_data in (providers_data or {}).items():
            try:
                payload = dict(provider_data or {})
                payload["custom"] = True
                self.model_names[provider] = ChatModelProvider(**payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Skip invalid custom provider {provider}: {exc}")

    def _handle_environment(self) -> None:
        self.model_dir = os.environ.get("MODEL_DIR") or self.model_dir

        self.model_provider_status = {}
        for provider, info in self.model_names.items():
            env_var = (info.env or "").strip()
            if env_var.upper() == "NO_API_KEY":
                self.model_provider_status[provider] = True
                continue
            api_key = os.environ.get(env_var)
            self.model_provider_status[provider] = bool(api_key or info.custom)

        if os.getenv("TAVILY_API_KEY"):
            self.enable_web_search = True

        self.valuable_model_provider = [key for key, ok in self.model_provider_status.items() if ok]

        self.sandbox_provider = (os.getenv("SANDBOX_PROVIDER") or self.sandbox_provider or "provisioner").strip()
        self.sandbox_provisioner_url = (
            os.getenv("SANDBOX_PROVISIONER_URL") or self.sandbox_provisioner_url or "http://sandbox-provisioner:8002"
        ).strip()
        self.sandbox_virtual_path_prefix = (
            os.getenv("SANDBOX_VIRTUAL_PATH_PREFIX") or self.sandbox_virtual_path_prefix or "/mnt/user-data"
        ).strip()
        self.sandbox_exec_timeout_seconds = int(
            os.getenv("SANDBOX_EXEC_TIMEOUT_SECONDS") or self.sandbox_exec_timeout_seconds or 180
        )
        self.sandbox_max_output_bytes = int(
            os.getenv("SANDBOX_MAX_OUTPUT_BYTES") or self.sandbox_max_output_bytes or 262144
        )
        self.sandbox_keepalive_interval_seconds = int(
            os.getenv("SANDBOX_KEEPALIVE_INTERVAL_SECONDS") or self.sandbox_keepalive_interval_seconds or 30
        )

        if self.sandbox_provider.lower() != "provisioner":
            raise ValueError("Only sandbox_provider=provisioner is supported.")
        if not self.sandbox_provisioner_url:
            raise ValueError("SANDBOX_PROVISIONER_URL is required when sandbox provider is provisioner.")
        if not self.sandbox_virtual_path_prefix.startswith("/"):
            self.sandbox_virtual_path_prefix = f"/{self.sandbox_virtual_path_prefix}"

        if not self.valuable_model_provider:
            raise ValueError("No model provider available, please check your `.env` file.")

    def save(self) -> None:
        if not self._config_file:
            logger.warning("Config file path not set")
            return

        default_config = Config.model_construct()
        user_modified: dict[str, Any] = {}
        for field_name, field_info in self.model_fields.items():
            if field_info.exclude:
                continue
            current_value = getattr(self, field_name)
            default_value = getattr(default_config, field_name)
            if current_value != default_value:
                user_modified[field_name] = current_value

        try:
            with self._config_file.open("wb") as file:
                tomli_w.dump(user_modified, file)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to save config to {self._config_file}: {exc}")

    def dump_config(self) -> dict[str, Any]:
        config_dict = self.model_dump(
            exclude={
                "model_names",
                "embed_model_names",
                "reranker_names",
                "model_provider_status",
                "valuable_model_provider",
            }
        )
        config_dict["model_names"] = {provider: info.model_dump() for provider, info in self.model_names.items()}
        config_dict["embed_model_names"] = {
            model_id: info.model_dump() for model_id, info in self.embed_model_names.items()
        }
        config_dict["reranker_names"] = {model_id: info.model_dump() for model_id, info in self.reranker_names.items()}
        config_dict["model_provider_status"] = self.model_provider_status
        config_dict["valuable_model_provider"] = self.valuable_model_provider

        fields_info: dict[str, Any] = {}
        for field_name, field_info in Config.model_fields.items():
            if field_info.exclude:
                continue
            annotation = field_info.annotation
            fields_info[field_name] = {
                "des": field_info.description,
                "default": field_info.default,
                "type": annotation.__name__ if hasattr(annotation, "__name__") else str(annotation),
                "exclude": bool(field_info.exclude),
            }
        config_dict["_config_items"] = fields_info
        return config_dict

    def get_model_choices(self) -> list[str]:
        choices: list[str] = []
        for provider, info in self.model_names.items():
            if not self.model_provider_status.get(provider, False):
                continue
            choices.extend([f"{provider}/{model}" for model in info.models])
        return choices

    def get_embed_model_choices(self) -> list[str]:
        return list(self.embed_model_names.keys())

    def get_reranker_choices(self) -> list[str]:
        return list(self.reranker_names.keys())

    def __getitem__(self, key: str) -> Any:
        logger.warning("Using deprecated dict-style access for Config. Please use attribute access instead.")
        return getattr(self, key, None)

    def __setitem__(self, key: str, value: Any) -> None:
        logger.warning("Using deprecated dict-style assignment for Config. Please use attribute access instead.")
        setattr(self, key, value)

    def update(self, other: dict[str, Any]) -> None:
        for key, value in (other or {}).items():
            if key in self.model_fields:
                setattr(self, key, value)
            else:
                logger.warning(f"Unknown config key: {key}")

    def _save_models_to_file(self, provider_name: str | None = None) -> None:
        if not self._config_file:
            logger.warning("Config file path not set")
            return

        user_config: dict[str, Any] = {}
        if self._config_file.exists():
            with self._config_file.open("rb") as file:
                user_config = tomli.load(file)
        user_config.setdefault("model_names", {})

        if provider_name:
            if provider_name in self.model_names:
                user_config["model_names"][provider_name] = self.model_names[provider_name].model_dump()
                self._modified_providers.add(provider_name)
        else:
            user_config["model_names"] = {provider: info.model_dump() for provider, info in self.model_names.items()}
            self._user_modified_fields.add("model_names")

        with self._config_file.open("wb") as file:
            tomli_w.dump(user_config, file)

    def get_custom_providers(self) -> dict[str, ChatModelProvider]:
        return {provider: info for provider, info in self.model_names.items() if info.custom}

    def _save_custom_providers(self) -> None:
        if not self._config_file:
            logger.warning("Config file path not set")
            return

        custom_config_file = self._config_file.parent / "custom_providers.toml"
        custom_providers = self.get_custom_providers()
        custom_config: dict[str, Any] = {}
        if custom_providers:
            custom_config["model_names"] = {provider: info.model_dump() for provider, info in custom_providers.items()}

        custom_config_file.parent.mkdir(parents=True, exist_ok=True)
        with custom_config_file.open("wb") as file:
            tomli_w.dump(custom_config, file)

    def add_custom_provider(self, provider_id: str, provider_data: dict[str, Any]) -> bool:
        if provider_id in self.model_names:
            logger.error(f"Provider ID already exists: {provider_id}")
            return False
        payload = dict(provider_data or {})
        env_value = payload.get("env")
        if isinstance(env_value, str) and env_value.startswith("${") and env_value.endswith("}"):
            payload["env"] = env_value[2:-1]
        payload["custom"] = True
        self.model_names[provider_id] = ChatModelProvider(**payload)
        self._save_custom_providers()
        self._handle_environment()
        return True

    def update_custom_provider(self, provider_id: str, provider_data: dict[str, Any]) -> bool:
        if provider_id not in self.model_names:
            logger.error(f"Provider not found: {provider_id}")
            return False
        if not self.model_names[provider_id].custom:
            logger.error(f"Cannot update non-custom provider: {provider_id}")
            return False

        payload = dict(provider_data or {})
        env_value = payload.get("env")
        if isinstance(env_value, str) and env_value.startswith("${") and env_value.endswith("}"):
            payload["env"] = env_value[2:-1]
        payload["custom"] = True
        self.model_names[provider_id] = ChatModelProvider(**payload)
        self._save_custom_providers()
        self._handle_environment()
        return True

    def delete_custom_provider(self, provider_id: str) -> bool:
        if provider_id not in self.model_names:
            logger.error(f"Provider not found: {provider_id}")
            return False
        if not self.model_names[provider_id].custom:
            logger.error(f"Cannot delete non-custom provider: {provider_id}")
            return False

        del self.model_names[provider_id]
        self._save_custom_providers()
        self._handle_environment()
        return True


config = Config()
