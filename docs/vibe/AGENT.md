
# 项目目录结构

```
Yuxi-Know/
├── docker/              # Docker 配置文件
├── docs/                # 项目文档
├── scripts/             # 脚本文件，如批量上传等
├── server/              # 服务端代码（部分）
├── src/                 # 主要源代码目录
│   ├── agents/          # 智能体应用
│   ├── config/          # 配置文件
│   ├── knowledge/       # 知识库相关
│   ├── models/          # 数据模型
│   ├── plugins/         # 插件
│   ├── static/          # 静态资源
│   └── utils/           # 工具函数
├── web/                 # 前端代码
└── docker-compose.yml   # Docker Compose 配置
```

# 主要容器名称

项目使用 Docker Compose 管理多个服务，主要容器名称如下：
- `api-dev` - FastAPI 后端服务
- `web-dev` - Vue.js 前端开发服务器
- `graph` - Neo4j 图数据库
- `milvus` - 向量数据库，包含 etcd 和 MinIO 依赖
- `mineru` - 可选的 MinerU OCR 服务（需要 GPU）
- `paddlex` - 可选的 PaddleX OCR 服务（需要 GPU）

## 项目调试

此项目是使用 Docker 进行部署的，使用 `docker compose up -d` 命令进行构建和启动。因此当进行任何修改的时候，不要尝试启动这个项目，应该先检查项目是否已经在后台启动（`docker ps`），具体的可以阅读 [docker-compose.yml](docker-compose.yml).

前端和后端都是配置了自动启动的，因此当修改完成后，会自动更新，可以使用 docker logs 查看日志。对于部分场景可以创建一个 test_router.py 在 [server/routers](server/routers) 中，然后通过 API 测试功能场景。对于前端的 UI 修改，则不用测试。

## 风格说明

UI风格要简洁，同时要保持一致性，颜色要尽量参考 [base.css](web/src/assets/css/base.css) 中的颜色。不要悬停位移，不要过度使用阴影以及渐变色。
