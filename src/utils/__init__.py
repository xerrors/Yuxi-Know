import time
import random
import os
from src.utils.logging_config import logger

def is_text_pdf(pdf_path):
    import fitz
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    if total_pages == 0:
        return False
        
    text_pages = 0
    for page_num in range(total_pages):
        page = doc.load_page(page_num)
        text = page.get_text()
        if text.strip():  # 检查是否有文本内容
            text_pages += 1
    
    # 计算有文本内容的页面比例
    text_ratio = text_pages / total_pages
    # 如果超过50%的页面有文本内容，则认为是文本PDF
    return text_ratio > 0.5

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