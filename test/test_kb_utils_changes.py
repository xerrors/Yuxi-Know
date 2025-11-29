"""
测试知识库工具函数的异步变更
文件: src/knowledge/utils/kb_utils.py
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
import hashlib
from src.knowledge.utils.kb_utils import calculate_content_hash, prepare_item_metadata


class TestCalculateContentHashChanges:
    """测试 calculate_content_hash 改为异步后的功能"""

    @pytest.mark.asyncio
    async def test_hash_bytes_data(self):
        """测试计算字节数据的哈希"""
        test_data = b"Test content for hashing"

        # 异步计算哈希
        hash_result = await calculate_content_hash(test_data)

        # 验证结果
        expected_hash = hashlib.sha256(test_data).hexdigest()
        assert hash_result == expected_hash
        assert len(hash_result) == 64  # SHA-256 长度
        print(f"✓ 字节数据哈希计算正确: {hash_result}")

    @pytest.mark.asyncio
    async def test_hash_bytearray_data(self):
        """测试计算 bytearray 数据的哈希"""
        test_data = bytearray(b"Bytearray test content")

        hash_result = await calculate_content_hash(test_data)

        expected_hash = hashlib.sha256(test_data).hexdigest()
        assert hash_result == expected_hash
        print(f"✓ bytearray 数据哈希计算正确: {hash_result}")

    @pytest.mark.asyncio
    async def test_hash_file_path_str(self, tmp_path):
        """测试计算文件路径（字符串）的哈希"""
        # 创建测试文件
        test_file = tmp_path / "test_hash_str.txt"
        test_content = b"File content for hashing test"
        test_file.write_bytes(test_content)

        # 异步计算文件哈希
        hash_result = await calculate_content_hash(str(test_file))

        # 验证结果
        expected_hash = hashlib.sha256(test_content).hexdigest()
        assert hash_result == expected_hash
        print(f"✓ 文件路径（字符串）哈希计算正确: {hash_result}")

    @pytest.mark.asyncio
    async def test_hash_file_path_object(self, tmp_path):
        """测试计算文件路径（Path对象）的哈希"""
        # 创建测试文件
        test_file = tmp_path / "test_hash_path.txt"
        test_content = b"Path object hashing test"
        test_file.write_bytes(test_content)

        # 异步计算文件哈希
        hash_result = await calculate_content_hash(test_file)

        # 验证结果
        expected_hash = hashlib.sha256(test_content).hexdigest()
        assert hash_result == expected_hash
        print(f"✓ 文件路径（Path对象）哈希计算正确: {hash_result}")

    @pytest.mark.asyncio
    async def test_hash_large_file(self, tmp_path):
        """测试计算大文件的哈希（验证分块读取）"""
        # 创建大于 8192 字节的测试文件
        test_file = tmp_path / "large_file.bin"
        test_content = b"A" * 20000  # 20KB

        test_file.write_bytes(test_content)

        # 异步计算哈希
        hash_result = await calculate_content_hash(test_file)

        # 验证结果
        expected_hash = hashlib.sha256(test_content).hexdigest()
        assert hash_result == expected_hash
        print(f"✓ 大文件哈希计算正确（文件大小: {len(test_content)} 字节）")

    @pytest.mark.asyncio
    async def test_hash_empty_file(self, tmp_path):
        """测试计算空文件的哈希"""
        test_file = tmp_path / "empty_file.txt"
        test_file.write_bytes(b"")

        hash_result = await calculate_content_hash(test_file)

        expected_hash = hashlib.sha256(b"").hexdigest()
        assert hash_result == expected_hash
        print(f"✓ 空文件哈希计算正确: {hash_result}")

    @pytest.mark.asyncio
    async def test_hash_consistency(self):
        """测试相同数据的哈希一致性"""
        test_data = b"Consistency test data"

        # 多次计算哈希
        hash1 = await calculate_content_hash(test_data)
        hash2 = await calculate_content_hash(test_data)
        hash3 = await calculate_content_hash(test_data)

        # 验证一致性
        assert hash1 == hash2 == hash3
        print(f"✓ 哈希计算一致性验证通过: {hash1}")


class TestPrepareItemMetadataChanges:
    """测试 prepare_item_metadata 改为异步后的功能"""

    @pytest.mark.asyncio
    async def test_prepare_file_metadata(self, tmp_path):
        """测试准备文件元数据"""
        # 创建测试文件
        test_file = tmp_path / "test_metadata.txt"
        test_content = b"Test file content for metadata"
        test_file.write_bytes(test_content)

        # 异步准备元数据
        metadata = await prepare_item_metadata(
            item=str(test_file),
            content_type="file",
            db_id="test_database",
            params={"custom_key": "custom_value"},
        )

        # 验证元数据
        assert metadata is not None
        assert metadata["filename"] == "test_metadata.txt"
        assert metadata["database_id"] == "test_database"
        assert "file_id" in metadata
        assert "content_hash" in metadata
        assert len(metadata["content_hash"]) == 64

        print(f"✓ 文件元数据准备成功:")
        print(f"  - filename: {metadata['filename']}")
        print(f"  - file_id: {metadata['file_id']}")
        print(f"  - content_hash: {metadata['content_hash'][:16]}...")

    @pytest.mark.asyncio
    async def test_prepare_url_metadata(self):
        """测试准备 URL 元数据"""
        test_url = "https://example.com/document.pdf"

        # 异步准备元数据
        metadata = await prepare_item_metadata(
            item=test_url, content_type="url", db_id="test_db_url", params=None
        )

        # 验证元数据
        assert metadata is not None
        assert metadata["filename"] == "document.pdf"
        assert metadata["database_id"] == "test_db_url"
        assert "file_id" in metadata
        assert metadata.get("content_hash") is None  # URL 不计算 hash

        print(f"✓ URL 元数据准备成功:")
        print(f"  - filename: {metadata['filename']}")
        print(f"  - file_id: {metadata['file_id']}")

    @pytest.mark.asyncio
    async def test_prepare_metadata_with_params(self, tmp_path):
        """测试带参数的元数据准备"""
        test_file = tmp_path / "params_test.txt"
        test_file.write_bytes(b"Params test content")

        params = {
            "chunk_size": 500,
            "chunk_overlap": 50,
            "separator": "\n\n",
            "custom_field": "test_value",
        }

        metadata = await prepare_item_metadata(
            item=str(test_file), content_type="file", db_id="params_test_db", params=params
        )

        assert metadata is not None
        assert "file_id" in metadata
        print(f"✓ 带参数的元数据准备成功")

    @pytest.mark.asyncio
    async def test_prepare_metadata_nonexistent_file(self, tmp_path):
        """测试不存在文件的元数据准备"""
        nonexistent_file = tmp_path / "nonexistent.txt"

        # 即使文件不存在也应该能准备元数据（hash 为 None）
        metadata = await prepare_item_metadata(
            item=str(nonexistent_file),
            content_type="file",
            db_id="test_db",
            params=None,
        )

        assert metadata is not None
        assert metadata["filename"] == "nonexistent.txt"
        assert metadata.get("content_hash") is None
        print(f"✓ 不存在文件的元数据准备成功（hash 为 None）")

    @pytest.mark.asyncio
    async def test_concurrent_metadata_preparation(self, tmp_path):
        """测试并发准备多个文件的元数据"""
        import asyncio

        # 创建多个测试文件
        files = []
        for i in range(5):
            test_file = tmp_path / f"concurrent_{i}.txt"
            test_file.write_bytes(f"Content {i}".encode())
            files.append(str(test_file))

        # 并发准备元数据
        tasks = [
            prepare_item_metadata(item=f, content_type="file", db_id=f"db_{i}", params=None)
            for i, f in enumerate(files)
        ]

        results = await asyncio.gather(*tasks)

        # 验证结果
        assert len(results) == 5
        for i, metadata in enumerate(results):
            assert metadata["filename"] == f"concurrent_{i}.txt"
            assert metadata["database_id"] == f"db_{i}"
            assert len(metadata["content_hash"]) == 64

        print(f"✓ 并发元数据准备测试通过，处理了 {len(results)} 个文件")


if __name__ == "__main__":
    exit_code = pytest.main([__file__, "-v", "-s", "--tb=short", "--color=yes"])
    sys.exit(exit_code)
