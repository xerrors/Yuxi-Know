# 快速开始指南

## 项目简介

Yuxi-Know（语析）是一个基于知识图谱和向量数据库的智能知识库系统，融合了 RAG（检索增强生成）技术与知识图谱技术，为用户提供智能问答和知识管理服务。

### 技术架构

- **后端服务**: FastAPI + Python 3.12+
- **前端界面**: Vue.js 3 + TypeScript
- **知识存储**: Milvus（向量数据库）+ Neo4j（图数据库）
- **智能体框架**: LangGraph
- **文档解析**: LightRAG + MinerU + PP-Structure-V3
- **容器编排**: Docker Compose

### 核心功能

- **智能问答**: 支持多种大语言模型，提供智能对话和问答服务
- **知识库管理**: 支持多种存储形式（Chroma、Milvus、LightRAG）
- **知识图谱**: 自动构建和可视化知识图谱，支持图查询
- **文档解析**: 支持 PDF、Word、图片等多种格式的智能解析
- **权限管理**: 三级权限体系（超级管理员、管理员、普通用户）
- **内容安全**: 内置内容审查机制，保障服务合规性

## 演示视频

<div align="center">
  <a href="https://www.bilibili.com/video/BV1ETedzREgY/?share_source=copy_web&vd_source=37b0bdbf95b72ea38b2dc959cfadc4d8" target="_blank">
    <img width="3651" height="1933" alt="视频演示缩略图" src="https://github.com/user-attachments/assets/eac4fa89-2176-46ae-a649-45a125cb6ed1" />
  </a>
  <p style="margin-top: 12px;">
    <a href="https://www.bilibili.com/video/BV1ETedzREgY/?share_source=copy_web&vd_source=37b0bdbf95b72ea38b2dc959cfadc4d8" target="_blank" style="text-decoration: none; color: #23ade5; font-weight: 500;">
      📽️ 点击查看视频演示 <i class="fa fa-external-link" style="margin-left: 4px;"></i>
    </a>
  </p>
</div>

## 快速开始

### 系统要求

#### 硬件要求
- **CPU**: 2 核心以上
- **内存**: 4GB 以上（推荐 8GB）
- **存储**: 10GB 以上可用空间
- **网络**: 稳定的互联网连接（用于下载模型和依赖）

#### 软件要求
- **Docker**: 20.10+ 版本
- **Docker Compose**: 2.0+ 版本
- **操作系统**: Linux、macOS 或 Windows（支持 WSL2）

#### 可选配置
- **GPU**: NVIDIA GPU（用于 OCR 服务和本地模型推理）
- **CUDA**: 11.8+ 或 12.6+（根据服务选择）

::: tip 提示
项目采用微服务架构，核心服务无需 GPU 支持。GPU 仅用于可选的 OCR 服务和本地模型推理，可通过环境变量配置外部服务。
:::

### 安装步骤

#### 1. 获取项目代码

```bash
# 克隆稳定版本
git clone -b 0.2.1 https://github.com/xerrors/Yuxi-Know.git
cd Yuxi-Know
```

::: warning 版本说明
- `0.2.1`: 当前稳定版本（推荐）
- `stable`: 旧版本稳定分支（与现版本不兼容）
- `main`: 最新开发版本（可能不稳定）
:::

#### 2. 配置环境变量

复制环境变量模板并编辑：

```bash
cp src/.env.template src/.env
```

编辑 `src/.env` 文件，配置必需的 API 密钥：

```env
# 必需配置 - 推荐使用硅基流动免费服务
SILICONFLOW_API_KEY=sk-270ea********8bfa97.e3XOMd****Q1Sk
```

