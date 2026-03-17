"""
测试知识库删除时 MinIO 文件清理功能

测试步骤：
1. 创建测试知识库
2. 上传测试文件到 MinIO（模拟文件上传流程）
3. 删除知识库
4. 验证 MinIO 文件是否被清理
"""

import asyncio
import os
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_delete_knowledge_base_cleanup():
    """测试删除知识库时 MinIO 文件清理"""
    from yuxi.storage.minio import get_minio_client
    from yuxi.knowledge import knowledge_base

    # 初始化
    minio_client = get_minio_client()
    kb_manager = knowledge_base
    doc_bucket = minio_client.KB_BUCKETS["documents"]
    parsed_bucket = minio_client.KB_BUCKETS["parsed"]

    # 测试参数
    test_db_name = "test_cleanup_db"
    test_file_content = b"This is test content for cleanup verification"

    try:
        # 1. 创建知识库
        print("1. 创建测试知识库...")
        kb_info = await kb_manager.create_database(
            database_name=test_db_name,
            description="Test knowledge base for MinIO cleanup",
            kb_type="lightrag",
        )
        db_id = kb_info["db_id"]
        print(f"   知识库创建成功: db_id={db_id}")

        # 2. 上传测试文件到 MinIO（模拟文件上传）
        print("2. 上传测试文件到 MinIO...")

        # 确保 bucket 存在
        minio_client.ensure_bucket_exists(doc_bucket)
        minio_client.ensure_bucket_exists(parsed_bucket)

        # 上传到知识库文档路径 (knowledgebases/{db_id}/upload/...)
        test_object_name = f"{db_id}/upload/test_file_{db_id[:8]}.txt"
        minio_client.upload_file(
            bucket_name=doc_bucket,
            object_name=test_object_name,
            data=test_file_content,
            content_type="text/plain",
        )
        print(f"   文件上传到 {doc_bucket}: {test_object_name}")

        # 上传到知识库解析路径 (knowledgebases/{db_id}/parsed/...)
        test_file_id = f"file_test_{db_id[:8]}"
        parsed_object_name = f"{db_id}/parsed/{test_file_id}.md"
        parsed_content = b"# Test Parsed Content\n\nThis is parsed markdown."
        minio_client.upload_file(
            bucket_name=parsed_bucket,
            object_name=parsed_object_name,
            data=parsed_content,
            content_type="text/markdown",
        )
        print(f"   文件上传到 {parsed_bucket}: {parsed_object_name}")

        # 3. 验证文件存在
        print("3. 验证文件存在...")
        assert minio_client.file_exists(doc_bucket, test_object_name), "原始文件应该存在"
        assert minio_client.file_exists(parsed_bucket, parsed_object_name), "解析后文件应该存在"
        print("   文件存在验证通过")

        # 4. 删除知识库
        print("4. 删除知识库...")
        result = await kb_manager.delete_database(db_id)
        print(f"   删除结果: {result}")

        # 5. 验证 MinIO 文件已清理
        print("5. 验证 MinIO 文件已清理...")

        # 检查文档对象
        doc_exists = minio_client.file_exists(doc_bucket, test_object_name)
        print(f"   {doc_bucket}/{test_object_name} 存在: {doc_exists}")

        # 检查解析对象
        parsed_exists = minio_client.file_exists(parsed_bucket, parsed_object_name)
        print(f"   {parsed_bucket}/{parsed_object_name} 存在: {parsed_exists}")

        # 6. 输出测试结果
        print("\n" + "=" * 50)
        if not doc_exists and not parsed_exists:
            print("✅ 测试通过！MinIO 文件已成功清理")
            return True
        else:
            print("❌ 测试失败！以下文件未被清理:")
            if doc_exists:
                print(f"   - {doc_bucket}/{test_object_name}")
            if parsed_exists:
                print(f"   - {parsed_bucket}/{parsed_object_name}")
            return False

    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # 清理测试数据（确保清理干净）
        print("\n清理测试数据...")
        try:
            # 尝试删除可能残留的文件（忽略错误）
            for bucket, obj in [(doc_bucket, test_object_name), (parsed_bucket, parsed_object_name)]:
                try:
                    await minio_client.adelete_file(bucket, obj)
                except Exception:
                    pass
        except Exception as e:
            print(f"   清理时出错: {e}")


if __name__ == "__main__":
    result = asyncio.run(test_delete_knowledge_base_cleanup())
    sys.exit(0 if result else 1)
