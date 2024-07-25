import os
import json
import yaml
from utils.logging_config import setup_logger

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
        self.filename = filename or "config/base.yaml"
        self._config_items = {}

        ### >>> 默认配置
        # 可以在 config/base.yaml 中覆盖
        self.add_item("mode", default="cli", des="运行模式", choices=["cli", "api"])
        self.add_item("stream", default=True, des="是否开启流式输出")
        # 功能选项
        self.add_item("enable_query_rewrite", default=True, des="是否开启查询重写")
        self.add_item("enable_knowledge_base", default=True, des="是否开启知识库")
        self.add_item("enable_knowledge_graph", default=True, des="是否开启知识图谱")
        self.add_item("enable_search_engine", default=True, des="是否开启搜索引擎")

        # 模型配置
        ## 注意这里是模型名，而不是具体的模型路径，默认使用 HuggingFace 的路径
        ## 如果需要自定义路径，则在 config/base.yaml 中配置 model_local_paths
        self.add_item("model_provider", default="qianfan", des="模型提供商", choices=["qianfan", "vllm", "zhipu", "deepseek"])
        self.add_item("model_name", default=None, des="模型名称，为空则表示使用默认值")
        self.add_item("embed_model", default="bge-large-zh-v1.5", des="Embedding 模型", choices=["bge-large-zh-v1.5", "zhipu"])
        self.add_item("reranker", default="bge-reranker-v2-m3", des="Re-Ranker 模型", choices=["bge-reranker-v2-m3"])
        self.add_item("model_local_paths", default={}, des="本地模型路径")
        ### <<< 默认配置结束

        self.load()
        self.handle_self()

    def add_item(self, key, default, des=None, choices=None):
        self.__setattr__(key, default)
        self._config_items[key] = {
            "default": default,
            "des": des,
            "choices": choices
        }

    def handle_self(self):
        ### handle local model
        model_root_dir = os.getenv("MODEL_ROOT_DIR", "pretrained_models")
        if self.model_local_paths is not None:
            for model, model_rel_path in self.model_local_paths.items():
                # 如果 model_rel_path 不是绝对路径，那么拼接 model_root_dir
                if not model_rel_path.startswith("/"):
                    self.model_local_paths[model] = os.path.join(model_root_dir, model_rel_path)


    def load(self):
        """根据传入的文件覆盖掉默认配置"""
        logger.info(f"Loading config from {self.filename}")
        if self.filename is not None and os.path.exists(self.filename):
            if self.filename.endswith(".json"):
                with open(self.filename, 'r') as f:
                    content = f.read()
                    if content:
                        self.update(json.loads(content))
                    else:
                        print(f"{self.filename} is empty.")
            elif self.filename.endswith(".yaml"):
                with open(self.filename, 'r') as f:
                    content = f.read()
                    if content:
                        self.update(yaml.safe_load(content))
                    else:
                        print(f"{self.filename} is empty.")
            else:
                logger.warning(f"Unknown config file type {self.filename}")
        else:
            logger.warning(f"Config file {self.filename} not found")

    def save(self):
        logger.info(f"Saving config to {self.filename}")
        if self.filename is None:
            logger.warning("Config file is not specified, save to default config/base.yaml")
            self.filename = "config/base.yaml"

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