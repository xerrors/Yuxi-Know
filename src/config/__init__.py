import os
import json
import yaml
from src.utils.logging_config import setup_logger

logger = setup_logger("Config")


class SimpleConfig(dict):

    def __key(self, key):
        return "" if key is None else key.lower()

    def __str__(self):
        return json.dumps(self)

    def __setattr__(self, key, value):
        self[self.__key(key)] = value

    def __getattr__(self, key):
        return self.get(self.__key(key))

    def __getitem__(self, key):
        return super().get(self.__key(key))

    def __setitem__(self, key, value):
        return super().__setitem__(self.__key(key), value)

    def __dict__(self):
        return {k: v for k, v in self.items()}


class Config(SimpleConfig):

    def __init__(self, filename=None):
        super().__init__()
        self._config_items = {}

        ### >>> 默认配置
        # 可以在 config/base.yaml 中覆盖
        self.add_item("stream", default=True, des="是否开启流式输出")
        self.add_item("save_dir", default="saves", des="保存目录")
        # 功能选项
        self.add_item("enable_reranker", default=False, des="是否开启重排序")
        self.add_item("enable_knowledge_base", default=False, des="是否开启知识库")
        self.add_item("enable_knowledge_graph", default=False, des="是否开启知识图谱")
        self.add_item("enable_search_engine", default=False, des="是否开启搜索引擎")

        # 模型配置
        ## 注意这里是模型名，而不是具体的模型路径，默认使用 HuggingFace 的路径
        ## 如果需要自定义路径，则在 config/base.yaml 中配置 model_local_paths
        self.add_item("model_provider", default="zhipu", des="模型提供商", choices=list(MODEL_NAMES.keys()))
        self.add_item("model_name", default=None, des="模型名称")
        self.add_item("embed_model", default="zhipu-embedding-3", des="Embedding 模型", choices=list(EMBED_MODEL_INFO.keys()))
        self.add_item("reranker", default="bge-reranker-v2-m3", des="Re-Ranker 模型", choices=list(RERANKER_LIST.keys()))
        self.add_item("model_local_paths", default={}, des="本地模型路径")
        ### <<< 默认配置结束

        self.filename = filename or os.path.join(self.save_dir, "config", "config.yaml")
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)

        self.load()
        self.handle_self()

    def add_item(self, key, default, des=None, choices=None):
        self.__setattr__(key, default)
        self._config_items[key] = {
            "default": default,
            "des": des,
            "choices": choices
        }

    def __dict__(self):
        blocklist = [
            "_config_items",
            "model_names",
            "model_provider_status",
        ]
        return {k: v for k, v in self.items() if k not in blocklist}

    def handle_self(self):
        self.model_names = MODEL_NAMES
        model_provider_info = self.model_names.get(self.model_provider, {})

        if self.model_provider != "custom":
            if self.model_name not in model_provider_info["models"]:
                logger.warning(f"Model name {self.model_name} not in {self.model_provider}, using default model name")
                self.model_name = model_provider_info["default"]

            default_model_name = model_provider_info["default"]
            self.model_name = self.get("model_name") or default_model_name
        else:
            self.model_name = self.get("model_name")
            if self.model_name not in [item["custom_id"] for item in self.custom_models]:
                logger.warning(f"Model name {self.model_name} not in custom models, using default model name")
                self.model_name = self.custom_models[0]["custom_id"]

        self.model_provider_status = {}
        for provider in self.model_names:
            conds = [bool(os.getenv(_k)) for _k in self.model_names[provider]["env"]]
            self.model_provider_status[provider] = all(conds)

    def load(self):
        """根据传入的文件覆盖掉默认配置"""
        logger.info(f"Loading config from {self.filename}")
        if self.filename is not None and os.path.exists(self.filename):

            if self.filename.endswith(".json"):
                with open(self.filename, 'r') as f:
                    content = f.read()
                    if content:
                        local_config = json.loads(content)
                        self.update(local_config)
                    else:
                        print(f"{self.filename} is empty.")

            elif self.filename.endswith(".yaml"):
                with open(self.filename, 'r') as f:
                    content = f.read()
                    if content:
                        local_config = yaml.safe_load(content)
                        self.update(local_config)
                    else:
                        print(f"{self.filename} is empty.")
            else:
                logger.warning(f"Unknown config file type {self.filename}")

        else:
            logger.warning(f"\n\n{'='*70}\n{'Config file not found':^70}\n{'You can custum your config in `' + self.filename + '`':^70}\n{'='*70}\n\n")

    def save(self):
        logger.info(f"Saving config to {self.filename}")
        if self.filename is None:
            logger.warning("Config file is not specified, save to default config/base.yaml")
            self.filename = os.path.join(self.save_dir, "config", "config.yaml")
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)

        if self.filename.endswith(".json"):
            with open(self.filename, 'w+') as f:
                json.dump(self.__dict__(), f, indent=4, ensure_ascii=False)
        elif self.filename.endswith(".yaml"):
            with open(self.filename, 'w+') as f:
                yaml.dump(self.__dict__(), f, indent=2, allow_unicode=True)
        else:
            logger.warning(f"Unknown config file type {self.filename}, save as json")
            with open(self.filename, 'w+') as f:
                json.dump(self, f, indent=4)

        logger.info(f"Config file {self.filename} saved")

