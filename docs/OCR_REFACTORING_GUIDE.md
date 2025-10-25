# OCR 重构说明

## 主要变更

### 1. 简化的处理器类型
- 移除了复杂的本地调用 MinerU 版本
- 统一使用 HTTP API 接口
- 现在只有 3 种处理器: RapidOCR, MinerU, PaddleX

### 2. 统一的接口
所有处理器都实现 `BaseDocumentProcessor` 接口:
- `process_file()` - 处理文件
- `check_health()` - 健康检查
- `get_service_name()` - 获取服务名

### 3. 使用方式
```python
# 新方式 (推荐)
from src.plugins.document_processor_factory import DocumentProcessorFactory
text = DocumentProcessorFactory.process_file("mineru_ocr", file_path, params)

# 旧方式 (仍可用)
from src.plugins import ocr
text = ocr.process_file_mineru(file_path, params)
```

## 迁移说明

### 代码迁移
```python
# 旧代码 (仍可用)
from src.plugins import ocr
text = ocr.process_file_mineru(file_path, params)

# 新代码 (推荐)
from src.plugins.document_processor_factory import DocumentProcessorFactory
text = DocumentProcessorFactory.process_file("mineru_ocr", file_path, params)
```

### 处理器类型
- `onnx_rapid_ocr`: RapidOCR (CPU)
- `mineru_ocr`: MinerU HTTP API (GPU)
- `paddlex_ocr`: PaddleX (GPU)

### 环境变量
```bash
# MinerU API
export MINERU_API_URI="http://localhost:30001"

# PaddleX
export PADDLEX_URI="http://localhost:8080"
```

## 主要改进

1. **简化架构**: 从4个处理器减少到3个
2. **统一接口**: 所有处理器实现相同接口
3. **内存优化**: PDF 处理内存占用从 ~800MB 降至 ~150MB
4. **错误处理**: 统一异常处理机制
5. **图片验证**: 强制要求图片文件必须启用 OCR