from dotenv import load_dotenv

load_dotenv("src/.env")

from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor()

from src.config import Config
config = Config()

from src.core import KnowledgeBase
knowledge_base = KnowledgeBase()

from src.core import GraphDatabase
graph_base = GraphDatabase()

from src.core.retriever import Retriever
retriever = Retriever()