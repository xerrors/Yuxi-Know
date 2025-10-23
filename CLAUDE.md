# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

**语析 (Yuxi-Know)** 是一个基于大模型的智能知识库与知识图谱问答系统，融合了 RAG（检索增强生成）与知识图谱技术。

- **技术栈**: FastAPI + Vue.js 3 + LangGraph + LightRAG + Neo4j + Milvus
- **Python版本**: ≥3.11
- **当前版本**: v0.3.0-beta
- **许可证**: MIT

## 开发命令

### Docker 环境管理

```bash
# 启动所有服务
make start
# 或: docker compose up -d

# 停止所有服务
make stop
# 或: docker compose down

# 查看后端日志
make logs
# 或: docker logs --tail=50 api-dev
```

### 代码质量

```bash
# 代码检查
make lint
# 或: uv run python -m ruff check .

# 代码格式化
make format
# 或: uv run ruff format . && uv run ruff check . --fix

# 查看格式化差异
make format_diff
# 或: uv run ruff format --diff .
```

### 测试

```bash
# 运行 API 单元测试
make router-tests
# 或: docker compose exec -T api uv run --group test pytest test/api

# 运行特定测试文件
docker compose exec -T api uv run --group test pytest test/api/test_xxx.py

# 带覆盖率报告
docker compose exec -T api uv run --group test pytest test/ --cov=src --cov-report=html
```

## 架构设计

### 分层架构

```
前端层 (Vue.js 3)
    ↓ HTTP/REST API
API层 (FastAPI)
    ↓
业务逻辑层 (Service)
    ├─ 智能体系统 (Agent - LangGraph)
    ├─ 知识库管理 (KnowledgeBase)
    ├─ 任务管理 (Tasker)
    └─ 认证服务 (Auth)
    ↓
数据访问层
    ├─ SQLite (对话、用户、统计)
    ├─ Neo4j (知识图谱)
    ├─ Milvus/Chroma (向量数据库)
    └─ MinIO (文件存储)
```

### 核心目录结构

```
src/                       # 核心Python源代码
├── agents/                # 智能体框架 (LangGraph)
│   ├── chatbot/           # 聊天机器人智能体
│   ├── react/             # ReAct智能体
│   └── common/            # 通用组件 (工具、模型、上下文)
├── knowledge/             # 知识库核心模块
│   ├── implementations/   # 具体实现 (Milvus, Chroma, LightRAG)
│   └── manager.py         # 知识库管理器
├── models/                # LLM模型加载 (chat, embed, rerank)
├── storage/               # 数据存储层
│   ├── db/                # SQLite ORM模型
│   ├── minio/             # MinIO对象存储
│   └── conversation/      # 对话历史管理
├── config/                # 配置管理
│   └── static/            # 静态配置 (models.yaml, agents_meta.yaml)
├── plugins/               # 文档处理插件 (MinerU, PaddleOCR)
└── utils/                 # 工具函数

server/                    # FastAPI应用层
├── main.py                # FastAPI应用入口
├── routers/               # API路由 (7个主要路由)
│   ├── auth_router.py     # /api/auth/*
│   ├── chat_router.py     # /api/chat/*
│   ├── knowledge_router.py # /api/knowledge/*
│   ├── graph_router.py    # /api/graph/*
│   ├── dashboard_router.py # /api/dashboard/*
│   ├── system_router.py   # /api/system/*
│   └── task_router.py     # /api/tasks/*
├── services/              # 业务逻辑服务
│   └── tasker.py          # 后台异步任务管理器
└── utils/                 # 服务层工具 (认证、用户管理)

web/                       # Vue.js前端应用
├── src/
│   ├── views/             # 页面视图
│   ├── components/        # 可复用组件
│   ├── layouts/           # 布局模板 (AppLayout, BlankLayout)
│   ├── router/            # Vue Router配置
│   ├── stores/            # Pinia状态管理
│   ├── apis/              # API调用层
│   └── utils/             # 前端工具函数
└── vite.config.js         # Vite构建配置
```

## 关键架构决策

### 1. 智能体系统 (LangGraph)

所有智能体基于 **LangGraph** 的状态机模型构建：

- **状态定义**: `messages[]`, `context` (包含 system_prompt, model, tools, mcps)
- **节点**: `llm_call` (调用LLM), `dynamic_tools_node` (工具执行)
- **边**: 通过 `tools_condition` 判断是否需要工具调用
- **持久化**: 使用 SQLite Checkpointer 支持中断恢复

**可用工具**:
- 知识库查询工具
- 知识图谱查询工具
- Web搜索工具 (Tavily)
- 计算器工具
- MySQL查询工具

### 2. 知识库系统

支持三种知识库实现：

- **Milvus**: 生产级向量数据库
- **Chroma**: 轻量级向量数据库
- **LightRAG**: 图增强检索系统，自动构建知识图谱

所有知识库通过 `KnowledgeBaseFactory` 工厂模式创建，由 `KnowledgeBaseManager` 统一管理。

### 3. 异步任务系统 (Tasker)

所有耗时操作（文档处理、知识图谱构建）均通过 **Tasker** 异步队列处理：

