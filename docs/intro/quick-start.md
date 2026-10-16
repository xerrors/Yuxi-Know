# 快速开始

这份教程带你在本机启动一套 Yuxi，并完成第一次登录。走完流程后，你会有一个可以打开的 Web 界面和 API 文档；模型配置、知识库和生产部署分别在后续页面说明。

## 你需要准备什么

- 已安装 [Docker Engine](https://docs.docker.com/get-docker/) 和 Docker Compose v2。
- 已按[沙盒配置与运维](../advanced/sandbox-operations.md#原生执行节点)准备专用 Linux/KVM Cube 执行节点、用户模板及与应用共享的 Workspace、Skills 目录。macOS 和 Windows 应用环境也需要可访问的 Linux/KVM 节点。
- 一个可用的大模型 API。下面的初始化脚本以 SiliconFlow 为例；也可以先复制 `.env.template`，改用其他受支持的供应商。
- 能够访问 Docker 镜像仓库和模型服务的网络。默认拓扑会启动知识库和图谱依赖，但 OCR 服务只在需要时通过 `all` profile 启动。

默认开发拓扑不要求 GPU。MinerU 和 PP-Structure-V3 等本地 OCR 服务需要 GPU，配置方法见[文档处理与 OCR](../advanced/document-processing.md)。

## 1. 获取代码

当前候选源码版本为 `v0.8.0.beta1`，从 fork 的 `develop/0-8-0` 分支获取，tag 在验收后创建。本版本仅支持全新部署，请使用独立数据目录；旧数据库与索引不会自动升级。变化与限制见[0.8.0 更新说明](../develop-guides/releases/0.8.0.md)，数据要求见[生产部署](../advanced/deployment.md)。

```bash
git clone --branch develop/0-8-0 --depth 1 https://github.com/Yuchuan925/Yuxi.git
cd Yuxi
```

如果你要参与开发，可以改为克隆 `main`；开发分支的行为可能先于发布版本变化。

## 2. 初始化环境

Linux/macOS：

```bash
./scripts/init.sh
```

Windows PowerShell：

```powershell
.\scripts\init.ps1
```

脚本会交互式读取或生成以下内容，并写入项目根目录的 `.env`：

- 必填的 `SILICONFLOW_API_KEY`。
- 可选的网页搜索供应商和对应密钥（豆包或 Tavily）。
- `JWT_SECRET_KEY` 和 `API_KEY_DERIVATION_SECRET` 两个相互独立的随机密钥，每个至少 32 个字符。
- `YUXI_INSTANCE_ID`，用于标识这套部署。

脚本还会拉取开发环境需要的基础镜像。它不会把密钥打印到终端，Linux/macOS 下会把 `.env` 权限设为 `600`。已有 `.env` 时，脚本只补齐缺失项；升级时请保留原有密钥，尤其是 `JWT_SECRET_KEY` 和 `API_KEY_DERIVATION_SECRET`。

不使用初始化脚本时，可以手动开始：

```bash
cp .env.template .env
```

然后在 `.env` 中填入模型 API Key 和两个独立的安全密钥。开发 Compose 会为部分基础服务提供默认值；生产部署不要沿用这些默认值。

无论使用脚本还是手动初始化，都需要按[执行节点配置](../advanced/sandbox-operations.md#原生执行节点)在 `.env` 中填写 `CUBE_API_URL`、`CUBE_PROXY_NODE_IP`、`CUBE_NODE_USER_DATA_DIR` 和 `CUBE_NODE_SKILL_PROJECTION_DIR`；控制面启用认证时还需填写节点提供的 `CUBE_API_KEY`。初始化脚本不部署 Cube 节点，也不生成其控制凭据。启动前运行 `docker compose config --quiet`，确认必填配置齐全。

## 3. 启动服务

```bash
docker compose up --build -d
```

第一次启动需要下载镜像并构建应用，耗时取决于网络和机器性能。用下面的命令查看状态和 API 日志：

```bash
docker compose ps
docker compose logs -f api
```

等 API 的健康检查完成后，可直接检查就绪接口：

```bash
curl --fail http://localhost:5050/api/system/ready
```

返回 JSON 且 `status` 为 `ready`，表示 API、PostgreSQL、Redis 和兼容 worker 已达到接流量条件。它只证明启动条件满足，不代替一次真实登录或对话验证。

## 4. 打开 Yuxi

| 入口 | 地址 |
| --- | --- |
| Web 界面 | <http://localhost:5173> |
| API 文档 | <http://localhost:5050/docs> |
| API 存活检查 | <http://localhost:5050/api/system/health> |
| API 就绪检查 | <http://localhost:5050/api/system/ready> |

首次打开 Web 界面时，按页面提示初始化超级管理员账号。登录成功后，可以从“智能体”页面配置模型，从“知识库”页面创建文档知识库。

## 常见问题

### 容器没有变成 healthy

先确认 Schema 初始化进程、API 与 worker 的日志：

```bash
docker compose ps
docker compose logs --tail=100 schema-init api worker
```

`schema-init` 是一次性 Schema 初始化服务，成功后会退出，这是正常状态。API 和 worker 必须在它成功后才能启动。

### 镜像拉取失败

先确认 Docker 能访问镜像仓库。也可以单独拉取某个镜像：

```bash
bash scripts/pull_image.sh python:3.13-slim
```

离线环境可以在有网络的机器上导出镜像，再将压缩包复制到目标机器并执行 `docker load`。仓库提供的导出脚本是 `docker/save_docker_images.sh`；导出前请核对脚本实际包含的镜像列表。

### 需要代理才能构建

在启动 Docker Compose 前设置 Docker daemon 或构建环境所需的代理。示例：

```bash
export HTTP_PROXY=http://<proxy-host>:<port>
export HTTPS_PROXY=http://<proxy-host>:<port>
docker compose up --build -d
```

代理地址只使用你自己的环境值，不要把账号或密码提交到 `.env`、文档或日志中。

### 知识库依赖启动失败

默认拓扑需要 Milvus、etcd、MinIO 和 Neo4j。先查看对应服务的日志和健康状态：

```bash
docker compose ps milvus etcd minio graph
docker compose logs --tail=100 milvus etcd minio graph
```

这些服务是默认拓扑的一部分；启动脚本正常退出不等于依赖健康，以 `docker compose ps` 的状态和就绪接口为准。

## 下一步

- [模型配置](./model-config.md)：接入聊天、嵌入和重排模型。
- [知识库与知识图谱](./knowledge-base.md)：上传文档并验证检索。
- [命令行工具](./cli.md)：用 npm CLI 连接实例、进行终端对话和查询知识库。
- [生产部署](../advanced/deployment.md)：配置生产环境和验证部署。
- [机制详解](../mechanisms/index.md)：理解运行、文件和存储边界。
