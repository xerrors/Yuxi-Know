"""日志适配、第三方 logging 桥接与进程级日志初始化。"""

import logging
import sys

from loguru import logger as loguru_logger

from yuxi.infrastructure.runtime_settings import get_runtime_dir
from yuxi.shared.datetime import shanghai_now

DATETIME = shanghai_now().strftime("%Y-%m-%d")
LOG_DIR = get_runtime_dir() / "logs"
LOG_FILE = str(LOG_DIR / f"yuxi-{DATETIME}.log")


class LoguruHandler(logging.Handler):
    """将 Python logging 桥接到 loguru 的 handler"""

    def emit(self, record: logging.LogRecord):
        level_map = {
            logging.DEBUG: "DEBUG",
            logging.INFO: "INFO",
            logging.WARNING: "WARNING",
            logging.ERROR: "ERROR",
            logging.CRITICAL: "CRITICAL",
        }
        level = level_map.get(record.levelno, "DEBUG")
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        loguru_logger.opt(depth=1, exception=record.exc_info).log(level, msg)


def _setup_logging_bridge():
    """配置 logging 到 loguru 的桥接，捕获第三方库日志"""
    loguru_handler = LoguruHandler()
    loguru_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    loguru_handler.setFormatter(formatter)

    for lib in ["httpx", "openai", "neo4j", "urllib3"]:
        lib_logger = logging.getLogger(lib)
        lib_logger.addHandler(loguru_handler)
        lib_logger.setLevel(logging.WARNING)
        lib_logger.propagate = False


def setup_logger(name, level="DEBUG", console=True):
    """使用 loguru 设置日志记录器"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 移除默认的 handler
    loguru_logger.remove()

    # 添加文件日志（无颜色）
    loguru_logger.add(
        LOG_FILE,
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} - {level} - {file}:{line} - {message}",
        encoding="utf-8",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        diagnose=False,
        enqueue=True,
    )

    # 添加控制台日志（有颜色）
    if console:
        loguru_logger.add(
            sys.stderr,
            level=level,
            format=("<green>{time:MM-DD HH:mm:ss}</green> <level>{level}</level> <cyan>{file}:{line}</cyan>: <level>{message}</level>"),
            colorize=True,
            diagnose=False,
            enqueue=True,
        )

    return loguru_logger


# 设置根日志记录器
logger = setup_logger("Yuxi")

# 初始化 logging 桥接
_setup_logging_bridge()

__all__ = ["logger"]


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )

    uvicorn_logger = logging.getLogger("uvicorn")
    logging.getLogger("uvicorn.access").handlers.clear()

    formatter = logging.Formatter(fmt="%(asctime)s %(levelname)s: %(message)s", datefmt="%m-%d %H:%M:%S")
    for handler in uvicorn_logger.handlers:
        handler.setFormatter(formatter)
