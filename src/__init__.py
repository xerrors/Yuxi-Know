from dotenv import load_dotenv

load_dotenv(".env", override=True)

import os  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from src.config import config as config  # noqa: E402

__version__ = "0.5.1"

if os.getenv("YUXI_SKIP_APP_INIT") != "1":
    from src.knowledge import graph_base as graph_base  # noqa: E402
    from src.knowledge import knowledge_base as knowledge_base  # noqa: E402

executor = ThreadPoolExecutor()  # noqa: E402


def get_version():
    """Return the Yuxi-Know version."""
    return __version__
