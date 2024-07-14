import os


class GraphBase:

    def __init__(self, config=None) -> None:
        self.config = config

        self._init_config(config)

    def _init_config(self, config):
        pass

