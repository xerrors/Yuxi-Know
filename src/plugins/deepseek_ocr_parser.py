"""
DeepSeek OCR Parser

Uses DeepSeek-OCR via SiliconFlow API for document parsing and OCR.
"""

import base64
import os
import re
import time
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import requests

from src.plugins.document_processor_base import BaseDocumentProcessor, DocumentParserException
from src.utils import logger


class DeepSeekOCRParser(BaseDocumentProcessor):
    """DeepSeek OCR Parser using SiliconFlow API"""

    # MIME type mapping for supported formats
    MIME_TYPE_MAP = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("SILICONFLOW_API_KEY")
        if not self.api_key:
            raise DocumentParserException(
                "SILICONFLOW_API_KEY environment variable not set", "deepseek_ocr", "missing_api_key"
            )

        self.api_url = "https://api.siliconflow.cn/v1/chat/completions"
        self.model = "deepseek-ai/DeepSeek-OCR"

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def get_service_name(self) -> str:
        return "deepseek_ocr"

    def get_supported_extensions(self) -> list[str]:
        """DeepSeek OCR supports PDF and images"""
        return list(self.MIME_TYPE_MAP.keys())

    def check_health(self) -> dict[str, Any]:
        """Check API availability and key validity"""
        try:
            # We can't easily "ping" without cost, but we can check if the model list is accessible
            models_url = "https://api.siliconflow.cn/v1/models"
            response = requests.get(models_url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "message": "DeepSeek OCR (SiliconFlow) is available",
                    "details": {"api_url": self.api_url},
                }
            elif response.status_code == 401:
                return {"status": "unhealthy", "message": "Invalid API Key", "details": {"error_code": "401"}}
            else:
                return {
                    "status": "unhealthy",
                    "message": f"API Error: {response.status_code}",
                    "details": {"status_code": response.status_code},
                }
        except Exception as e:
            return {"status": "unavailable", "message": f"Connection failed: {str(e)}", "details": {"error": str(e)}}

    def process_file(self, file_path: str, params: dict[str, Any] | None = None) -> str:
        """
        Process file using DeepSeek OCR via SiliconFlow
        """
        if not os.path.exists(file_path):
            raise DocumentParserException(f"File not found: {file_path}", self.get_service_name(), "file_not_found")

        file_ext = Path(file_path).suffix.lower()
        if not self.supports_file_type(file_ext):
            raise DocumentParserException(
                f"Unsupported file type: {file_ext}", self.get_service_name(), "unsupported_file_type"
            )

        try:
            start_time = time.time()
            logger.info(f"DeepSeek OCR starting: {os.path.basename(file_path)}")

            if file_ext == ".pdf":
                content = self._process_pdf(file_path)
            else:
                content = self._process_image(file_path)

            processing_time = time.time() - start_time
            logger.info(
                f"DeepSeek OCR finished: {os.path.basename(file_path)} - {len(content)} chars ({processing_time:.2f}s)"
            )

            return content

        except Exception as e:
            if isinstance(e, DocumentParserException):
                raise
            error_msg = f"DeepSeek OCR failed: {str(e)}"
            logger.error(error_msg)
            raise DocumentParserException(error_msg, self.get_service_name(), "processing_failed")

    def _process_pdf(self, file_path: str) -> str:
        """Process PDF by converting pages to images"""
        doc = fitz.open(file_path)
        try:
            full_text = []

            total_pages = len(doc)
            logger.info(f"Processing PDF with {total_pages} pages")

            for i, page in enumerate(doc):
                logger.debug(f"Processing page {i + 1}/{total_pages}")
                # Convert page to image (200 DPI for better quality)
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")

                page_text = self._call_api(img_bytes, "image/png")
                full_text.append(page_text)

            return "\n\n".join(full_text)
        finally:
            doc.close()

    def _process_image(self, file_path: str) -> str:
        """Process single image file"""
        mime_type = self._get_mime_type(file_path)
        with open(file_path, "rb") as f:
            file_content = f.read()
        return self._call_api(file_content, mime_type)

    def _call_api(self, data_bytes: bytes, mime_type: str) -> str:
        """Call SiliconFlow API"""
        encoded_string = base64.b64encode(data_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{encoded_string}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": "<image>\n<|grounding|>Convert the document to markdown. "},
                ],
            }
        ]

        payload = {"model": self.model, "messages": messages, "max_tokens": 4096, "temperature": 0.1}

        response = requests.post(self.api_url, headers=self.headers, json=payload, timeout=120)

        if response.status_code != 200:
            error_msg = f"API Error {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise DocumentParserException(error_msg, self.get_service_name(), f"http_{response.status_code}")

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # Clean up special tags like <|ref|>...<|/ref|> and <|det|>...<|/det|>
        content = re.sub(r"<\|ref\|>.*?<\|/ref\|>", "", content)
        content = re.sub(r"<\|det\|>.*?<\|/det\|>", "", content)
        # content = re.sub(r"<\|.*?\|>", "", content)

        return content.strip()

    def _get_mime_type(self, file_path: str) -> str:
        file_ext = Path(file_path).suffix.lower()
        return self.MIME_TYPE_MAP.get(file_ext, "image/jpeg")  # Default fallback
