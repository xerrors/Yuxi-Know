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


class Config(SimpleConfig):

    def __init__(self, filename=None):
        super().__init__()
        self.filename = filename or "config/base.yaml"

        ### >>> 默认配置
        # 可以在 config/base.yaml 中覆盖
        self.mode = "cli"
        self.stream = True

        # 功能选项
        self.enable_query_rewrite = True
        self.enable_knowledge_base = True
        self.enable_knowledge_graph = True
        self.enable_search_engine = True

        # 模型配置
        ## 注意这里是模型名，而不是具体的模型路径，默认使用 HuggingFace 的路径
        ## 如果需要自定义路径，则在 config/base.yaml 中配置 model_local_paths
        self.model_provider = "qianfan"
        self.model_name = None # 默认使用 provider 的默认模型
        self.embed_model = "bge-large-zh-v1.5"
        self.reranker = "bge-reranker-v2-m3"
        ### <<< 默认配置结束

        self.load()
        self.handle_self()

    def handle_self(self):
        ### handle local model
        model_root_dir = os.getenv("MODEL_ROOT_DIR", "pretrained_models")
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
                    self.update(json.load(f))
            elif self.filename.endswith(".yaml"):
                with open(self.filename, 'r') as f:
                    self.update(yaml.safe_load(f))
        else:
            logger.warning(f"Config file {self.filename} not found")

    def save(self):
        logger.info(f"Saving config to {self.filename}")
        if self.filename is None:
            logger.warning("Config file is not specified, save to default config/base.yaml")
            self.filename = "config/base.yaml"

        if self.filename.endswith(".json"):
            with open(self.filename, 'w+') as f:
                json.dump(self, f, indent=4, ensure_ascii=False)
        elif self.filename.endswith(".yaml"):
            with open(self.filename, 'w+') as f:
                yaml.dump(self, f, indent=2)
        else:
            logger.warning(f"Unknown config file type {self.filename}, save as json")
            with open(self.filename, 'w+') as f:
                json.dump(self, f, indent=4)

        logger.info(f"Config file {self.filename} saved")