import logging
import os
from datetime import datetime

import pytz
from colorlog import ColoredFormatter

DATETIME = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d-%H%M%S')
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

    # 文件日志（无颜色）
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(level)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # 控制台日志（有颜色）
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        color_formatter = ColoredFormatter(
            "%(log_color)s%(asctime)s - %(levelname)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )
        console_handler.setFormatter(color_formatter)
        logger.addHandler(console_handler)

    return logger


# Setup the root logger
logger = setup_logger('Yuxi')

# If you want to disable logging from external libraries
# logging.getLogger('some_external_library').setLevel(logging.CRITICAL)
