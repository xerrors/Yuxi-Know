# 文档处理与 OCR

系统提供 4 种文档处理选项：

- **RapidOCR**: CPU 友好，无需 GPU，适合基础文字识别
- **MinerU**: 本地化高精度 VLM 解析，适合复杂 PDF 和表格文档
- **MinerU Official**: 官方云服务 API，无需本地部署，开箱即用
- **PaddleX**: 结构化解析，适合表格、票据等特殊格式

## 快速配置

### 1. 基础 OCR (RapidOCR)

```bash
# 下载模型
hf download SWHL/RapidOCR --local-dir ./models/SWHL/RapidOCR

# 启动服务
docker compose up -d api
```

### 2. 高精度 OCR (MinerU)

需要配置：

```bash
MINERU_VL_SERVER=http://localhost:30000
MINERU_API_URI=http://localhost:30001
```

然后启动相关服务

```bash
# 需要 GPU，启动 MinerU 服务
docker compose up -d mineru-vllm-server mineru-api

# 启动主服务
docker compose up -d api
```

### 3. 官方云服务 (MinerU Official)


API 密钥可以从 [MinerU 官网](https://mineru.net) 申请。

```bash
# 设置 API 密钥环境变量
export MINERU_API_KEY="your-api-key-here"

# 启动主服务
docker compose up -d api
```

### 4. 结构化解析 (PaddleX)

```bash
# 需要 GPU，启动 PaddleX 服务
docker compose up -d paddlex

# 启动主服务
docker compose up -d api
```

## 处理器选择

| 处理器 | 适用场景 | 硬件要求 | 特点 |
|--------|----------|------------|------|
| **RapidOCR** | 基础文字识别 | CPU | 速度快，资源占用低 |
| **MinerU** | 复杂 PDF、表格、公式 | GPU | 精度高，版面分析好 |
| **MinerU Official** | 复杂文档解析（云服务） | 无特殊要求 | 官方云服务，开箱即用，有 API 配额 |
| **PaddleX** | 表格、票据、结构化文档 | GPU | 专业版面解析 |

## 参数说明

### enable_ocr 选项
- `disable`: 不启用 OCR（PDF 按文本提取，图片**必须选择 OCR 方式**）
- `onnx_rapid_ocr`: RapidOCR 处理
- `mineru_ocr`: MinerU HTTP API 处理
- `mineru_official`: MinerU 官方云服务 API 处理
- `paddlex_ocr`: PaddleX 处理

### 注意事项
- **图片文件必须启用 OCR**，否则无法提取内容
- MinerU 和 PaddleX 需要 GPU 支持
- MinerU Official 需要设置 `MINERU_API_KEY` 环境变量
- RapidOCR 适合 CPU 环境和基础识别需求

## 故障排除

### 常见问题

1. **RapidOCR 模型不存在**
   ```bash
   # 下载模型
   huggingface-cli download SWHL/RapidOCR --local-dir ./models/SWHL/RapidOCR
   ```

2. **GPU 服务连接失败**
   ```bash
   # 检查服务状态
   docker compose ps

   # 查看日志
   docker compose logs mineru
   ```

3. **健康检查**
   ```bash
   # 检查所有 OCR 服务状态
   curl http://localhost:5050/system/health/ocr-services
   ```

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
