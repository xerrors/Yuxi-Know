import os
from concurrent.futures import ThreadPoolExecutor

from src.core import DataBaseManager
from src.core.retriever import Retriever
from src.models import select_model
from src.config import Config
from src.utils import logger

# 创建线程池
executor = ThreadPoolExecutor()


class Startup:
    def __init__(self):
        self.start()

    def start(self):
        self.config = Config()
        self.model = select_model(self.config)
        self.dbm = DataBaseManager(self.config)
        self.retriever = Retriever(self.config, self.dbm, self.model)

        logger.info(f"Loading lite model: {self.config.model_name_lite}")
        self.model_lite = select_model(self.config,
                                       model_provider=self.config.model_provider_lite,
                                       model_name=self.config.model_name_lite)

    def restart(self):
        logger.info("Restarting...")
        self.start()
        logger.info("Restarted")


startup = Startup()