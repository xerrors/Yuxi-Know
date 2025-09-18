from dotenv import load_dotenv

load_dotenv("src/.env", override=True)

from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from src.config import config  # noqa: E402
from src.knowledge import knowledge_base, graph_base  # noqa: E402


executor = ThreadPoolExecutor()