- **任务队列**: FIFO队列管理
- **进度跟踪**: 实时更新任务状态
- **结果存储**: 完成后存储到 SQLite
- **失败重试**: 支持失败回调处理

### 4. 文档处理

支持多种格式文档：

- **文本**: `.txt`, `.md`
- **文档**: `.doc`, `.docx`, `.pdf`
- **网页**: `.html`, `.htm`
- **数据**: `.json`, `.csv`, `.xls`, `.xlsx`
- **图片**: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff` (需要 OCR)

处理流程：
1. 选择合适的解析器 (MinerU for PDF, PaddleOCR for images)
2. 文本提取与分块
3. Embedding 向量化
4. 存储到向量数据库
5. 可选：知识图谱构建 (LightRAG)

## 配置管理

### 环境变量配置

项目根目录 `.env` 文件（从 `.env.template` 复制）:

```bash
# 模型提供商 API Key (推荐使用硅基流动)
SILICONFLOW_API_KEY=xxx
OPENAI_API_KEY=xxx
DEEPSEEK_API_KEY=xxx
ZHIPUAI_API_KEY=xxx

# 数据库配置
NEO4J_URI=bolt://graph:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=0123456789
MILVUS_URI=http://milvus:19530

# 文档处理服务 (需要GPU)
MINERU_OCR_URI=http://mineru:30000
PADDLEX_URI=http://paddlex:8080

# Web搜索 (可选)
TAVILY_API_KEY=xxx
```

### 模型配置

`src/config/static/models.yaml` 定义所有可用的 LLM 和 Embedding 模型：

- **LLM模型**: 支持 OpenAI, DeepSeek, SiliconFlow, Together, ZhipuAI 等
- **Embedding模型**: 支持 OpenAI, HuggingFace 本地模型
- **重排序模型**: 支持 Jina Reranker

## 数据库服务

### Docker Compose 服务

| 服务名 | 端口 | 用途 |
|--------|------|------|
| `api-dev` | 5050 | FastAPI后端服务 |
| `web-dev` | 5173 | Vue.js前端服务 |
| `graph` (Neo4j) | 7474/7687 | 知识图谱数据库 |
| `milvus` | 19530 | 向量数据库 |
| `minio` | 9000/9001 | 对象存储 |
| `etcd` | 2379 | Milvus元数据存储 |

### 访问地址

- **Web界面**: http://localhost:5173
- **API文档**: http://localhost:5050/docs
- **Neo4j浏览器**: http://localhost:7474

## 开发最佳实践

### 后端开发

1. **路由**: 新增 API 路由在 `server/routers/` 下，并在 `server/routers/__init__.py` 注册
2. **业务逻辑**: 核心业务代码放在 `src/` 下，避免在路由中编写复杂逻辑
3. **异步任务**: 耗时操作必须使用 Tasker 异步处理
4. **代码规范**: 提交前运行 `make lint` 和 `make format`
5. **测试**: 为新增 API 编写单元测试 `test/api/test_xxx.py`

### 前端开发

1. **API调用**: 统一在 `web/src/apis/` 下定义 API 函数
2. **状态管理**: 使用 Pinia stores (`web/src/stores/`)
3. **组件**: 可复用组件放在 `web/src/components/`
4. **样式**: 使用 Less，参考 `web/src/assets/css/base.css` 配色系统
5. **热更新**: Vite 支持热更新，无需重启容器

### 智能体开发

1. **工具定义**: 在 `src/agents/common/tools.py` 定义新工具
2. **工具包**: 复杂工具可创建 toolkit，如 `src/agents/common/toolkits/mysql/`
3. **LangGraph状态**: 在智能体 graph 定义中添加自定义 State 字段
4. **上下文管理**: 使用 `Context` 对象传递智能体配置

## 重要文件

| 文件 | 用途 |
|------|------|
| `src/config/app.py` | 全局配置管理 |
| `server/main.py` | FastAPI应用入口 |
| `src/knowledge/manager.py` | 知识库管理器 |
| `src/agents/chatbot/graph.py` | LangGraph智能体定义 |
| `server/services/tasker.py` | 异步任务管理器 |
| `src/storage/db/models.py` | SQLAlchemy ORM模型 |
| `docker-compose.yml` | 服务编排配置 |
| `pyproject.toml` | Python依赖与工具配置 |
| `web/src/router/index.js` | 前端路由配置 |

## 常见问题

1. **Milvus启动失败**: `docker compose up milvus -d && docker restart api-dev`
2. **模型加载失败**: 检查 `.env` 中的 API Key 是否正确配置
3. **任务卡住**: 查看 Tasker 日志，可能是工具执行超时
4. **前端无法连接后端**: 检查 Vite 配置中的代理设置

## v0.3 重大变更

- **.env 文件位置**: 从 `src/.env` 移到项目根目录
- **数据库重构**: 不再使用 MemorySaver，改用新的存储结构
- **自定义模型移除**: 改用自定义 provider 方式
- **新增功能**: Dashboard 统计、消息反馈、用户管理增强

## 文档资源

- **在线文档**: https://xerrors.github.io/Yuxi-Know/
- **视频演示**: https://www.bilibili.com/video/BV1ETedzREgY/
