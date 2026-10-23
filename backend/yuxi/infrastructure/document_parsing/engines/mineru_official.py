"""
MinerU Official 解析器

使用 MinerU 官方云服务 API 进行文档解析
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

from yuxi.infrastructure.document_parsing import DocumentParserException
from yuxi.infrastructure.document_parsing.artifacts import extract_markdown_archive
from yuxi.infrastructure.document_parsing.engines import DocumentEngine
from yuxi.infrastructure.observability.logging import logger
from yuxi.shared.hashing import hashstr


class MinerUOfficialParser(DocumentEngine):
    """MinerU 官方 API 解析器"""

    engine_id = "mineru_official"

    def __init__(self, api_key: str | None = None, api_base: str | None = None, model_version: str = "pipeline"):
        """使用配置凭据与默认模型初始化，单次解析参数优先。"""

        self.api_key = api_key or os.getenv("MINERU_API_KEY")
        if not self.api_key:
            raise DocumentParserException("MINERU_API_KEY 环境变量未设置", "mineru_official", "missing_api_key")

        self.api_base = (api_base or "https://mineru.net/api/v4").rstrip("/")
        self.model_version = model_version
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def check_health(self) -> dict[str, Any]:
        """报告凭证配置状态，避免健康检查创建真实解析任务。"""

        return {
            "status": "configured",
            "message": "MinerU 官方 API Key 已配置，将在解析时验证",
            "details": {"api_base": self.api_base},
        }

    def process_file(self, file_path: str, output_dir: Path, params: dict[str, Any] | None = None) -> str:
        """
        使用 MinerU 官方 API 处理文件

        Args:
            file_path: 本地文件路径
            params: 处理参数
                - is_ocr: 是否启用 OCR (默认: True)
                - enable_formula: 是否启用公式识别 (默认: True)
                - enable_table: 是否启用表格识别 (默认: True)
                - language: 文档语言 (默认: "ch")
                - page_ranges: 页码范围 (默认: None)
                - model_version: 模型版本 "pipeline" 或 "vlm" (默认使用实例配置)

        Returns:
            str: 提取的 Markdown 文本
        """
        if not os.path.exists(file_path):
            raise DocumentParserException(f"文件不存在: {file_path}", self.get_service_name(), "file_not_found")

        file_ext = Path(file_path).suffix.lower()
        if not self.supports_file_type(file_ext):
            raise DocumentParserException(f"不支持的文件类型: {file_ext}", self.get_service_name(), "unsupported_file_type")

        # 处理参数
        params = params or {}

        # 由于官方 API 不支持直接文件上传，我们需要先上传文件到可访问的 URL
        # 这里使用批量文件上传接口
        try:
            start_time = time.time()
            logger.info(f"MinerU Official 开始处理: {os.path.basename(file_path)}")

            # 步骤 1: 申请文件上传链接
            batch_id = self._upload_file(file_path, params)
            logger.info(f"文件上传成功，batch_id: {batch_id}")

            # 步骤 2: 轮询任务结果
            result = self._poll_batch_result(
                batch_id,
                max_wait_time=int(params.get("max_wait_seconds", 600)),
                poll_interval=float(params.get("poll_interval_seconds", 5)),
            )
            logger.info(f"任务完成，状态: {result['state']}")

            zip_url = result.get("full_zip_url")
            zip_path = self._download_zip(zip_url)
            try:
                processed = extract_markdown_archive(zip_path, output_dir)
                text = processed
            finally:
                try:
                    os.unlink(zip_path)
                except Exception:
                    pass

            processing_time = time.time() - start_time
            logger.info(f"MinerU Official 处理成功: {os.path.basename(file_path)} - {len(text)} 字符 ({processing_time:.2f}s)")

            return text

        except Exception as e:
            if isinstance(e, DocumentParserException):
                raise
            processing_time = time.time() - start_time
            error_msg = f"MinerU Official 处理失败: {str(e)}"
            logger.error(f"{error_msg} ({processing_time:.2f}s)")
            raise DocumentParserException(error_msg, self.get_service_name(), "processing_failed")

    def _upload_file(self, file_path: str, params: dict[str, Any]) -> str:
        """上传文件并返回 batch_id"""
        filename = os.path.basename(file_path)

        data_id = params.get("data_id", filename)
        if len(data_id) > 30:
            data_id = data_id[:30] + "_" + hashstr(data_id, length=8)

        upload_data = {
            "model_version": params.get("model_version", self.model_version),
            "enable_formula": params.get("enable_formula", True),
            "enable_table": params.get("enable_table", True),
            "language": params.get("language", "ch"),
            "files": [
                {
                    "name": filename,
                    "is_ocr": params.get("is_ocr", True),
                    "data_id": data_id,
                    "page_ranges": params.get("page_ranges"),
                }
            ],
        }

        # 申请上传链接
        response = requests.post(f"{self.api_base}/file-urls/batch", headers=self.headers, json=upload_data, timeout=30)

        if response.status_code != 200:
            raise DocumentParserException(f"申请上传链接失败: HTTP {response.status_code}", self.get_service_name(), "upload_url_failed")

        result = response.json()
        if result.get("code") != 0:
            error_msg = result.get("msg", "未知错误")
            raise DocumentParserException(
                f"申请上传链接失败: {error_msg}",
                self.get_service_name(),
                f"api_error_{result.get('code', 'unknown')}",
            )

        batch_id = result["data"]["batch_id"]
        upload_urls = result["data"]["file_urls"]

        if not upload_urls:
            raise DocumentParserException("未获取到文件上传链接", self.get_service_name(), "no_upload_url")

        # 上传文件
        upload_url = upload_urls[0]
        with open(file_path, "rb") as f:
            upload_response = requests.put(upload_url, data=f, timeout=60)

        if upload_response.status_code != 200:
            raise DocumentParserException(
                f"文件上传失败: HTTP {upload_response.status_code}",
                self.get_service_name(),
                "file_upload_failed",
            )

        return batch_id

    def _poll_batch_result(
        self,
        batch_id: str,
        max_wait_time: int = 600,
        poll_interval: float = 5,
    ) -> dict[str, Any]:
        """轮询批量任务结果"""
        start_time = time.time()

        while time.time() - start_time < max_wait_time:
            response = requests.get(f"{self.api_base}/extract-results/batch/{batch_id}", headers=self.headers, timeout=30)

            if response.status_code != 200:
                raise DocumentParserException(
                    f"查询任务状态失败: HTTP {response.status_code}",
                    self.get_service_name(),
                    "status_query_failed",
                )

            result = response.json()
            if result.get("code") != 0:
                error_msg = result.get("msg", "未知错误")
                raise DocumentParserException(
                    f"查询任务状态失败: {error_msg}",
                    self.get_service_name(),
                    f"api_error_{result.get('code', 'unknown')}",
                )

            extract_results = result["data"].get("extract_result", [])
            if not extract_results:
                time.sleep(poll_interval)
                continue

            # 检查第一个文件的状态
            file_result = extract_results[0]
            state = file_result.get("state")

            if state == "done":
                return file_result
            elif state == "failed":
                err_msg = file_result.get("err_msg", "未知错误")
                raise DocumentParserException(f"文档解析失败: {err_msg}", self.get_service_name(), "parsing_failed")

            # 继续等待
            time.sleep(poll_interval)

        raise DocumentParserException("任务处理超时", self.get_service_name(), "timeout")

    def _download_zip(self, zip_url: str) -> str:
        """下载结果ZIP到临时文件并返回路径"""
        if not zip_url:
            raise DocumentParserException("未获取到结果下载链接", self.get_service_name(), "no_download_url")
        response = requests.get(zip_url, timeout=60)
        if response.status_code != 200:
            raise DocumentParserException(f"下载结果失败: HTTP {response.status_code}", self.get_service_name(), "download_failed")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
            tmp_file.write(response.content)
            tmp_file.flush()
            return tmp_file.name
