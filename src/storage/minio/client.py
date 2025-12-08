"""
MinIO 存储客户端
简化的 MinIO 对象存储操作
"""

import asyncio
import json
import os
from datetime import timedelta
from io import BytesIO

from urllib3 import BaseHTTPResponse

from minio import Minio
from minio.error import S3Error
from src.utils import logger


class StorageError(Exception):
    """存储相关异常基类"""

    pass


class StorageUploadError(StorageError):
    """存储相关异常基类"""


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

    PUBLIC_READ_BUCKETS = {"generated-images", "avatar", "kb-images"}

    def __init__(self):
        """初始化 MinIO 客户端"""
        self.endpoint = os.getenv("MINIO_URI") or "http://milvus-minio:9000"
        self.access_key = os.getenv("MINIO_ACCESS_KEY") or "minioadmin"
        self.secret_key = os.getenv("MINIO_SECRET_KEY") or "minioadmin"
        self._client = None

        # 设置公开访问端点
        if os.getenv("RUNNING_IN_DOCKER"):
            host_ip = (os.getenv("HOST_IP") or "").strip()
            if not host_ip:
                host_ip = "localhost"
            if "://" in host_ip:
                host_ip = host_ip.split("://")[-1]
            host_ip = host_ip.rstrip("/")
            self.public_endpoint = f"{host_ip}:9000"
            logger.debug(f"Docker MinIOClient public_endpoint: {self.public_endpoint}")
        else:
            self.public_endpoint = "localhost:9000"
            logger.debug(f"Default_client: {self.public_endpoint}")

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
            created = False
            if not self.client.bucket_exists(bucket_name=bucket_name):
                self.client.make_bucket(bucket_name=bucket_name)
                created = True
                logger.info(f"存储桶 '{bucket_name}' 已创建")

            self._ensure_public_read_access(bucket_name)

            if created and bucket_name in self.PUBLIC_READ_BUCKETS:
                logger.info(f"存储桶 '{bucket_name}' 已配置为公开可读")

            return True
        except S3Error as e:
            logger.error(f"存储桶 '{bucket_name}' 错误: {e}")
            raise StorageError(f"Error with bucket '{bucket_name}': {e}")
        except StorageError:
            raise

    def upload_file(
        self, bucket_name: str, object_name: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> UploadResult:
        """上传文件到 MinIO"""
        try:
            self.ensure_bucket_exists(bucket_name=bucket_name)

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

    async def aupload_file(
        self, bucket_name: str, object_name: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> UploadResult:
        result = await asyncio.to_thread(
            self.upload_file, bucket_name=bucket_name, object_name=object_name, data=data, content_type=content_type
        )
        return result

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
            response = self.client.get_object(bucket_name=bucket_name, object_name=object_name)
            data = response.read()
            response.close()
            logger.info(f"成功下载 '{object_name}' 从存储桶 '{bucket_name}'")
            return data

        except S3Error as e:
            if "NoSuchKey" in str(e):
                raise StorageError(f"对象 '{object_name}' 在存储桶 '{bucket_name}' 中不存在")
            raise StorageError(f"下载文件失败: {e}")

    async def adownload_response(self, bucket_name: str, object_name: str) -> BaseHTTPResponse:
        """异步下载文件"""
        try:
            response = await asyncio.to_thread(
                self.client.get_object,
                bucket_name=bucket_name,
                object_name=object_name,
            )
            return response

        except S3Error as e:
            if "NoSuchKey" in str(e):
                raise StorageError(f"对象 '{object_name}' 在存储桶 '{bucket_name}' 中不存在")
            raise StorageError(f"下载文件失败: {e}")

    async def adownload_file(self, bucket_name: str, object_name: str) -> bytes:
        """异步下载文件"""
        try:
            response = await asyncio.to_thread(self.client.get_object, bucket_name=bucket_name, object_name=object_name)
            data = await asyncio.to_thread(response.read)
            response.close()
            logger.info(f"成功下载 '{object_name}' 从存储桶 '{bucket_name}'")
            return data

        except S3Error as e:
            if "NoSuchKey" in str(e):
                raise StorageError(f"对象 '{object_name}' 在存储桶 '{bucket_name}' 中不存在")
            raise StorageError(f"下载文件失败: {e}")

    def get_presigned_url(self, bucket_name: str, object_name: str, days=7) -> str:
        """将minio放在内网访问，外部通过返回代理链接访问"""
        res_url = self.client.get_presigned_url(
            method="GET", bucket_name=bucket_name, object_name=object_name, expires=timedelta(days=days)
        )
        return res_url

    def delete_file(self, bucket_name: str, object_name: str) -> bool:
        """删除文件"""
        try:
            self.client.remove_object(bucket_name=bucket_name, object_name=object_name)
            logger.info(f"成功删除 '{object_name}' 从存储桶 '{bucket_name}'")
            return True

        except S3Error as e:
            if "NoSuchKey" in str(e):
                logger.warning(f"要删除的对象 '{object_name}' 不存在")
                return False
            raise StorageError(f"删除文件失败: {e}")

    async def adelete_file(self, bucket_name: str, object_name: str) -> bool:
        """删除文件"""
        result = await asyncio.to_thread(
            self.delete_file,
            bucket_name=bucket_name,
            object_name=object_name,
        )
        return result

    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        """检查文件是否存在"""
        try:
            self.client.stat_object(bucket_name=bucket_name, object_name=object_name)
            return True
        except S3Error as e:
            if "NoSuchKey" in str(e):
                return False
            raise StorageError(f"检查文件存在性失败: {e}")

    def _ensure_public_read_access(self, bucket_name: str) -> None:
        """设置存储桶策略，允许公开读取对象"""
        if bucket_name not in self.PUBLIC_READ_BUCKETS:
            return

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                },
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:ListBucket"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}"],
                },
            ],
        }

        try:
            self.client.set_bucket_policy(bucket_name=bucket_name, policy=json.dumps(policy))
        except S3Error as e:
            logger.warning(f"设置存储桶 '{bucket_name}' 公共读取策略失败: {e}")
            raise StorageError(f"无法设置存储桶公共访问策略: {e}")


# 全局客户端实例
_default_client = None


def get_minio_client() -> MinIOClient:
    """获取 MinIO 客户端实例"""
    global _default_client
    if _default_client is None:
        _default_client = MinIOClient()
    return _default_client


async def aupload_file_to_minio(bucket_name: str, file_name: str, data: bytes, file_extension: str) -> str:
    """
    通过字节上传文件到 MinIO的异步接口，根据输入的file_extension确定文件格式，并返回资源url

    Args:
        bucket_name: bucket_name
        file_name : filename
        data: 文件字节流
        file_extension: 输入的拓展名
    Returns:
        str: 文件访问 URL
    """
    client = get_minio_client()
    # 根据扩展名猜测 content_type
    content_type = client._guess_content_type(file_extension)
    # 上传文件
    upload_result = await client.aupload_file(bucket_name, file_name, data, content_type)
    return upload_result.url
