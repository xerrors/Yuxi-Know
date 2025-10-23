# 文档解析

## OCR 服务

系统提供多种 OCR 服务选项，满足不同精度和性能需求。

### 基础 OCR 服务

使用 RapidOCR ONNX 版本，无需 GPU 支持：

#### 1. 下载模型

```bash
huggingface-cli download SWHL/RapidOCR --local-dir ${MODEL_DIR:-./models}/SWHL/RapidOCR
```

#### 2. 模型要求

确保以下文件存在：
- `PP-OCRv4/ch_PP-OCRv4_det_infer.onnx`
- `PP-OCRv4/ch_PP-OCRv4_rec_infer.onnx`

::: warning 权限问题
如果提示 `[Errno 13] Permission denied`，需要使用 sudo 修改权限后执行。
:::

### 高级 OCR 服务

为提升 PDF 解析准确性，可选择以下 GPU 加速服务：

#### 1. MinerU 服务（推荐）

```bash
# 需要 CUDA 12.6+ 环境
docker compose up mineru --build
```

#### 2. PP-Structure-V3 服务

```bash
# 需要 CUDA 11.8+ 环境
docker compose up paddlex --build
```

**配置文件**: `docker/PP-StructureV3.yaml`

### OCR 服务选择建议

- **基础使用**: RapidOCR（无需 GPU）
- **高精度需求**: MinerU（推荐）
- **结构化文档**: PP-Structure-V3
- **生产环境**: 根据硬件条件选择

### `enable_ocr` 取值说明（入库参数）

- `disable`：不启用 OCR（PDF 将按纯文本提取，图片会自动转为 `onnx_rapid_ocr` 提示）
- `onnx_rapid_ocr`：CPU 友好，安装简单
- `mineru_ocr`：GPU 加速，复杂文档效果好
- `paddlex_ocr`：结构化表格/票据等场景

## 批量处理脚本

系统提供便捷的批量处理脚本，用于高效批量上传文档。

### 文件上传脚本

使用 `scripts/batch_upload.py upload` 批量上传文件到知识库：

```bash
# 批量上传文档
uv run scripts/batch_upload.py upload \
    --db-id your_kb_id \
    --directory path/to/your/data \
    --pattern "*.docx" \
    --base-url http://127.0.0.1:5050/api \
    --username your_username \
    --password your_password \
    --concurrency 4 \
    --recursive \
    --record-file scripts/tmp/batch_processed_files.txt
```

**参数说明**:
- `--db-id`: 目标知识库 ID
- `--directory`: 文件目录路径
- `--pattern`: 文件匹配模式
- `--concurrency`: 并发处理数量
- `--recursive`: 递归处理子目录
- `--record-file`: 处理记录文件路径

提示：系统按“内容哈希”进行去重；同一知识库已存在相同内容的文件会被拒绝（409）。

### 脚本功能

- **进度跟踪**: 实时显示处理进度
- **错误处理**: 自动跳过无法处理的文件
- **断点续传**: 支持中断后继续处理
- **日志记录**: 详细记录处理过程
- **结果统计**: 处理完成后显示统计信息

更多关于“入库参数、导出数据、支持类型”等，请参阅：介绍 → 知识库与知识图谱 → 文档管理。
