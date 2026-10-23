"""
MinIO 存储客户端
简化的 MinIO 对象存储操作
"""

import asyncio
import json
import os
from datetime import timedelta
from io import BytesIO
from urllib.parse import quote, urlsplit

from urllib3 import BaseHTTPResponse

from minio import Minio
from minio.error import S3Error
from yuxi.infrastructure.observability.logging import logger
from yuxi.shared.files import detect_media_type


class StorageError(Exception):
    """存储相关异常基类"""

    pass


class ObjectSizeLimitError(StorageError):
    """对象字节数超过调用方指定的读取上限。"""


class UploadResult:
    """简化的上传结果"""

    def __init__(self, url: str, bucket_name: str, object_name: str):
        self.url = url
        self.bucket_name = bucket_name
        self.object_name = object_name


def normalize_public_minio_url(value: str | None) -> str | None:
    if not value or value.startswith("/minio/public/"):
        return value
    try:
        parsed = urlsplit(value)
        if parsed.port != 9000 or not parsed.path.startswith("/public/"):
            return value
    except ValueError:
        return value
    public_base_url = (os.getenv("MINIO_PUBLIC_URL") or "/minio").rstrip("/")
    normalized = f"{public_base_url}{parsed.path}"
    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"
    if parsed.fragment:
        normalized = f"{normalized}#{parsed.fragment}"
    return normalized


