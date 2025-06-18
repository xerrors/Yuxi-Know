import os
import uuid
from pathlib import Path
from argparse import ArgumentParser

import fitz  # fitz就是pip install PyMuPDF
import numpy as np  # Added import for numpy
from PIL import Image
from tqdm import tqdm
from rapidocr_onnxruntime import RapidOCR

from src.utils import logger, is_text_pdf


GOLBAL_STATE = {}


class OCRPlugin:
    """OCR 插件"""

    def __init__(self, **kwargs):
        self.ocr = None
        self.det_box_thresh = kwargs.get('det_box_thresh', 0.3)

    def load_model(self):
        """加载 OCR 模型"""
        logger.info("加载 OCR 模型，仅在第一次调用时加载")
        model_dir = os.path.join(os.getenv("MODEL_DIR", ""), "SWHL/RapidOCR")
        det_model_dir = os.path.join(model_dir, "PP-OCRv4/ch_PP-OCRv4_det_infer.onnx")
        rec_model_dir = os.path.join(model_dir, "PP-OCRv4/ch_PP-OCRv4_rec_infer.onnx")
        assert os.path.exists(model_dir), (
            f"模型文件不存在，请下载 SWHL/RapidOCR 到 {model_dir}，"
            "并确认是否在 docker-compose.dev.yml 中添加 MODEL_DIR 环境变量"
        )
        self.ocr = RapidOCR(det_box_thresh=0.3, det_model_path=det_model_dir, rec_model_path=rec_model_dir)
        logger.info(f"OCR Plugin for det_box_thresh = {self.det_box_thresh} loaded.")

    def process_image(self, image):
        """
        对单张图像执行OCR并提取文本

        Args:
            image: 图像数据，支持多种格式：
                  - str: 图像文件路径
                  - PIL.Image: PIL图像对象
                  - numpy.ndarray: numpy图像数组

        Returns:
            str: 提取的文本内容
        """
        # 确保模型已加载
        if self.ocr is None:
            self.load_model()

        # 处理不同类型的输入图像
        try:
            if isinstance(image, str):
                # 图像路径直接传递给OCR处理
                image_path = image
                is_temp_file = False
            else:
                # 创建临时文件
                is_temp_file = True
                image_path = self._create_temp_image_file(image)

            # 执行 OCR
            result, _ = self.ocr(image_path)

            # 清理临时文件
            if is_temp_file and os.path.exists(image_path):
                os.remove(image_path)

            # 提取文本
            if result:
                text = '\n'.join([line[1] for line in result])
                return text
            else:
                logger.warning("OCR未能识别出文本内容")
                return ""

        except Exception as e:
            logger.error(f"OCR处理失败: {str(e)}")
            raise

    def _create_temp_image_file(self, image):
        """
        将图像数据保存为临时文件

        Args:
            image: PIL.Image或numpy.ndarray格式的图像数据

        Returns:
            str: 临时文件路径
        """
        # 为临时文件创建目录（如果不存在）
        tmp_dir = os.path.join(os.getcwd(), 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)

        # 生成临时文件路径
        temp_filename = f'ocr_temp_{uuid.uuid4().hex[:8]}.png'
        image_path = os.path.join(tmp_dir, temp_filename)

        # 根据图像类型保存文件
        if isinstance(image, Image.Image):
            # 保存PIL图像对象到临时文件
            image.save(image_path)
        elif isinstance(image, np.ndarray):
            # 将numpy数组转换为PIL图像并保存
            Image.fromarray(image).save(image_path)
        else:
            raise ValueError("不支持的图像类型，必须是PIL.Image或numpy数组")

        return image_path

    def process_pdf(self, pdf_path):
        """
        处理PDF文件并提取文本
        :param pdf_path: PDF文件路径
        :return: 提取的文本
        """

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        try:
            # 检查是否为文本PDF，可能会出现错误，比如每一页都有可读取的水印文字，但是内容本身是扫描件，需要使用OCR处理
            # if is_text_pdf(pdf_path):
            #     from src.core.indexing import pdfreader
            #     logger.info("PDF file is text, use llama_index.readers.file to read")
            #     return pdfreader(pdf_path)

            images = []

            pdfDoc = fitz.open(pdf_path)
            totalPage = pdfDoc.page_count
            for pg in tqdm(range(totalPage), desc='to images', ncols=100):
                page = pdfDoc[pg]
                rotate, zoom_x, zoom_y = 0, 2, 2
                mat = fitz.Matrix(zoom_x, zoom_y).prerotate(rotate)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img_pil)

            # 处理每个图像并合并文本
            all_text = []
            for img_path in tqdm(images, desc='to txt', ncols=100):
                text = self.process_image(img_path)
                all_text.append(text)

            return '\n\n'.join(all_text)

        except Exception as e:
            logger.error(f"PDF processing error: {str(e)}")
            return ""

    def process_pdf_mineru(self, pdf_path):
        """
        使用Mineru OCR处理PDF文件
        :param pdf_path: PDF文件路径
        :return: 提取的文本
        """
        mineru_ocr_uri = os.getenv("MINERU_OCR_URI", "http://localhost:30000")
        mineru_ocr_uri_health = f"{mineru_ocr_uri}/health"
        import requests
        import json
        from .mineru import parse_doc

        health_check_response = requests.get(mineru_ocr_uri_health, timeout=5)
        if health_check_response.status_code != 200:
            logger.error(f"Mineru OCR service health check failed with {mineru_ocr_uri_health}: {health_check_response.json()}")
            raise RuntimeError("Mineru OCR service health check failed. Please check the log use `docker logs mineru-api`")

        pdf_path_list = [pdf_path]
        output_dir = os.path.join(os.getcwd(), "tmp", "mineru_ocr")

        pdf_text = parse_doc(pdf_path_list, output_dir,
                         backend="vlm-sglang-client",
                         server_url=mineru_ocr_uri)[0]

        logger.debug(f"Mineru OCR result: {pdf_text[:50]}(...) total {len(pdf_text)} characters.")
        return pdf_text

def get_state(task_id):
    return GOLBAL_STATE.get(task_id, {})

def plainreader(file_path):
    """读取普通文本文件并返回text文本"""
    assert os.path.exists(file_path), "File not found"

    with open(file_path) as f:
        text = f.read()
    return text



if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('--pdf-path', type=str, required=True, help='Path to the PDF file')
    parser.add_argument('--return-text', action='store_true', help='Return the extracted text')
    args = parser.parse_args()

    ocr = OCRPlugin()
    text = ocr.process_pdf(args.pdf_path)
    print(text)
