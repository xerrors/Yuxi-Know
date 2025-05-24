from dotenv import load_dotenv

load_dotenv("src/.env")

from concurrent.futures import ThreadPoolExecutor  # noqa: E402
executor = ThreadPoolExecutor()

from src.config import Config  # noqa: E402
config = Config()

from src.core import KnowledgeBase  # noqa: E402
knowledge_base = KnowledgeBase()

from src.core import GraphDatabase  # noqa: E402
graph_base = GraphDatabase()

from src.core.retriever import Retriever  # noqa: E402
retriever = Retriever()
