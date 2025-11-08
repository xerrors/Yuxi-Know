
# 项目目录结构 (Project Overview)

Yuxi-Know 是一个基于知识图谱和向量数据库的智能知识库系统。它通过 FastAPI 提供后端 API，使用 Vue.js 构建前端界面，并利用 Docker Compose 进行整体服务的编排和管理。

文档中心在 `docs` 文件夹下面。

## 开发与调试工作流 (Development & Debugging Workflow)

本项目完全通过 Docker Compose 进行管理。所有开发和调试都应在运行的容器环境中进行。使用 `docker compose up -d` 命令进行构建和启动。

核心原则: 由于 api-dev 和 web-dev 服务均配置了热重载 (hot-reloading)，本地修改代码后无需重启容器，服务会自动更新。应该先检查项目是否已经在后台启动（`docker ps`），查看日志（`docker logs api-dev --tail 100`）具体的可以阅读 [docker-compose.yml](docker-compose.yml).

前端开发规范：

- API 接口规范：所有的 API 接口都应该定义在 web/src/apis 下面，并继承自 apiGet/apiPost/apiRequest
- Icon 应该从 @ant-design/icons-vue 或者 lucide-vue-next
- Vue 中的样式使用 less，并尽量使用[base.css](web/src/assets/css/base.css) 中的颜色。
- UI风格要简洁，同时要保持一致性，颜色要尽量参考 不要悬停位移，不要过度使用阴影以及渐变色。


后端开发规范：

- 项目使用 uv 来管理依赖，所以需要使用 uv run 来调试。
- Python 代码要符合 Python 的规范，符合 pythonic 风格，尽量使用较新的语法，避免使用旧版本的语法（版本兼容到 3.12+），使用 make lint 检查 lint。使用 make format 来格式化代码。

其他：

- 如果需要新建说明文档（仅开发者可见，非必要不创建），则保存在 `docs/vibe` 文件夹下面
- 测试脚本可以放在 test 文件夹下面，可以从 docker 中启动测试（不要使用本地 Python 环境）
- 代码更新后要检查文档部分是否有需要更新的地方，文档的目录定义在 `docs/.vitepress/config.mts` 中
