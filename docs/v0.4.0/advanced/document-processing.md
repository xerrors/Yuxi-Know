# 文档处理与 OCR

系统提供 4 种文档处理选项：

- **RapidOCR**: CPU 友好，无需 GPU，适合基础文字识别
- **MinerU**: 本地化高精度 VLM 解析，适合复杂 PDF 和表格文档
- **MinerU Official**: 官方云服务 API，无需本地部署，开箱即用
- **PaddleX**: 结构化解析，适合表格、票据等特殊格式

## 支持的文件类型

### 常规文档格式
- **文本文档**: `.txt`, `.md`, `.html`, `.htm`
- **Word 文档**: `.docx`
- **PDF 文档**: `.pdf`
- **电子表格**: `.csv`, `.xls`, `.xlsx`
- **JSON 数据**: `.json`

### 图像格式（需要 OCR）
- **常见图片**: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.tif`, `.gif`, `.webp`

### ZIP 压缩包
- **ZIP 文档**: `.zip` - 支持包含 Markdown 文件和图片的压缩包
  - 自动提取和处理 ZIP 包中的 `.md` 文件
  - 自动处理 ZIP 包中的图片文件并上传到对象存储（MINIO）
  - 图片链接会自动替换为可访问的 URL
  - 优先处理名为 `full.md` 的文件，否则使用第一个 `.md` 文件
  - 支持图片目录的智能识别（`images/`、`../images/` 等）

::: tip 图片显示
文档中的图片会自动上传到对象存储并替换为可访问的 URL。但是如果想要在外部正常显示图片，需要配置 `HOST_IP` 环境变量，将其设置为您的服务器 IP 地址。
:::

## 快速配置

### 1. 基础 OCR (RapidOCR)

```bash
# 下载模型
hf download SWHL/RapidOCR --local-dir ./models/SWHL/RapidOCR

# 启动服务
docker compose up -d api
```

需要确保 `MODEL_DIR` 环境变量指向 RapidOCR 上层目录，例如 `./models`。

### 2. 高精度 OCR (MinerU)

需要在 `.env` 文件中配置：

```bash
MINERU_VL_SERVER=http://localhost:30000  # 对应 docker compose 中的 mineru-vllm-server 服务
MINERU_API_URI=http://localhost:30001  # 对应 docker compose 中的 mineru-api 服务
```

然后启动相关服务

```bash
# 需要 GPU，启动 MinerU 服务
docker compose up mineru-vllm-server mineru-api -d

# 启动主服务
docker compose up api -d
```

::: tip 处理超时
文档解析超时时间默认 600 秒，可通过 `MINERU_TIMEOUT` 环境变量调整。
:::


### 3. 官方云服务 (MinerU Official)

API 密钥可以从 [MinerU 官网](https://mineru.net) 申请。

然后在 `.env` 文件中添加

```bash
# 设置 API 密钥环境变量
MINERU_API_KEY="your-api-key-here"
```

然后使用 `docker compose up api -d` 重启后端服务。

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

对应网页中的 `使用 OCR` 选项

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
