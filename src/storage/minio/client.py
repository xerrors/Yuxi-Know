"""
MinIO 存储客户端
简化的 MinIO 对象存储操作
"""

import os
import uuid
from io import BytesIO

from minio import Minio
from minio.error import S3Error
from src.utils import logger


class StorageError(Exception):
    """存储相关异常基类"""

    pass


class UploadResult:
    """简化的上传结果"""

    def __init__(self, url: str, bucket_name: str, object_name: str):
        self.url = url
        self.bucket_name = bucket_name
        self.object_name = object_name


class MinIOClient:
    """
    简化的 MinIO 客户端类
    """

    def __init__(self):
        """初始化 MinIO 客户端"""
        self.endpoint = os.getenv("MINIO_URI", "http://milvus-minio:9000")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self._client = None

        # 设置公开访问端点
        if os.getenv("RUNNING_IN_DOCKER"):
            host_ip = os.getenv("HOST_IP", "localhost")
            self.public_endpoint = f"{host_ip}:9000"
        else:
            self.public_endpoint = "localhost:9000"

    @property
    def client(self) -> Minio:
        """获取 MinIO 客户端实例"""
        if self._client is None:
            endpoint = self.endpoint
            if "://" in endpoint:
                endpoint = endpoint.split("://")[-1]

            self._client = Minio(
                endpoint=endpoint, access_key=self.access_key, secret_key=self.secret_key, secure=False
            )
        return self._client

    def ensure_bucket_exists(self, bucket_name: str) -> bool:
        """确保存储桶存在"""
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info(f"存储桶 '{bucket_name}' 已创建")
                return True
            return True
        except S3Error as e:
            logger.error(f"存储桶 '{bucket_name}' 错误: {e}")
            raise StorageError(f"Error with bucket '{bucket_name}': {e}")

    def upload_file(
        self, bucket_name: str, object_name: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> UploadResult:
        """上传文件到 MinIO"""
        try:
            self.ensure_bucket_exists(bucket_name)

            data_stream = BytesIO(data)
            result = self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data_stream,
                length=len(data),
                content_type=content_type,
            )

            assert result is not None
            url = f"http://{self.public_endpoint}/{bucket_name}/{object_name}"

            return UploadResult(url, bucket_name, object_name)

        except S3Error as e:
            error_msg = f"上传文件 '{object_name}' 失败: {e}"
            logger.error(error_msg)
            raise StorageError(error_msg)

    def upload_file_from_path(self, bucket_name: str, object_name: str, file_path: str) -> UploadResult:
        """从文件路径上传文件"""
        try:
            with open(file_path, "rb") as file_data:
                data = file_data.read()

            # 猜测内容类型
            content_type = self._guess_content_type(object_name)

            return self.upload_file(bucket_name, object_name, data, content_type)

        except FileNotFoundError:
            raise StorageError(f"文件 '{file_path}' 不存在")
        except Exception as e:
            raise StorageError(f"从路径上传文件失败: {e}")

    def _guess_content_type(self, object_name: str) -> str:
        """根据文件名猜测 MIME 类型"""
        ext = object_name.split(".")[-1].lower()
        content_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "pdf": "application/pdf",
            "txt": "text/plain",
            "json": "application/json",
            "html": "text/html",
            "css": "text/css",
            "js": "application/javascript",
        }
        return content_types.get(ext, "application/octet-stream")

    def download_file(self, bucket_name: str, object_name: str) -> bytes:
        """下载文件"""
        try:
            response = self.client.get_object(bucket_name, object_name)
            data = response.read()
            response.close()
            logger.info(f"成功下载 '{object_name}' 从存储桶 '{bucket_name}'")
            return data

        except S3Error as e:
            if "NoSuchKey" in str(e):
                raise StorageError(f"对象 '{object_name}' 在存储桶 '{bucket_name}' 中不存在")
            raise StorageError(f"下载文件失败: {e}")

    def delete_file(self, bucket_name: str, object_name: str) -> bool:
        """删除文件"""
        try:
            self.client.remove_object(bucket_name, object_name)
            logger.info(f"成功删除 '{object_name}' 从存储桶 '{bucket_name}'")
            return True

        except S3Error as e:
            if "NoSuchKey" in str(e):
                logger.warning(f"要删除的对象 '{object_name}' 不存在")
                return False
            raise StorageError(f"删除文件失败: {e}")

    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        """检查文件是否存在"""
        try:
            self.client.stat_object(bucket_name, object_name)
            return True
        except S3Error as e:
            if "NoSuchKey" in str(e):
                return False
            raise StorageError(f"检查文件存在性失败: {e}")


# 全局客户端实例
_default_client = None


def get_minio_client() -> MinIOClient:
    """获取 MinIO 客户端实例"""
    global _default_client
    if _default_client is None:
        _default_client = MinIOClient()
    return _default_client


def upload_image_to_minio(data: bytes, file_extension: str = "jpg") -> str:
    """
    上传图片到 MinIO（保持向后兼容）

    Args:
        data: 图片数据
        file_extension: 文件扩展名

    Returns:
        str: 图片访问 URL
    """
    client = get_minio_client()
    file_name = f"{uuid.uuid4()}.{file_extension}"
    result = client.upload_file(
        bucket_name="generated-images", object_name=file_name, data=data, content_type=f"image/{file_extension}"
    )
    return result.url
