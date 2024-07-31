from src.core import DataBaseManager
from src.core.retriever import Retriever
from src.models import select_model
from src.config import Config
from src.utils import setup_logger

logger = setup_logger("Startup")


class Startup:
    def __init__(self):
        self.start()

    def start(self):
        self.config = Config()
        self.model = select_model(self.config)
        self.dbm = DataBaseManager(self.config)
        self.retriever = Retriever(self.config, self.dbm, self.model)

    def restart(self):
        logger.info("Restarting...")
        self.start()
        logger.info("Restarted")


startup = Startup()