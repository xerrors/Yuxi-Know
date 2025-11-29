"""
测试 MinIO 客户端的异步方法变更
文件: src/storage/minio/client.py
"""

import asyncio
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from src.storage.minio.client import MinIOClient, aupload_file_to_minio, get_minio_client


class TestMinIOClientChanges:
    """测试 MinIO 客户端的新增异步方法"""

    @pytest.fixture
    def minio_client(self):
        """创建 MinIO 客户端实例"""
        client = get_minio_client()
        return client

    @pytest.mark.asyncio
    async def test_aupload_file(self, minio_client):
        """测试新增的 aupload_file 异步方法"""
        bucket_name = "test-async-upload"
        object_name = "test_async_upload.txt"
        test_data = b"Async upload test content"

        # 确保 bucket 存在
        minio_client.ensure_bucket_exists(bucket_name)

        # 测试异步上传
        result = await minio_client.aupload_file(
            bucket_name=bucket_name,
            object_name=object_name,
            data=test_data,
            content_type="text/plain",
        )

        assert result is not None
        assert result.bucket_name == bucket_name
        assert result.object_name == object_name
        print(f"✓ aupload_file 测试通过: {result.url}")

        # 验证文件存在
        exists = minio_client.file_exists(bucket_name, object_name)
        assert exists is True

        # 清理
        minio_client.delete_file(bucket_name, object_name)

    @pytest.mark.asyncio
    async def test_adownload_response(self, minio_client):
        """测试新增的 adownload_response 异步方法"""
        bucket_name = "test-async-download-resp"
        object_name = "test_download_response.txt"
        test_data = b"Download response test content"

        # 准备测试文件
        minio_client.ensure_bucket_exists(bucket_name)
        minio_client.upload_file(bucket_name, object_name, test_data)

        # 测试异步下载响应
        response = await minio_client.adownload_response(bucket_name, object_name)

        assert response is not None
        downloaded_data = response.read()
        response.close()
        response.release_conn()

        assert downloaded_data == test_data
        print(f"✓ adownload_response 测试通过，数据大小: {len(downloaded_data)} 字节")

        # 清理
        minio_client.delete_file(bucket_name, object_name)

    @pytest.mark.asyncio
    async def test_adownload_file(self, minio_client):
        """测试新增的 adownload_file 异步方法"""
        bucket_name = "test-async-download"
        object_name = "test_async_download.txt"
        test_data = b"Async download test content"

        # 准备测试文件
        minio_client.ensure_bucket_exists(bucket_name)
        minio_client.upload_file(bucket_name, object_name, test_data)

        # 测试异步下载
        downloaded_data = await minio_client.adownload_file(bucket_name, object_name)

        assert downloaded_data == test_data
        print(f"✓ adownload_file 测试通过，数据匹配")

        # 清理
        minio_client.delete_file(bucket_name, object_name)

    @pytest.mark.asyncio
    async def test_adelete_file(self, minio_client):
        """测试新增的 adelete_file 异步方法"""
        bucket_name = "test-async-delete"
        object_name = "test_async_delete.txt"
        test_data = b"Async delete test content"

        # 准备测试文件
        minio_client.ensure_bucket_exists(bucket_name)
        minio_client.upload_file(bucket_name, object_name, test_data)

        # 验证文件存在
        assert minio_client.file_exists(bucket_name, object_name)

        # 测试异步删除
        result = await minio_client.adelete_file(bucket_name, object_name)

        assert result is True
        assert not minio_client.file_exists(bucket_name, object_name)
        print(f"✓ adelete_file 测试通过")

    def test_get_presigned_url(self, minio_client):
        """测试新增的 get_presigned_url 方法"""
        bucket_name = "test-presigned-url"
        object_name = "test_presigned.txt"
        test_data = b"Presigned URL test content"

        # 准备测试文件
        minio_client.ensure_bucket_exists(bucket_name)
        minio_client.upload_file(bucket_name, object_name, test_data)

        # 测试获取预签名 URL（默认 7 天）
        presigned_url = minio_client.get_presigned_url(bucket_name, object_name)

        assert presigned_url is not None
        assert bucket_name in presigned_url
        assert object_name in presigned_url
        assert "X-Amz-Expires" in presigned_url
        print(f"✓ get_presigned_url 测试通过")
        print(f"  URL: {presigned_url[:100]}...")

        # 测试自定义过期时间
        presigned_url_custom = minio_client.get_presigned_url(bucket_name, object_name, days=1)
        assert presigned_url_custom is not None
        print(f"✓ get_presigned_url (自定义天数) 测试通过")

        # 清理
        minio_client.delete_file(bucket_name, object_name)

    @pytest.mark.asyncio
    async def test_aupload_file_to_minio_function(self):
        """测试新增的 aupload_file_to_minio 工具函数"""
        bucket_name = "test-upload-util"
        file_name = "test_util_upload.pdf"
        test_data = b"PDF test content"
        file_extension = ".pdf"

        # 测试工具函数
        url = await aupload_file_to_minio(
            bucket_name=bucket_name,
            file_name=file_name,
            data=test_data,
            file_extension=file_extension,
        )

        assert url is not None
        assert bucket_name in url
        assert file_name in url
        print(f"✓ aupload_file_to_minio 工具函数测试通过")
        print(f"  返回的预签名 URL: {url[:100]}...")

        # 清理
        client = get_minio_client()
        client.delete_file(bucket_name, file_name)

    @pytest.mark.asyncio
    async def test_concurrent_async_operations(self, minio_client):
        """测试并发异步操作"""
        bucket_name = "test-concurrent"
        minio_client.ensure_bucket_exists(bucket_name)

        # 准备多个测试任务
        async def upload_and_download(index):
            object_name = f"concurrent_test_{index}.txt"
            test_data = f"Concurrent test {index}".encode()

            # 异步上传
            await minio_client.aupload_file(bucket_name, object_name, test_data)

            # 异步下载
            downloaded = await minio_client.adownload_file(bucket_name, object_name)
            assert downloaded == test_data

            # 异步删除
            await minio_client.adelete_file(bucket_name, object_name)

            return f"Task {index} completed"

        # 并发执行多个任务
        tasks = [upload_and_download(i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        print(f"✓ 并发异步操作测试通过，完成 {len(results)} 个任务")
        for result in results:
            print(f"  - {result}")


if __name__ == "__main__":
    exit_code = pytest.main([__file__, "-v", "-s", "--tb=short", "--color=yes"])
    sys.exit(exit_code)
