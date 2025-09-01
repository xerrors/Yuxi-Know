import os
import time
import uuid
from argparse import ArgumentParser
from collections import defaultdict

import fitz  # fitz就是pip install PyMuPDF
import numpy as np  # Added import for numpy
from PIL import Image
from rapidocr_onnxruntime import RapidOCR
from tqdm import tqdm

from src.utils import logger

GOLBAL_STATE = {}

# OCR服务监控统计
OCR_STATS = {"requests": defaultdict(int), "failures": defaultdict(int), "service_status": defaultdict(str)}


def log_ocr_request(service_name: str, file_path: str, success: bool, processing_time: float, error_msg: str = None):
    """记录OCR请求统计信息"""
    # 更新统计
    OCR_STATS["requests"][service_name] += 1

    if not success:
        OCR_STATS["failures"][service_name] += 1
        OCR_STATS["service_status"][service_name] = "error"
        logger.error(f"OCR失败 - {service_name}: {os.path.basename(file_path)} - {error_msg}")
    else:
        OCR_STATS["service_status"][service_name] = "healthy"
        logger.info(f"OCR成功 - {service_name}: {os.path.basename(file_path)}")


def get_ocr_stats():
    """获取OCR服务统计信息"""
    stats = {}
    for service in OCR_STATS["requests"]:
        success_count = OCR_STATS["requests"][service] - OCR_STATS["failures"][service]
        success_rate = (success_count / OCR_STATS["requests"][service]) if OCR_STATS["requests"][service] > 0 else 0

        stats[service] = {
            "total_requests": OCR_STATS["requests"][service],
            "success_count": success_count,
            "failure_count": OCR_STATS["failures"][service],
            "success_rate": f"{success_rate:.2%}",
            "status": OCR_STATS["service_status"][service],
        }

    return stats


class OCRServiceException(Exception):
    """OCR服务异常"""

    def __init__(self, message, service_name=None, status_code=None):
        super().__init__(message)
        self.service_name = service_name
        self.status_code = status_code


