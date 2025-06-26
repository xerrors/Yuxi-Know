from dotenv import load_dotenv

load_dotenv("src/.env")

from concurrent.futures import ThreadPoolExecutor  # noqa: E402
executor = ThreadPoolExecutor()

from src.config import Config  # noqa: E402
config = Config()

from src.core.lightrag_based_kb import LightRagBasedKB  # noqa: E402
knowledge_base = LightRagBasedKB()

from src.core import GraphDatabase  # noqa: E402
graph_base = GraphDatabase()
