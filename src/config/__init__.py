import os
import json
import yaml
import logging

logger = logging.getLogger(__name__)


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
        self.filename = filename

        ### startup
        self.mode = "cli"
        self.stream = False

        self.load()
        self.handle_self()

    def handle_self(self):
        ### handle local model
        model_root_dir = os.getenv("MODEL_ROOT_DIR", "pretrained_models")
        for model, model_rel_path in self.model_local_paths.items():
            if not model_rel_path.startswith("/"):
                self.model_local_paths[model] = os.path.join(model_root_dir, model_rel_path)


    def load(self):
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
        if self.filename is not None:
            with open(self.filename, 'w') as f:
                json.dump(self, f, indent=4)
                logger.info(f"Config file {self.filename} saved")