::: tip 免费获取 API Key
[硅基流动](https://cloud.siliconflow.cn/i/Eo5yTHGJ) 注册即送 14 元额度，支持多种开源模型。
:::

#### 3. 启动服务

```bash
# 构建并启动所有服务
docker compose up --build

# 后台运行（推荐）
docker compose up --build -d
```

#### 4. 访问系统

服务启动完成后，访问以下地址：

- **Web 界面**: http://localhost:5173
- **API 文档**: http://localhost:5050/docs

#### 5. 停止服务

```bash
docker compose down
```

### 故障排除

#### 查看服务状态

```bash
# 查看所有容器状态
docker ps

# 查看后端服务日志
docker logs api-dev -f

# 查看前端服务日志
docker logs web-dev -f
```

#### 常见问题

<details>
<summary><strong>Docker 镜像拉取失败</strong></summary>

如果拉取镜像失败，可以尝试手动拉取：

```bash
bash docker/pull_image.sh python:3.11-slim
```

**离线部署方案**：

```bash
# 在有网络的环境保存镜像
bash docker/save_docker_images.sh  # Linux/macOS
powershell -ExecutionPolicy Bypass -File docker/save_docker_images.ps1  # Windows

# 传输到目标设备
scp docker_images_xxx.tar <user>@<dev_host>:<path_to_save>

# 在目标设备加载镜像
docker load -i docker_images_xxx.tar
```

</details>

<details>
<summary><strong>构建失败</strong></summary>

如果构建失败，通常是网络问题，可以配置代理：

```bash
export HTTP_PROXY=http://IP:PORT
export HTTPS_PROXY=http://IP:PORT
```

如果已配置代理但构建失败，尝试移除代理后重试。

</details>

<details>
<summary><strong>Milvus 启动失败</strong></summary>

```bash
# 重启 Milvus 服务
docker compose up milvus -d
docker restart api-dev
```

</details>


## 模型配置

### 对话模型

系统支持多种大语言模型服务商，通过配置对应的 API 密钥即可使用：

| 服务商 | 环境变量 | 特点 |
|--------|----------|------|
| 硅基流动 | `SILICONFLOW_API_KEY` | 🆓 免费额度，默认推荐 |
| OpenAI | `OPENAI_API_KEY` | GPT 系列模型 |
| DeepSeek | `DEEPSEEK_API_KEY` | 国产大模型 |
| OpenRouter | `OPENROUTER_API_KEY` | 多模型聚合平台 |
| 智谱清言 | `ZHIPUAI_API_KEY` | GLM 系列模型 |
| 阿里云百炼 | `DASHSCOPE_API_KEY` | 通义千问系列 |

#### 自定义模型供应商

如需添加新的模型供应商，请按以下步骤操作：

1. 编辑 `src/config/static/models.yaml` 文件
2. 在 `.env` 文件中添加对应的环境变量
3. 重新部署项目

**配置示例**：

```yaml
custom-provider-name:
  name: custom-provider-name
  default: custom-model-name
  base_url: "https://api.your-provider.com/v1"
  env:
    - CUSTOM_API_KEY_ENV_NAME
  models:
    - supported-model-name
```

### 嵌入模型和重排序模型

::: warning 重要说明
从 v0.2 版本开始，项目采用微服务架构，模型部署与项目本身完全解耦。如需使用本地模型，需要先通过 vLLM 或 Ollama 部署为 API 服务。
:::

#### 本地模型部署

**1. 配置模型信息**

在 `src/config/static/models.yaml` 或 `src/config/static/models.private.yaml` 中添加配置：

```yaml
EMBED_MODEL_INFO:
  vllm/Qwen/Qwen3-Embedding-0.6B:
    name: Qwen/Qwen3-Embedding-0.6B
    dimension: 1024
    base_url: http://localhost:8000/v1/embeddings
    api_key: no_api_key

RERANKER_LIST:
  vllm/BAAI/bge-reranker-v2-m3:
    name: BAAI/bge-reranker-v2-m3
    base_url: http://localhost:8000/v1/rerank
    api_key: no_api_key
```

**2. 启动模型服务**

```bash
# 启动嵌入模型
vllm serve Qwen/Qwen3-Embedding-0.6B \
  --task embed \
  --dtype auto \
  --port 8000

# 启动重排序模型
vllm serve BAAI/bge-reranker-v2-m3 \
  --task score \
  --dtype fp16 \
  --port 8000
```

### OpenAI 兼容模型

系统理论上兼容任何 OpenAI 兼容的模型服务，包括：

- **vLLM**: 高性能推理服务
- **Ollama**: 本地模型管理
- **API 中转服务**: 各种代理和聚合服务

在 Web 界面的"设置"页面中可以添加本地模型地址。


## 功能详解

### 知识库管理

系统支持多种知识库存储形式，满足不同场景需求：

| 存储类型 | 特点 | 适用场景 |
|----------|------|----------|
| **Chroma** | 轻量级向量数据库 | 小型项目、快速原型 |
| **Milvus** | 高性能向量数据库 | 大规模生产环境 |
| **LightRAG** | 图增强检索 | 复杂知识关系 |

#### 知识库可视化

<table>
  <tbody>
    <tr>
      <td><img src="https://github.com/user-attachments/assets/6ad3cc6a-3816-4545-b074-6eeb814d8124" alt="知识图谱可视化"></td>
      <td><img src="https://github.com/user-attachments/assets/6cc3c3a6-b7c2-4dc3-9678-b97de7835959" alt="知识库可视化"></td>
      <td><img src="/images/neo4j_browser.png"></td>
    </tr>
  </tbody>
</table>

### 知识图谱

#### LightRAG 自动构建

系统支持基于 [LightRAG](https://github.com/HKUDS/LightRAG) 的知识图谱自动构建：

1. **创建 LightRAG 知识库**: 在知识库管理中选择 LightRAG 类型
2. **上传文档**: 系统自动解析文档并构建知识图谱
3. **图谱导入**: 构建的图谱自动导入 Neo4j 数据库
4. **标签区分**: 使用不同标签区分不同来源的图谱数据

::: warning 使用限制
- LightRAG 知识库可在知识库详情中可视化
- 不支持在侧边栏图谱中直接检索
- 图谱检索工具不支持 LightRAG 知识库
- 查询需要使用对应的知识库作为工具
:::

#### 图谱构建模型

默认使用 `siliconflow` 的 `Qwen/Qwen3-30B-A3B-Instruct-2507` 模型，可通过环境变量自定义：

```env
LIGHTRAG_LLM_PROVIDER=siliconflow
LIGHTRAG_LLM_NAME=Qwen/Qwen3-30B-A3B-Instruct-2507
```

#### 图谱可视化

<table>
  <thead>
    <tr>
      <th>知识图谱可视化</th>
      <th>知识库可视化</th>
      <th>Neo4J管理端</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><img src="https://github.com/user-attachments/assets/87b1dc91-65f4-4529-84b3-1b2a561c580d" alt="知识图谱可视化" height="210"></td>
      <td><img src="https://github.com/user-attachments/assets/452b8228-a59f-4f28-80ce-7d93e9497ccc" alt="知识库可视化" height="210"></td>
    </tr>
  </tbody>
</table>


#### 外部图谱导入

系统支持导入已有的知识图谱数据到 Neo4j 中：

**数据格式**: JSONL 格式，每行一个三元组

```jsonl
{"h": "北京", "t": "中国", "r": "首都"}
{"h": "上海", "t": "中国", "r": "直辖市"}
```

**导入规则**:
- 节点自动添加 `Upload`、`Entity` 标签
- 关系自动添加 `Relation` 标签
- 通过 `name` 属性访问实体名称
- 通过 `type` 属性访问关系名称

**Neo4j 访问信息**:
- 默认账户: `neo4j`
- 默认密码: `0123456789`
- 管理界面: http://localhost:7474

::: tip 测试数据
可以使用 `test/data/A_Dream_of_Red_Mansions_tiny.jsonl` 文件进行测试导入。
:::

#### 外部 Neo4j 接入

如需接入已有的 Neo4j 实例，可修改 `docker-compose.yml` 中的 `NEO4J_URI` 配置。

::: warning 注意事项
确保每个节点都有 `Entity` 标签，每个关系都有 `RELATION` 类型，否则会影响图的检索与构建功能。
:::

## 高级配置

### OCR 服务

系统提供多种 OCR 服务选项，满足不同精度和性能需求：

#### 基础 OCR 服务

使用 RapidOCR ONNX 版本，无需 GPU 支持：

**1. 下载模型**

```bash
huggingface-cli download SWHL/RapidOCR --local-dir ${MODEL_DIR:-./models}/SWHL/RapidOCR
```

**2. 模型要求**

确保以下文件存在：
- `PP-OCRv4/ch_PP-OCRv4_det_infer.onnx`
- `PP-OCRv4/ch_PP-OCRv4_rec_infer.onnx`

::: warning 权限问题
如果提示 `[Errno 13] Permission denied`，需要使用 sudo 修改权限后执行。
:::

#### 高级 OCR 服务

为提升 PDF 解析准确性，可选择以下 GPU 加速服务：

**MinerU 服务**（推荐）

```bash
# 需要 CUDA 12.6+ 环境
docker compose up mineru --build
```

**PP-Structure-V3 服务**

```bash
# 需要 CUDA 11.8+ 环境
docker compose up paddlex --build
```

配置文件位置: `docker/PP-StructureV3.yaml`

### 智能体开发

系统基于 [LangGraph](https://github.com/langchain-ai/langgraph) 框架，支持自定义智能体应用开发。

#### 内置智能体

系统默认集成三个示例智能体：

| 智能体 | 功能 | 位置 |
|--------|------|------|
| **基础智能体** | 简单对话功能 | `src/agents/chatbot/` |
| **ReAct 智能体** | 推理与行动循环 | `src/agents/react/` |
| **DeepResearch 智能体** | 深度研究分析 | `src/agents/deepresearch/` |

#### 开发自定义智能体

**1. 创建智能体类**

继承 `BaseAgent` 并实现 `get_graph` 方法：

```python
from .base import BaseAgent

class CustomAgent(BaseAgent):
    def get_graph(self):
        # 返回 LangGraph 实例
        return graph_instance

    @property
    def context_schema(self):
        # 定义配置参数
        return schema
```

**2. 注册智能体**

在 `src/agents/__init__.py` 中注册：

```python
from .custom_agent import CustomAgent

agent_manager = AgentManager()
agent_manager.register_agent(CustomAgent)
agent_manager.init_all_agents()
```

**3. 参考示例**

查看 `src/agents/react/graph.py` 中的 `ReActAgent` 实现示例。

### MySQL 数据库集成

系统支持智能体查询 MySQL 数据库，为数据分析提供强大支持。

#### 配置数据库连接

在环境变量中配置数据库信息：

```env
# MySQL 数据库配置
MYSQL_HOST=192.168.1.100
MYSQL_USER=username
MYSQL_PASSWORD=your_secure_password
MYSQL_DATABASE=database_name
MYSQL_PORT=3306
MYSQL_CHARSET=utf8mb4
```

#### 可用工具

在智能体配置中启用以下 MySQL 工具：

| 工具名称 | 功能描述 |
|----------|----------|
| `mysql_list_tables` | 获取数据库中的所有表名 |
| `mysql_describe_table` | 获取指定表的详细结构信息 |
| `mysql_query` | 执行只读的 SQL 查询语句 |

#### 安全特性

- ✅ **只读操作**: 仅允许 SELECT、SHOW、DESCRIBE、EXPLAIN 操作
- ✅ **SQL 注入防护**: 严格的表名参数验证
- ✅ **超时控制**: 默认 10 秒，最大 60 秒
- ✅ **结果限制**: 默认 10000 字符，100 行，最大 1000 行

#### 使用建议

1. **权限设置**: 确保数据库用户只有只读权限
2. **大表查询**: 建议使用 LIMIT 子句限制结果
3. **复杂查询**: 可能需要调整超时时间
4. **结果处理**: 查询结果过大会被自动截断并提示

### 图表可视化 - MCP

系统支持基于 MCP（Model Context Protocol）的图表可视化功能。

#### 功能特点

- 基于 @antvis 团队开发的 [可视化图表-MCP-Server](https://www.modelscope.cn/mcp/servers/@antvis/mcp-server-chart)
- 支持多种图表类型和数据可视化
- 通过魔搭社区配置 Host 资源

#### 配置方法

在 `src/agents/common/mcp.py` 的 `MCP_SERVERS` 中添加配置：

```python
# MCP Server configurations
MCP_SERVERS = {
    "sequentialthinking": {
        "url": "https://remote.mcpservers.org/sequentialthinking/mcp",
        "transport": "streamable_http",
    },
    "mcp-server-chart": {
        "url": "https://mcp.api-inference.modelscope.net/9993ae42524c4c/mcp",
        "transport": "streamable_http",
    }
}
```

::: warning 配置注意
记得将 `type` 字段修改为 `transport`。
:::

### 内容安全

系统内置内容审查机制，保障服务内容的合规性。

#### 功能特点

- **输入过滤**: 对用户输入进行关键词检测
- **输出审查**: 对模型生成内容进行安全审查
- **实时拦截**: 防止不当内容传播

#### 配置方法

管理员可在 `设置` → `基本设置` 页面中：

- ✅ 一键启用/禁用内容审查功能
- ✅ 自定义敏感词词库
- ✅ 调整审查策略

#### 敏感词管理

敏感词词库位于 `src/config/static/bad_keywords.txt` 文件：

- 每行一个关键词
- 支持自定义修改
- 实时生效，无需重启服务



### 服务端口

系统使用多个端口提供不同服务，以下是完整的端口映射：

| 端口 | 服务 | 容器名称 | 说明 |
|------|------|----------|------|
| **5173** | Web 前端 | web-dev | 用户界面 |
| **5050** | API 后端 | api-dev | 核心服务 |
| **7474/7687** | Neo4j | graph | 图数据库 |
| **9000/9001** | MinIO | milvus-minio | 对象存储 |
| **19530/9091** | Milvus | milvus | 向量数据库 |
| **30000** | MinerU | mineru | PDF 解析（可选）|
| **8080** | PaddleX | paddlex-ocr | OCR 服务（可选）|
| **8081** | vLLM | - | 本地推理（可选）|

::: tip 端口访问
- Web 界面: http://localhost:5173
- API 文档: http://localhost:5050/docs
- Neo4j 管理: http://localhost:7474
:::


### 品牌定制

系统支持完整的品牌信息自定义，包括 Logo、组织名称、版权信息等。

#### 配置方法

**1. 复制模板文件**

```bash
cp src/config/static/info.template.yaml src/config/static/info.local.yaml
```

**2. 编辑品牌信息**

在 `src/config/static/info.local.yaml` 中配置：

```yaml
# 组织信息
organization_name: "您的组织名称"
logo_url: "/path/to/your/logo.png"

# 版权信息
copyright: "© 2024 您的组织名称"
```

**3. 环境变量配置**

或在 `.env` 文件中指定配置文件路径：

```env
YUXI_BRAND_FILE_PATH=src/config/static/info.local.yaml
```

#### 样式定制

系统配色主要保存在 `web/src/assets/css/base.css` 中：

- 替换 `--main-*` 相关变量即可改变配色
- 支持主题色、辅助色等完整定制
- 实时预览，无需重启服务

::: tip 配置优先级
`info.local.yaml` > `info.template.yaml`（默认）
:::

### 批量处理脚本

系统提供便捷的批量处理脚本，支持文件上传和解析操作。

#### 文件上传脚本

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

#### 文件解析脚本

使用 `scripts/batch_upload.py trans` 将文件解析为 Markdown：

```bash
# 批量解析文档
uv run scripts/batch_upload.py trans \
    --db-id your_kb_id \
    --directory path/to/your/data \
    --output-dir path/to/output_markdown \
    --pattern "*.docx" \
    --base-url http://127.0.0.1:5050/api \
    --username your_username \
    --password your_password \
    --concurrency 4 \
    --recursive
```

**输出结果**: 解析后的 Markdown 文件将保存到指定输出目录。

## 常见问题

### 服务管理

**Q: 如何查看后端服务日志？**

```bash
# 查看后端日志
docker logs api-dev -f

# 查看前端日志
docker logs web-dev -f

# 查看所有服务状态
docker ps
```

### OCR 服务

**Q: RapidOCR 模型未找到怎么办？**

确认以下文件存在：
- `MODEL_DIR` 指向的目录存在 `SWHL/RapidOCR`
- 包含 `PP-OCRv4` 下的 `det_infer.onnx` 和 `rec_infer.onnx` 文件

**Q: MinerU/PaddleX 健康检查失败？**

分别检查服务状态：
- MinerU: http://localhost:30000/health
- PaddleX: http://localhost:8080/

确认 GPU/驱动与 CUDA 版本匹配。

### 数据库连接

**Q: Milvus 启动失败？**

```bash
# 重启 Milvus 服务
docker compose up milvus -d
docker restart api-dev
```

**Q: Neo4j 连接问题？**

检查默认账户信息：
- 用户名: `neo4j`
- 密码: `0123456789`
- 管理界面: http://localhost:7474

## 参与贡献

感谢所有贡献者的支持！

<a href="https://github.com/xerrors/Yuxi-Know/contributors">
    <img src="https://contributors.nn.ci/api?repo=xerrors/Yuxi-Know" alt="贡献者名单">
</a>

### 如何贡献

1. **Fork 项目**: 在 GitHub 上 Fork 本项目
2. **创建分支**: `git checkout -b feature/amazing-feature`
3. **提交更改**: `git commit -m 'Add some amazing feature'`
4. **推送分支**: `git push origin feature/amazing-feature`
5. **创建 PR**: 在 GitHub 上创建 Pull Request

### 开发指南

- 遵循项目代码规范
- 添加必要的测试用例
- 更新相关文档
- 确保所有测试通过
