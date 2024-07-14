import logging
from datetime import datetime


# DATETIME = datetime.now().strftime('%Y-%m-%d-%H%M%S')
DATETIME = "debug" # 为了方便，调试的时候输出到 debug.log 文件

def setup_logger(name, log_file=None, level=logging.DEBUG, console=True):

    if log_file is None:
        log_file = f'output/log/project-{DATETIME}.log'


    """Function to setup logger with the given name and log file."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # File handler for logging to a file
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)

    # Formatter for the logs
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
logger = setup_logger('Athena')

# If you want to disable logging from external libraries
# logging.getLogger('some_external_library').setLevel(logging.CRITICAL)