MODEL_NAMES = {
    "openai": {
        "name": "OpenAI",
        "url": "https://platform.openai.com/docs/models",
        "default": "gpt-3.5-turbo",
        "env": ["OPENAI_API_KEY"],
        "models": [
            "gpt-4",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-3.5-turbo"
        ]
    },

    # https://platform.deepseek.com/api-docs/zh-cn/pricing
    "deepseek": {
        "name": "DeepSeek",
        "url": "https://platform.deepseek.com/api-docs/zh-cn/pricing",
        "default": "deepseek-chat",
        "env": ["DEEPSEEK_API_KEY"],
        "models": [
            "deepseek-chat",
        ]
    },

    # https://open.bigmodel.cn/dev/api  glm-4-plus、glm-4-0520、glm-4 、glm-4-air、glm-4-airx、glm-4-long 、 glm-4-flashx 、 glm-4-flash
    "zhipu": {
        "name": "智谱AI (Zhipu)",
        "url": "https://open.bigmodel.cn/dev/api",
        "default": "glm-4-flash",
        "env": ["ZHIPUAI_API_KEY"],
        "models": [
            "glm-4",
            "glm-4-plus",
            "glm-4-air",
            "glm-4-airx",
            "glm-4-long",
            "glm-4-flashx",
            "glm-4-flash",
        ]
    },

    # {'ERNIE-4.0-8K-0104', 'ERNIE-Lite-8K-0308', 'ERNIE-Speed-128K', 'ERNIE-3.5-128K（预览版）', 'Yi-34B-Chat', 'ERNIE-4.0-8K-Preview-0518', 'ERNIE-Bot-4', 'ERNIE-3.5-128K', 'ChatGLM2-6B-32K', 'ERNIE-3.5-8K', 'EB-turbo-AppBuilder', 'ERNIE-Lite-AppBuilder-8K', 'ERNIE-4.0-8K-0329', 'AquilaChat-7B', 'Gemma-7B-it', 'Qianfan-Chinese-Llama-2-70B', 'Mixtral-8x7B-Instruct', 'Gemma-7B-It', 'ERNIE Speed-AppBuilder', 'ERNIE-Function-8K', 'ERNIE-4.0-8K-preview', 'ERNIE-Bot', 'Qianfan-BLOOMZ-7B-compressed', 'ERNIE-4.0-8K', 'BLOOMZ-7B', 'ERNIE-Character-8K', 'ERNIE-3.5-8K-0205', 'ERNIE-4.0-8K-0613', 'Llama-2-70B-Chat', 'ERNIE-Character-Fiction-8K', 'ERNIE-4.0-8K-Preview', 'ERNIE-3.5-8K-Preview', 'ERNIE-Speed', 'ERNIE-Tiny-8K', 'ERNIE-4.0-Turbo-8K-Preview', 'Meta-Llama-3-8B', 'ERNIE-4.0-8K-Latest', 'ERNIE 3.5', 'XuanYuan-70B-Chat-4bit', 'Llama-2-13B-Chat', 'ERNIE-Bot-turbo', 'ERNIE-3.5-8K-0613', 'ERNIE-Lite-AppBuilder-8K-0614', 'ERNIE-4.0-preview', 'Llama-2-7B-Chat', 'Qianfan-Chinese-Llama-2-13B', 'ERNIE-Bot-turbo-AI', 'Meta-Llama-3-70B', 'ERNIE-Functions-8K', 'ERNIE-Lite-8K-0922（原ERNIE-Bot-turbo-0922）', 'ERNIE Speed', 'ERNIE-3.5-preview', 'Qianfan-Chinese-Llama-2-7B', 'ERNIE-Speed-8K', 'ERNIE-Lite-8K-0922', 'ChatLaw', 'ERNIE-3.5-8K-0329', 'ERNIE-4.0-Turbo-8K', 'ERNIE-3.5-8K-preview', 'ERNIE-Lite-8K'}
    "qianfan": {
        "name": "百度千帆 (QianFan)",
        "url": "https://open.bigmodel.cn/dev/api",
        "default": "ERNIE-Speed",
        "env": ["QIANFAN_ACCESS_KEY", "QIANFAN_SECRET_KEY"],
        "models": [
            "ERNIE-Speed",
            "ERNIE-Speed-8K",
            "ERNIE-Speed-128K",
            "ERNIE-Tiny-8K",
            "ERNIE-Lite-8K",
            "ERNIE-4.0-8K-Latest",
        ]
    },

    # https://bailian.console.aliyun.com/?switchAgent=10226727&productCode=p_efm#/model-market
    "dashscope": {
        "name": "阿里百炼 (DashScope)",
        "url": "https://bailian.console.aliyun.com/?switchAgent=10226727&productCode=p_efm#/model-market",
        "default": "qwen2.5-72b-instruct",
        "env": ["DASHSCOPE_API_KEY"],
        "models": [
            "qwen-max-latest",
            "qwen-plus-latest",
            "qwen-long-latest",
            "qwen-turbo-latest",
            "qwen2.5-72b-instruct",
            "qwen2.5-32b-instruct",
            "qwen2.5-14b-instruct",
            "qwen2.5-7b-instruct",
            "qwen2.5-3b-instruct",
            "qwen2.5-1.5b-instruct",
            "qwen2.5-0.5b-instruct",
        ]
    },

    # https://cloud.siliconflow.cn/models
    "siliconflow": {
        "name": "SiliconFlow",
        "url": "https://cloud.siliconflow.cn/models",
        "default": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "env": ["SILICONFLOW_API_KEY"],
        "models": [
            "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "meta-llama/Meta-Llama-3.1-70B-Instruct",
            "meta-llama/Meta-Llama-3.1-405B-Instruct",
        ]
    },
}


EMBED_MODEL_INFO = {
    "bge-large-zh-v1.5": SimpleConfig({
        "name": "bge-large-zh-v1.5",
        "default_path": "BAAI/bge-large-zh-v1.5",
        "dimension": 1024,
        "query_instruction": "为这个句子生成表示以用于检索相关文章：",
    }),
    "zhipu-embedding-2": SimpleConfig({
        "name": "zhipu-embedding-2",
        "default_path": "embedding-2",
        "dimension": 1024,
    }),
    "zhipu-embedding-3": SimpleConfig({
        "name": "zhipu-embedding-3",
        "default_path": "embedding-3",
        "dimension": 2048,
    }),
}

RERANKER_LIST = {
    "bge-reranker-v2-m3": "BAAI/bge-reranker-v2-m3",
}