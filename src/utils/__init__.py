import time
import random
import os
from src.utils.logging_config import logger

def is_text_pdf(pdf_path):
    import fitz
    doc = fitz.open(pdf_path)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text()
        if text.strip():  # 检查是否有文本内容
            return True
    return False

def hashstr(input_string, length=8, with_salt=False):
    import hashlib
    # 添加时间戳作为干扰
    if with_salt:
        input_string += str(time.time() + random.random())

    hash = hashlib.md5(str(input_string).encode()).hexdigest()
    return hash[:length]


def get_docker_safe_url(base_url):
    if os.getenv("RUNNING_IN_DOCKER") == "true":
        # 替换所有可能的本地地址形式
        base_url = base_url.replace("http://localhost", "http://host.docker.internal")
        base_url = base_url.replace("http://127.0.0.1", "http://host.docker.internal")
        logger.info(f"Running in docker, using {base_url} as base url")
    return base_url