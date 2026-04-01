from dotenv import load_dotenv

load_dotenv(".env", override=True)

from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from yuxi.config import config as config  # noqa: E402

__version__ = "0.6.0"

from yuxi.knowledge import graph_base as graph_base  # noqa: E402
from yuxi.knowledge import knowledge_base as knowledge_base  # noqa: E402

executor = ThreadPoolExecutor()  # noqa: E402


def get_version():
    """Return the Yuxi version."""
    return __version__
