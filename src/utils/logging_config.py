import logging
import os
from datetime import datetime


DATETIME = datetime.now().strftime('%Y-%m-%d-%H%M%S')
# DATETIME = "debug" # 为了方便，调试的时候输出到 debug.log 文件
LOG_FILE = f'saves/log/project-{DATETIME}.log'

def setup_logger(name, level=logging.DEBUG, console=True):
    os.makedirs("saves/log", exist_ok=True)

    """Function to setup logger with the given name and log file."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 清除已有的 Handler，防止重复添加
    if logger.hasHandlers():
        logger.handlers.clear()

    # File handler for logging to a file
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(level)

    # Formatter for the logs
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler for logging to the console (optional)
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


# Setup the root logger
logger = setup_logger('Yuxi')

# If you want to disable logging from external libraries
# logging.getLogger('some_external_library').setLevel(logging.CRITICAL)
