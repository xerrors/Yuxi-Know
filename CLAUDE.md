# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Yuxi-Know 是一个基于大模型的智能知识库与知识图谱智能体开发平台，融合了 RAG 技术与知识图谱技术，基于 LangGraph v1 + Vue.js + FastAPI + LightRAG 架构构建。项目完全通过 Docker Compose 进行管理，支持热重载开发。

## 开发环境管理

### 核心原则
- 所有开发调试都应在运行的 Docker 容器环境中进行
- 使用 `docker compose up -d` 启动完整开发环境
- api-dev 和 web-dev 服务均配置热重载，本地修改代码后无需重启容器
- 先检查 `docker ps` 确认服务状态，使用 `docker logs api-dev --tail 100` 查看日志

### 常用命令

#### 项目启动和停止
```bash
# 启动所有服务
make start
# 或
docker compose up -d

# 停止所有服务
make stop
# 或
docker compose down

# 查看日志
make logs
# 或
docker logs --tail=50 api-dev
```

#### 后端开发（在 Docker 容器内）
```bash
# 代码检查和格式化
make lint          # 检查代码规范
make format        # 格式化代码
make format_diff   # 查看格式化差异

# 运行测试
make router-tests  # 运行 API 路由测试

# 直接在容器内执行命令
docker compose exec api uv run python your_script.py
```

#### 前端开发
```bash
# 在 web 目录下执行
pnpm run dev        # 开发模式（已通过 Docker 配置）
pnpm run build      # 构建生产版本
pnpm run lint       # ESLint 检查
pnpm run format     # Prettier 格式化
```

#### 文档开发
```bash
# 在 docs 目录下执行
pnpm run docs:dev   # 开发文档
pnpm run docs:build # 构建文档
```

## 项目架构

### 技术栈
- **后端**: FastAPI + Python 3.11+，使用 uv 管理依赖
- **前端**: Vue 3.5 + Vite 7 + Ant Design Vue + Pinia
- **AI框架**: LangChain v1 + LangGraph v1 + LightRAG
- **数据库**: Neo4j (图数据库) + Milvus (向量数据库) + MinIO (对象存储)
- **容器化**: Docker Compose 多服务编排

### 核心目录结构
```
├── server/          # FastAPI 后端服务
├── web/             # Vue.js 前端应用
├── src/             # 核心业务逻辑代码
├── docs/            # 文档中心 (VitePress)
├── test/            # 测试代码
├── docker/          # Docker 配置文件
├── scripts/         # 脚本工具
├── saves/           # 数据保存目录
├── models/          # 模型文件目录
└── docker-compose.yml
```

### 主要服务
- `api-dev`: FastAPI 后端服务 (端口 5050)
- `web-dev`: Vue.js 前端服务 (端口 5173)
- `graph`: Neo4j 图数据库 (端口 7474, 7687)
- `milvus`: Milvus 向量数据库 (端口 19530)
- `minio`: MinIO 对象存储 (端口 9000, 9001)
- `mineru`: MinerU 文档解析服务 (可选)
- `paddlex`: PaddleX OCR 服务 (可选)

## 开发规范

### 前端开发规范
- **API 接口**: 所有 API 接口定义在 `web/src/apis` 下，继承自 `apiGet/apiPost/apiRequest`
- **图标**: 从 `@ant-design/icons-vue` 或 `lucide-vue-next` 选取
- **样式**: 使用 Less，优先采用 `web/src/assets/css/base.css` 中的颜色
- **UI风格**: 简洁一致，避免悬停位移、过度阴影和渐变色
- **组件库**: 基于 Ant Design Vue，保持组件一致性

### 后端开发规范
- **包管理**: 使用 uv 管理依赖，调试时使用 `uv run`
- **代码规范**: 符合 Pythonic 风格，支持 Python 3.12+ 语法
- **代码质量**: 使用 `make lint` 检查，`make format` 格式化
- **API设计**: 遵循 RESTful 规范，使用 Pydantic 进行数据验证

### 通用开发规范
- **文档更新**: 代码更新后同步更新 `docs/latest` 中的相关文档
- **测试**: 测试脚本放在 `test/` 目录，从 Docker 容器中运行
- **环境变量**: 配置通过 `.env` 文件管理
- **数据安全**: 敏感数据不提交到版本控制

## 特色功能模块

### 智能体系统
- 基于 LangGraph v1 的智能体框架
- 支持多代理协作和工具调用
- 提供完整的智能体开发套件

### 知识管理
- 多模态文档解析 (PDF、Word、图片等)
- 知识图谱自动构建和可视化
- 向量化存储和检索

### 数据处理
- MinerU 文档解析集成
- PaddleX OCR 文字识别
- 支持多种模型提供商 (OpenAI、DeepSeek、阿里云等)

## 调试和故障排除

### 常见问题排查
1. **服务启动失败**: 检查端口占用和 Docker 服务状态
2. **API 连接问题**: 确认 `VITE_API_URL` 环境变量配置
3. **模型加载问题**: 检查 `models/` 目录和权限设置
4. **数据库连接**: 确认 Neo4j 和 Milvus 服务健康状态

### 日志查看
```bash
# 查看各服务日志
docker logs api-dev --tail 100
docker logs web-dev --tail 50
docker logs graph --tail 50
docker logs milvus --tail 50
```

### 性能监控
- 使用健康检查端点 `/api/system/health`
- 监控 GPU 使用情况 (如果使用 GPU 服务)
- 检查内存和磁盘使用情况

You MUST read `./AGENTS.md`