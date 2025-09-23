# MinIO 存储模块

简化的 MinIO 对象存储模块，提供基本的文件存储功能。

## 核心功能

### 基本使用

```python
from src.storage.minio import upload_image_to_minio

# 上传图片（保持原有接口）
url = upload_image_to_minio(image_data, "jpg")
print(f"图片已上传: {url}")
```

### 高级使用

```python
from src.storage.minio import MinIOClient, get_minio_client

# 获取客户端实例
client = get_minio_client()

# 上传文件
with open("example.txt", "rb") as f:
    data = f.read()

result = client.upload_file("my-bucket", "example.txt", data)
print(f"文件已上传: {result.url}")

# 下载文件
downloaded_data = client.download_file("my-bucket", "example.txt")

# 删除文件
client.delete_file("my-bucket", "example.txt")
```

## 功能特性

- ✅ **向后兼容**：保持 `upload_image_to_minio` 函数的原有接口
- ✅ **简洁易用**：核心功能一目了然
- ✅ **错误处理**：统一的异常处理
- ✅ **类型安全**：完整的类型注解

## 架构优势

1. **职责清晰**：`src/storage/minio` 专门处理对象存储
2. **易于维护**：代码简洁，功能明确
3. **易于扩展**：为未来功能扩展留出空间
4. **向后兼容**：不破坏现有代码