class OCRPlugin:
    """OCR 插件"""

    def __init__(self, **kwargs):
        self.ocr = None
        self.det_box_thresh = kwargs.get("det_box_thresh", 0.3)
        self.model_dir_root = (
            os.getenv("MODEL_DIR") if not os.getenv("RUNNING_IN_DOCKER") else os.getenv("MODEL_DIR_IN_DOCKER")
        )

    def _check_rapid_ocr_availability(self):
        """检查RapidOCR模型是否可用"""
        try:
            model_dir = os.path.join(self.model_dir_root, "SWHL/RapidOCR")
            det_model_dir = os.path.join(model_dir, "PP-OCRv4/ch_PP-OCRv4_det_infer.onnx")
            rec_model_dir = os.path.join(model_dir, "PP-OCRv4/ch_PP-OCRv4_rec_infer.onnx")

            if not os.path.exists(model_dir):
                raise OCRServiceException(
                    f"模型目录不存在: {model_dir}。请下载 SWHL/RapidOCR 模型", "rapid_ocr", "model_not_found"
                )

            if not os.path.exists(det_model_dir) or not os.path.exists(rec_model_dir):
                raise OCRServiceException(
                    f"模型文件缺失。请确认模型文件完整: {det_model_dir}, {rec_model_dir}",
                    "rapid_ocr",
                    "model_incomplete",
                )

            return True

        except Exception as e:
            if isinstance(e, OCRServiceException):
                raise
            else:
                raise OCRServiceException(f"RapidOCR模型检查失败: {str(e)}", "rapid_ocr", "check_failed")

    def load_model(self):
        """加载 OCR 模型"""
        logger.info("加载 OCR 模型，仅在第一次调用时加载")

        # 先检查模型可用性
        self._check_rapid_ocr_availability()

        model_dir = os.path.join(self.model_dir_root, "SWHL/RapidOCR")
        det_model_dir = os.path.join(model_dir, "PP-OCRv4/ch_PP-OCRv4_det_infer.onnx")
        rec_model_dir = os.path.join(model_dir, "PP-OCRv4/ch_PP-OCRv4_rec_infer.onnx")

        try:
            self.ocr = RapidOCR(det_box_thresh=0.3, det_model_path=det_model_dir, rec_model_path=rec_model_dir)
            logger.info(f"OCR Plugin for det_box_thresh = {self.det_box_thresh} loaded.")
        except Exception as e:
            raise OCRServiceException(f"RapidOCR模型加载失败: {str(e)}", "rapid_ocr", "load_failed")

    def process_image(self, image, params=None):
        """
        对单张图像执行OCR并提取文本

        Args:
            image: 图像数据，支持多种格式：
                  - str: 图像文件路径
                  - PIL.Image: PIL图像对象
                  - numpy.ndarray: numpy图像数组
            params: 参数
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
            start_time = time.time()
            result, _ = self.ocr(image_path)
            processing_time = time.time() - start_time

            # 清理临时文件
            if is_temp_file and os.path.exists(image_path):
                os.remove(image_path)

            # 提取文本
            if result:
                text = "\n".join([line[1] for line in result])
                log_ocr_request("rapid_ocr", image_path, True, processing_time)
                return text
            else:
                log_ocr_request("rapid_ocr", image_path, False, processing_time, "OCR未能识别出文本内容")
                return ""

        except Exception as e:
            error_msg = f"OCR处理失败: {str(e)}"
            log_ocr_request("rapid_ocr", image_path, False, 0, error_msg)
            logger.error(error_msg)
            raise OCRServiceException(error_msg, "rapid_ocr", "processing_failed")

    def _create_temp_image_file(self, image):
        """
        将图像数据保存为临时文件

        Args:
            image: PIL.Image或numpy.ndarray格式的图像数据

        Returns:
            str: 临时文件路径
        """
        # 为临时文件创建目录（如果不存在）
        tmp_dir = os.path.join(os.getcwd(), "tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        # 生成临时文件路径
        temp_filename = f"ocr_temp_{uuid.uuid4().hex[:8]}.png"
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

    def process_pdf(self, pdf_path, params=None):
        """
        处理PDF文件并提取文本
        :param pdf_path: PDF文件路径
        :param params: 参数
        :return: 提取的文本
        """

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        try:
            images = []

            pdfDoc = fitz.open(pdf_path)
            totalPage = pdfDoc.page_count
            for pg in tqdm(range(totalPage), desc="to images", ncols=100):
                page = pdfDoc[pg]
                rotate, zoom_x, zoom_y = 0, 2, 2
                mat = fitz.Matrix(zoom_x, zoom_y).prerotate(rotate)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img_pil)

            # 处理每个图像并合并文本
            all_text = []
            for img_path in tqdm(images, desc="to txt", ncols=100):
                text = self.process_image(img_path)
                all_text.append(text)

            logger.debug(f"PDF OCR result: {all_text[:50]}(...) total {len(all_text)} pages.")
            return "\n\n".join(all_text)

        except Exception as e:
            logger.error(f"PDF processing error: {str(e)}")
            return ""

    def process_file_mineru(self, file_path, params=None):
        """
        使用Mineru OCR处理文件
        :param file_path: 文件路径
        :param params: 参数
        :return: 提取的文本
        """
        import requests

        from .mineru import parse_doc

        mineru_ocr_uri = os.getenv("MINERU_OCR_URI", "http://localhost:30000")
        mineru_ocr_uri_health = f"{mineru_ocr_uri}/health"

        try:
            # 健康检查
            health_check_response = requests.get(mineru_ocr_uri_health, timeout=5)
            if health_check_response.status_code != 200:
                error_detail = "Unknown error"
                try:
                    error_detail = health_check_response.json()
                except Exception:
                    error_detail = health_check_response.text

                raise OCRServiceException(
                    f"MinerU OCR服务健康检查失败: {error_detail}", "mineru_ocr", "health_check_failed"
                )

        except Exception as e:
            if isinstance(e, OCRServiceException):
                raise
            raise OCRServiceException(f"MinerU OCR服务检查失败: {str(e)}", "mineru_ocr", "service_error")

        try:
            start_time = time.time()
            file_path_list = [file_path]
            output_dir = os.path.join(os.getcwd(), "tmp", "mineru_ocr")

            text = parse_doc(file_path_list, output_dir, backend="vlm-sglang-client", server_url=mineru_ocr_uri)[0]

            processing_time = time.time() - start_time
            log_ocr_request("mineru_ocr", file_path, True, processing_time)

            logger.debug(f"Mineru OCR result: {text[:50]}(...) total {len(text)} characters.")
            return text

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"MinerU OCR处理失败: {str(e)}"
            log_ocr_request("mineru_ocr", file_path, False, processing_time, error_msg)

            raise OCRServiceException(error_msg, "mineru_ocr", "processing_failed")

    def process_file_paddlex(self, pdf_path, params=None):
        """
        使用Paddlex OCR处理PDF文件
        :param pdf_path: PDF文件路径
        :param params: 参数
        :return: 提取的文本
        """
        from .paddlex import analyze_document, check_paddlex_health

        paddlex_uri = os.getenv("PADDLEX_URI", "http://localhost:8080")

        try:
            # 健康检查
            health_check_response = check_paddlex_health(paddlex_uri)
            if not health_check_response.ok:
                error_detail = "Unknown error"
                try:
                    error_detail = health_check_response.json()
                except Exception:
                    error_detail = health_check_response.text

                raise OCRServiceException(
                    f"PaddleX OCR服务健康检查失败: {error_detail}", "paddlex_ocr", "health_check_failed"
                )
        except Exception as e:
            if isinstance(e, OCRServiceException):
                raise
            raise OCRServiceException(f"PaddleX OCR服务检查失败: {str(e)}", "paddlex_ocr", "service_error")

        try:
            start_time = time.time()
            result = analyze_document(pdf_path, base_url=paddlex_uri)
            processing_time = time.time() - start_time

            if not result["success"]:
                error_msg = f"PaddleX OCR处理失败: {result['error']}"
                log_ocr_request("paddlex_ocr", pdf_path, False, processing_time, error_msg)

                raise OCRServiceException(error_msg, "paddlex_ocr", "processing_failed")

            log_ocr_request("paddlex_ocr", pdf_path, True, processing_time)
            return result["full_text"]

        except Exception as e:
            if isinstance(e, OCRServiceException):
                raise
            processing_time = time.time() - start_time if "start_time" in locals() else 0
            error_msg = f"PaddleX OCR处理失败: {str(e)}"
            log_ocr_request("paddlex_ocr", pdf_path, False, processing_time, error_msg)

            raise OCRServiceException(error_msg, "paddlex_ocr", "processing_failed")


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
    parser.add_argument("--pdf-path", type=str, required=True, help="Path to the PDF file")
    parser.add_argument("--return-text", action="store_true", help="Return the extracted text")
    args = parser.parse_args()

    ocr = OCRPlugin()
    text = ocr.process_pdf(args.pdf_path)
    print(text)
