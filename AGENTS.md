
# 项目目录结构 (Project Overview)

Yuxi-Know 是一个基于知识图谱和向量数据库的智能知识库系统。它通过 FastAPI 提供后端 API，使用 Vue.js 构建前端界面，并利用 Docker Compose 进行整体服务的编排和管理。


```
Yuxi-Know/
├── docker/              # Docker 配置文件
├── scripts/             # 脚本文件，如批量上传等
├── server/              # 服务端代码（部分）
├── src/                 # 主要源代码目录
│   ├── agents/          # 智能体应用
│   ├── config/          # 配置文件
│   ├── knowledge/       # 知识库相关
│   ├── models/          # 数据模型
│   ├── plugins/         # 插件（存放OCR）
│   ├── static/          # 静态资源（配置文件）
│   └── utils/           # 工具函数
├── web/                 # 前端代码
└── docker-compose.yml   # Docker Compose 配置
```

# 核心服务与容器 (Core Services & Containers)

项目使用 Docker Compose 管理多个服务，主要容器名称如下：
- `api-dev` - FastAPI 后端服务
- `web-dev` - Vue.js 前端开发服务器
- `graph` - Neo4j 图数据库
- `milvus` - 向量数据库，包含 etcd 和 MinIO 依赖
- `mineru` - 可选的 MinerU OCR 服务（需要 GPU）
- `paddlex` - 可选的 PaddleX OCR 服务（需要 GPU）

## 开发与调试工作流 (Development & Debugging Workflow)

本项目完全通过 Docker Compose 进行管理。所有开发和调试都应在运行的容器环境中进行。使用 `docker compose up -d` 命令进行构建和启动。

核心原则: 由于 api-dev 和 web-dev 服务均配置了热重载 (hot-reloading)，本地修改代码后无需重启容器，服务会自动更新。应该先检查项目是否已经在后台启动（`docker ps`），具体的可以阅读 [docker-compose.yml](docker-compose.yml).

## 风格说明

- UI风格要简洁，同时要保持一致性，颜色要尽量参考 [base.css](web/src/assets/css/base.css) 中的颜色。不要悬停位移，不要过度使用阴影以及渐变色。
- Python 代码要符合 Python 的规范，尽量使用较新的语法，避免使用旧版本的语法（版本兼容到 3.12+），使用 uvx ruff check 检查 lint。
