from core import DataBaseManager
from core.retriever import Retriever
from models import select_model
from config import Config
from utils import setup_logger

logger = setup_logger("Startup")


class Startup:
    def __init__(self):
        self.config = Config("config/base.yaml")
        self.model = select_model(self.config)
        self.dbm = DataBaseManager(self.config)
        self.retriever = Retriever(self.config, self.dbm, self.model)

    def restart(self):
        logger.info("Restarting...")
        self.model = select_model(self.config)
        self.dbm = DataBaseManager(self.config)
        self.retriever = Retriever(self.config, self.dbm, self.model)
        logger.info("Restarted")


startup = Startup()