class MinIOClient:
    """
    简化的 MinIO 客户端类
    """

    PUBLIC_READ_BUCKETS = {"public"}

    # 知识库相关的 bucket 名称；images 使用私有 bucket，图片统一经后端鉴权代理访问
    KB_BUCKETS = {
        "documents": "knowledgebases",
        "parsed": "knowledgebases",
        "images": "kb-images",
    }

    def __init__(self):
        """初始化 MinIO 客户端"""
        self.endpoint = os.getenv("MINIO_URI") or "http://minio:9000"
        self.access_key = os.getenv("MINIO_ACCESS_KEY") or "minioadmin"
        self.secret_key = os.getenv("MINIO_SECRET_KEY") or "minioadmin"
        self.public_base_url = (os.getenv("MINIO_PUBLIC_URL") or "/minio").rstrip("/")
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

            self._client = Minio(endpoint=endpoint, access_key=self.access_key, secret_key=self.secret_key, secure=False)
        return self._client

    def ensure_bucket_exists(self, bucket_name: str) -> bool:
        """确保存储桶存在"""
        try:
            created = False
            if not self.client.bucket_exists(bucket_name=bucket_name):
                try:
                    self.client.make_bucket(bucket_name=bucket_name)
                except S3Error as e:
                    # 其他上传可能已创建同一桶；只有明确归当前账号所有才可继续。
                    if e.code != "BucketAlreadyOwnedByYou":
                        raise
                else:
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
        self, bucket_name: str, object_name: str, data: bytes, content_type: str | None = None, metadata: dict | None = None
    ) -> UploadResult:
        """上传文件到 MinIO"""
        try:
            self.ensure_bucket_exists(bucket_name=bucket_name)

            resolved_content_type = content_type or detect_media_type(object_name)
            data_stream = BytesIO(data)
            result = self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data_stream,
                length=len(data),
                content_type=resolved_content_type,
                metadata=metadata,
            )

            assert result is not None
            if bucket_name in self.PUBLIC_READ_BUCKETS:
                url = f"{self.public_base_url}/{bucket_name}/{quote(object_name, safe='/')}"
            else:
                url = f"http://{self.public_endpoint}/{bucket_name}/{quote(object_name, safe='/')}"

            return UploadResult(url, bucket_name, object_name)

        except S3Error as e:
            error_msg = f"上传文件 '{object_name}' 失败: {e}"
            logger.error(error_msg)
            raise StorageError(error_msg)

    async def aupload_file(
        self,
        bucket_name: str,
        object_name: str,
        data: bytes,
        content_type: str | None = None,
        metadata: dict | None = None,
    ) -> UploadResult:
        """在线程内上传字节及可选对象元数据。"""
        result = await asyncio.to_thread(
            self.upload_file,
            bucket_name=bucket_name,
            object_name=object_name,
            data=data,
            content_type=content_type,
            metadata=metadata,
        )
        return result

    async def object_metadata(self, bucket_name: str, object_name: str) -> dict[str, str]:
        """回读对象来源元数据，不从物理键猜测逻辑文件名。"""
        stat = await asyncio.to_thread(self.client.stat_object, bucket_name, object_name)
        return {key.lower(): value for key, value in stat.metadata.items()}

    def download_file(self, bucket_name: str, object_name: str, *, max_bytes: int | None = None) -> bytes:
        """读取对象；指定上限时最多读取上限加一字节以判断超限。"""
        if max_bytes is not None and max_bytes < 0:
            raise ValueError("object read limit must be non-negative")
        response = None
        try:
            response = self.client.get_object(bucket_name=bucket_name, object_name=object_name)
            data = response.read() if max_bytes is None else response.read(max_bytes + 1)
            if max_bytes is not None and len(data) > max_bytes:
                raise ObjectSizeLimitError("object exceeds read limit")
            logger.info(f"成功下载 '{object_name}' 从存储桶 '{bucket_name}'")
            return data

        except S3Error as e:
            if e.code == "NoSuchKey":
                raise StorageError(f"对象 '{object_name}' 在存储桶 '{bucket_name}' 中不存在")
            raise StorageError(f"下载文件失败: {e}")
        finally:
            if response is not None:
                response.close()
                response.release_conn()

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
            if e.code == "NoSuchKey":
                raise StorageError(f"对象 '{object_name}' 在存储桶 '{bucket_name}' 中不存在")
            raise StorageError(f"下载文件失败: {e}")

    async def adownload_file(self, bucket_name: str, object_name: str, *, max_bytes: int | None = None) -> bytes:
        """在线程内读取并关闭对象响应，支持调用方指定字节上限。"""
        return await asyncio.to_thread(self.download_file, bucket_name, object_name, max_bytes=max_bytes)

    def get_presigned_url(self, bucket_name: str, object_name: str, days=7) -> str:
        """将minio放在内网访问，外部通过返回代理链接访问"""
        res_url = self.client.get_presigned_url(
            method="GET",
            bucket_name=bucket_name,
            object_name=object_name,
            expires=timedelta(days=days),
        )
        return res_url

    def delete_file(self, bucket_name: str, object_name: str) -> bool:
        """删除文件"""
        try:
            self.client.remove_object(bucket_name=bucket_name, object_name=object_name)
            logger.info(f"成功删除 '{object_name}' 从存储桶 '{bucket_name}'")
            return True

        except S3Error as e:
            if e.code == "NoSuchKey":
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

    async def adelete_objects_by_prefix(self, bucket_name: str, prefix: str) -> int:
        """
        按前缀删除对象

        Args:
            bucket_name: bucket 名称
            prefix: 对象前缀

        Returns:
            删除的对象数量
        """
        deleted_count = 0

        def _delete_objects():
            nonlocal deleted_count
            try:
                objects = self.client.list_objects(bucket_name, prefix=prefix, recursive=True)
                for obj in objects:
                    self.client.remove_object(bucket_name, obj.object_name)
                    deleted_count += 1
            except S3Error as e:
                if e.code == "NoSuchBucket":
                    logger.warning(f"待清理的存储桶 '{bucket_name}' 不存在")
                    return
                raise StorageError(f"删除对象前缀失败: {bucket_name}/{prefix}: {e}") from e

        await asyncio.to_thread(_delete_objects)
        return deleted_count

    async def alist_object_metadata(self, bucket_name: str, prefix: str) -> list[dict]:
        """在线程池中列出过期清理所需的对象元数据。"""

        def list_metadata() -> list[dict]:
            try:
                return [
                    {
                        "object_name": str(item.object_name),
                        "last_modified": item.last_modified,
                    }
                    for item in self.client.list_objects(bucket_name, prefix=prefix, recursive=True)
                ]
            except S3Error as exc:
                raise StorageError(f"列出对象前缀失败: {bucket_name}/{prefix}: {exc}") from exc

        return await asyncio.to_thread(list_metadata)

    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        """检查文件是否存在"""
        try:
            self.client.stat_object(bucket_name=bucket_name, object_name=object_name)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise StorageError(f"检查文件存在性失败: {e}")

    def stat_file(self, bucket_name: str, object_name: str) -> int | None:
        """获取文件大小（字节），文件不存在时返回 None"""
        try:
            stat = self.client.stat_object(bucket_name=bucket_name, object_name=object_name)
            return stat.size
        except S3Error as e:
            if e.code == "NoSuchKey":
                return None
            raise StorageError(f"获取文件信息失败: {e}")

    async def astat_file(self, bucket_name: str, object_name: str) -> int | None:
        """异步获取文件大小（字节），文件不存在时返回 None"""
        return await asyncio.to_thread(self.stat_file, bucket_name, object_name)

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


async def aupload_file_to_minio(bucket_name: str, file_name: str, data: bytes) -> str:
    """
    通过字节上传文件到 MinIO 的异步接口，并返回资源 URL。
    MIME 类型由 MinIO 客户端内部根据 object_name 自动推断。

    Args:
        bucket_name: bucket_name
        file_name : filename
        data: 文件字节流
    Returns:
        str: 文件访问 URL
    """
    client = get_minio_client()
    upload_result = await client.aupload_file(bucket_name, file_name, data)
    return upload_result.url
