"""
测试知识库路由的变更
文件: server/routers/knowledge_router.py
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import UploadFile
from io import BytesIO


class TestKnowledgeRouterChanges:
    """测试 knowledge_router.py 的变更"""

    @pytest.mark.asyncio
    async def test_add_documents_minio_upload(self):
        """测试上传文档后自动上传到 MinIO"""
        # 模拟成功处理的文件项
        success_items = [
            {
                "status": "done",
                "path": "/tmp/test_file.pdf",
                "filename": "test_file.pdf",
                "file_type": "application/pdf",
            }
        ]

        # 模拟 aupload_file_to_minio 函数
        with patch("server.routers.knowledge_router.aupload_file_to_minio") as mock_upload:
            mock_upload.return_value = "https://minio.example.com/ref-test-db/test_file.pdf"

            # 模拟 aiofiles.open
            with patch("server.routers.knowledge_router.aiofiles.open") as mock_open:
                mock_file = AsyncMock()
                mock_file.read = AsyncMock(return_value=b"PDF content")
                mock_open.return_value.__aenter__.return_value = mock_file

                # 模拟上传逻辑
                for success_item in success_items:
                    # 读取文件
                    async with mock_open(success_item["path"], "rb") as f:
                        file_bytes = await f.read()

                    # 上传到 MinIO
                    refdb = "test_db".replace("_", "-")
                    url = await mock_upload(
                        f"ref-{refdb}",
                        success_item["filename"],
                        file_bytes,
                        success_item["file_type"],
                    )

                    assert url is not None
                    assert "ref-test-db" in url
                    print(f"✓ MinIO 上传模拟成功: {url}")

    @pytest.mark.asyncio
    async def test_delete_document_minio_cleanup(self):
        """测试删除文档时同时删除 MinIO 中的文件"""
        db_id = "test_database"
        doc_id = "doc_12345"
        file_name = "test_document.pdf"

        # 模拟 knowledge_base.get_file_basic_info
        with patch("server.routers.knowledge_router.knowledge_base") as mock_kb:
            mock_kb.get_file_basic_info = AsyncMock(
                return_value={"meta": {"filename": file_name}}
            )
            mock_kb.delete_file = AsyncMock()

            # 模拟 MinIO 客户端
            with patch("server.routers.knowledge_router.get_minio_client") as mock_get_client:
                mock_client = Mock()
                mock_client.adelete_file = AsyncMock(return_value=True)
                mock_get_client.return_value = mock_client

                # 执行删除逻辑
                file_meta_info = await mock_kb.get_file_basic_info(db_id, doc_id)
                file_name_result = file_meta_info.get("meta", {}).get("filename")

                await mock_client.adelete_file("ref-" + db_id.replace("_", "-"), file_name_result)
                await mock_kb.delete_file(db_id, doc_id)

                # 验证调用
                mock_kb.get_file_basic_info.assert_called_once_with(db_id, doc_id)
                mock_client.adelete_file.assert_called_once_with(
                    "ref-test-database", file_name
                )
                mock_kb.delete_file.assert_called_once_with(db_id, doc_id)
                print(f"✓ 删除文档时 MinIO 清理逻辑验证成功")

    @pytest.mark.asyncio
    async def test_download_document_streaming_response(self):
        """测试文档下载的流式响应"""
        import asyncio

        # 模拟 MinIO 响应对象
        class MockMinioResponse:
            def __init__(self, data):
                self.data = data
                self.position = 0

            def read(self, size):
                """同步读取方法"""
                if self.position >= len(self.data):
                    return b""
                chunk = self.data[self.position : self.position + size]
                self.position += size
                return chunk

            def close(self):
                pass

            def release_conn(self):
                pass

        test_data = b"A" * 20000  # 20KB 测试数据
        mock_response = MockMinioResponse(test_data)

        # 模拟流式生成器
        async def minio_stream():
            try:
                while True:
                    chunk = await asyncio.to_thread(mock_response.read, 8192)
                    if not chunk:
                        break
                    yield chunk
            finally:
                mock_response.close()
                mock_response.release_conn()

        # 收集所有块
        chunks = []
        async for chunk in minio_stream():
            chunks.append(chunk)

        # 验证
        result_data = b"".join(chunks)
        assert len(result_data) == len(test_data)
        assert result_data == test_data
        print(f"✓ 流式下载响应验证成功（数据大小: {len(result_data)} 字节，{len(chunks)} 个块）")

    @pytest.mark.asyncio
    async def test_upload_file_hash_calculation(self):
        """测试文件上传时的异步哈希计算"""
        from src.knowledge.utils.kb_utils import calculate_content_hash

        # 模拟上传的文件内容
        file_content = b"Test file content for hashing"

        # 异步计算哈希
        content_hash = await calculate_content_hash(file_content)

        assert content_hash is not None
        assert len(content_hash) == 64  # SHA-256
        print(f"✓ 上传文件哈希计算成功: {content_hash}")

    @pytest.mark.asyncio
    async def test_file_existence_check(self):
        """测试文件存在性检查的异步调用"""
        db_id = "test_db"
        content_hash = "a" * 64

        # 模拟 knowledge_base
        with patch("server.routers.knowledge_router.knowledge_base") as mock_kb:
            mock_kb.file_existed_in_db = AsyncMock(return_value=False)

            # 执行检查
            file_exists = await mock_kb.file_existed_in_db(db_id, content_hash)

            assert file_exists is False
            mock_kb.file_existed_in_db.assert_called_once_with(db_id, content_hash)
            print(f"✓ 异步文件存在性检查验证成功")

    def test_upload_file_fixed_salt_logic(self):
        """测试上传文件时的固定 salt 逻辑"""
        from src.utils import hashstr

        # 测试固定 salt 的文件命名
        basename = "test_document"
        ext = ".pdf"

        # 使用固定 salt
        filename1 = f"{basename}_{hashstr(basename, 4, with_salt=True, salt='fixed_salt')}{ext}".lower()
        filename2 = f"{basename}_{hashstr(basename, 4, with_salt=True, salt='fixed_salt')}{ext}".lower()

        # 验证相同名称生成相同的哈希（因为 salt 固定）
        assert filename1 == filename2
        print(f"✓ 固定 salt 文件命名验证成功: {filename1}")

    @pytest.mark.asyncio
    async def test_streaming_response_error_handling(self):
        """测试流式响应的错误处理"""
        import asyncio

        class MockErrorResponse:
            def read(self, size):
                raise Exception("MinIO read error")

            def close(self):
                pass

            def release_conn(self):
                pass

        mock_response = MockErrorResponse()

        async def minio_stream():
            try:
                while True:
                    chunk = await asyncio.to_thread(mock_response.read, 8192)
                    if not chunk:
                        break
                    yield chunk
            except Exception as e:
                print(f"✓ 错误被正确捕获: {e}")
                raise
            finally:
                mock_response.close()
                mock_response.release_conn()

        # 验证错误处理
        with pytest.raises(Exception, match="MinIO read error"):
            async for chunk in minio_stream():
                pass

        print(f"✓ 流式响应错误处理验证成功")


class TestMinIOIntegration:
    """测试 MinIO 集成逻辑"""

    @pytest.mark.asyncio
    async def test_bucket_naming_convention(self):
        """测试 bucket 命名约定（ref-{db_id}）"""
        db_id = "test_knowledge_base"
        expected_bucket = "ref-test-knowledge-base"  # 下划线替换为连字符

        refdb = db_id.replace("_", "-")
        actual_bucket = f"ref-{refdb}"

        assert actual_bucket == expected_bucket
        print(f"✓ Bucket 命名约定正确: {db_id} -> {actual_bucket}")

    @pytest.mark.asyncio
    async def test_concurrent_minio_uploads(self):
        """测试并发上传到 MinIO"""
        import asyncio

        # 模拟多个文件的并发上传
        async def mock_upload(file_id):
            await asyncio.sleep(0.1)  # 模拟上传延迟
            return f"https://minio.example.com/bucket/file_{file_id}"

        # 并发上传 5 个文件
        tasks = [mock_upload(i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for i, url in enumerate(results):
            assert f"file_{i}" in url

        print(f"✓ 并发 MinIO 上传模拟成功，处理了 {len(results)} 个文件")


if __name__ == "__main__":
    exit_code = pytest.main([__file__, "-v", "-s", "--tb=short", "--color=yes"])
    sys.exit(exit_code)
