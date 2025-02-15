import os
from src.core import DataBaseManager
from src.core.retriever import Retriever
from src.models import select_model
from src.config import Config
from src.utils import setup_logger

logger = setup_logger("Startup")


class Startup:
    def __init__(self):
        self.config = Config("config/base.yaml")
        self._check_environment()
        self.start()

    def _check_environment(self):
        """检查必要的环境变量"""
        required_vars = {
            "zhipu": ["ZHIPUAI_API_KEY"],
            "openai": ["OPENAI_API_KEY"],
            "deepseek": ["DEEPSEEK_API_KEY"],
        }
        
        provider = self.config.model_provider
        if provider in required_vars:
            missing = [var for var in required_vars[provider] if not os.getenv(var)]
            if missing:
                logger.error(f"Missing required environment variables for {provider}: {missing}")
                raise ValueError(f"Missing required environment variables: {missing}")
                
        if self.config.enable_web_search and not os.getenv("TAVILY_API_KEY"):
            logger.warning("TAVILY_API_KEY not set, web search will be disabled")

    def start(self):
        self.model = select_model(self.config)
        self.dbm = DataBaseManager(self.config)
        self.retriever = Retriever(self.config, self.dbm, self.model)

    def restart(self):
        logger.info("Restarting...")
        self.start()
        logger.info("Restarted")


startup = Startup()