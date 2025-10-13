import json
import os
from pathlib import Path

import yaml

from src.utils.logging_config import logger


class SimpleConfig(dict):
    def __key(self, key):
        return "" if key is None else key  # 目前忘记了这里为什么要 lower 了，只能说配置项最好不要有大写的

    def __str__(self):
        return json.dumps(self)

    def __setattr__(self, key, value):
        self[self.__key(key)] = value

    def __getattr__(self, key):
        return self.get(self.__key(key))

    def __getitem__(self, key):
        return self.get(self.__key(key))

    def __setitem__(self, key, value):
        return super().__setitem__(self.__key(key), value)

    def __dict__(self):
        return {k: v for k, v in self.items()}

    def update(self, other):
        for key, value in other.items():
            self[key] = value


class Config(SimpleConfig):
    def __init__(self):
        super().__init__()
        self._config_items = {}
        self.save_dir = os.getenv("SAVE_DIR", "saves")
        self.filename = str(Path(f"{self.save_dir}/config/base.yaml"))
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)

        self._models_config_path: Path | None = os.getenv("OVERRIDE_DEFAULT_MODELS_CONFIG_WITH")
        self._update_models_from_file()

        ### >>> 默认配置
        # 功能选项
        self.add_item("enable_reranker", default=False, des="是否开启重排序")
        self.add_item("enable_content_guard", default=False, des="是否启用内容审查")
        self.add_item("enable_content_guard_llm", default=False, des="是否启用LLM内容审查")
        self.add_item(
            "content_guard_llm_model", default="siliconflow/Qwen/Qwen3-235B-A22B-Instruct-2507", des="内容审查LLM模型"
        )
        # 默认智能体配置
        self.add_item("default_agent_id", default="", des="默认智能体ID")
        # 模型配置
        ## 注意这里是模型名，而不是具体的模型路径，默认使用 HuggingFace 的路径
        ## 如果需要自定义本地模型路径，则在 .env 中配置 MODEL_DIR
        self.add_item(
            "default_model",
            default=self._get_default_chat_model_spec(),
            des="默认对话模型",
        )
        self.add_item(
            "fast_model",
            default="siliconflow/THUDM/GLM-4-9B-0414",
            des="快速响应模型",
        )

        self.add_item(
            "embed_model",
            default="siliconflow/BAAI/bge-m3",
            des="Embedding 模型",
            choices=list(self.embed_model_names.keys()),
        )
        self.add_item(
            "reranker",
            default="siliconflow/BAAI/bge-reranker-v2-m3",
            des="Re-Ranker 模型",
            choices=list(self.reranker_names.keys()),
        )  # noqa: E501
        ### <<< 默认配置结束

        self.load()
        # 清理已废弃的配置项
        self.pop("model_provider", None)
        self.pop("model_name", None)
        self.handle_self()

    def add_item(self, key, default, des=None, choices=None):
        self.__setattr__(key, default)
        self._config_items[key] = {"default": default, "des": des, "choices": choices}

    def __dict__(self):
        blocklist = [
            "_config_items",
            "model_names",
            "model_provider_status",
            "embed_model_names",
            "reranker_names",
            "_models_config_path",
        ]
        return {k: v for k, v in self.items() if k not in blocklist}

    def _update_models_from_file(self):
        """
        从 models.yaml 或覆盖配置文件中更新 MODEL_NAMES
        """
        # 检查是否设置了覆盖配置文件的环境变量
        override_config_path = os.getenv("OVERRIDE_DEFAULT_MODELS_CONFIG_WITH")

        if override_config_path and os.path.exists(override_config_path):
            config_file = Path(override_config_path)
            logger.info(f"Using override models config from: {override_config_path}")
        else:
            config_file = Path("src/config/static/models.yaml")
            logger.info("Using default models config")

        self._models_config_path = str(config_file)

        with open(self._models_config_path, encoding="utf-8") as f:
            _models = yaml.safe_load(f)

        self.model_names = _models["MODEL_NAMES"]
        self.embed_model_names = _models["EMBED_MODEL_INFO"]
        self.reranker_names = _models["RERANKER_LIST"]

    def _save_models_to_file(self):
        """
        将当前模型配置写回模型配置文件
        """
        if self._models_config_path is None:
            self._models_config_path = str(Path("src/config/static/models.yaml"))

        models_payload = {
            "MODEL_NAMES": self.model_names,
            "EMBED_MODEL_INFO": self.embed_model_names,
            "RERANKER_LIST": self.reranker_names,
        }

        with open(self._models_config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(models_payload, f, indent=2, allow_unicode=True, sort_keys=False)

    def _get_default_chat_model_spec(self):
        """选择一个默认的聊天模型，优先使用 siliconflow 的默认模型"""
        preferred_provider = "siliconflow"
        provider_info = (self.model_names or {}).get(preferred_provider)
        if provider_info:
            default_model = provider_info.get("default")
            if default_model:
                return f"{preferred_provider}/{default_model}"

        for provider, info in (self.model_names or {}).items():
            default_model = info.get("default")
            if default_model:
                return f"{provider}/{default_model}"

        return ""

    def handle_self(self):
        """
        处理配置
        """
        self.model_dir = os.environ.get("MODEL_DIR", "")

        if self.model_dir:
            if os.path.exists(self.model_dir):
                logger.debug(
                    f"The model directory （{self.model_dir}） "
                    f"contains the following folders: {os.listdir(self.model_dir)}"
                )
            else:
                logger.warning(
                    f"Warning: The model directory （{self.model_dir}） does not exist. "
                    "If not configured, please ignore it. "
                    "If configured, please check if the configuration is correct; "
                    "For example, the mapping in the docker-compose file"
                )

        # 检查模型提供商的环境变量
        self.model_provider_status = {}
        for provider in self.model_names:
            env_var = self.model_names[provider]["env"]
            # 如果环境变量名为 NO_API_KEY，则认为总是可用
            if env_var == "NO_API_KEY":
                self.model_provider_status[provider] = True
            else:
                self.model_provider_status[provider] = bool(os.getenv(env_var))

        if os.getenv("TAVILY_API_KEY"):
            self.enable_web_search = True

        self.valuable_model_provider = [k for k, v in self.model_provider_status.items() if v]
        assert len(self.valuable_model_provider) > 0, "No model provider available, please check your `.env` file."

    def load(self):
        """根据传入的文件覆盖掉默认配置"""
        logger.info(f"Loading config from {self.filename}")
        if self.filename is not None and os.path.exists(self.filename):
            if self.filename.endswith(".json"):
                with open(self.filename) as f:
                    content = f.read()
                    if content:
                        local_config = json.loads(content)
                        self.update(local_config)
                    else:
                        print(f"{self.filename} is empty.")

            elif self.filename.endswith(".yaml"):
                with open(self.filename) as f:
                    content = f.read()
                    if content:
                        local_config = yaml.safe_load(content)
                        self.update(local_config)
                    else:
                        print(f"{self.filename} is empty.")
            else:
                logger.warning(f"Unknown config file type {self.filename}")

    def save(self):
        logger.info(f"Saving config to {self.filename}")
        if self.filename is None:
            logger.warning("Config file is not specified, save to default config/base.yaml")
            self.filename = os.path.join(self.save_dir, "config", "base.yaml")
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)

        if self.filename.endswith(".json"):
            with open(self.filename, "w+") as f:
                json.dump(self.__dict__(), f, indent=4, ensure_ascii=False)
        elif self.filename.endswith(".yaml"):
            with open(self.filename, "w+") as f:
                yaml.dump(self.__dict__(), f, indent=2, allow_unicode=True)
        else:
            logger.warning(f"Unknown config file type {self.filename}, save as json")
            with open(self.filename, "w+") as f:
                json.dump(self, f, indent=4)

        logger.info(f"Config file {self.filename} saved")

    def dump_config(self):
        return json.loads(str(self))


config = Config()
