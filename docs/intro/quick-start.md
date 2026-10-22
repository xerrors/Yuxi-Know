# 快速开始

本教程完成一次可用的 Yuxi 部署：在一台应用主机上启动 Compose 服务，并连接一台已经运行 Cube 的 Linux/KVM 执行节点。Cube 不由 Yuxi 启动；API 和 worker 启动时会检查 Cube 控制面、用户模板和数据代理，检查失败则服务不会进入就绪状态。

## 先确认两台主机的角色

| 角色 | 运行内容 | 要求 |
| --- | --- | --- |
| 应用主机 | `api`、`worker`、`frontend`、PostgreSQL、Redis、MinIO、Milvus、Neo4j 等 Compose 服务 | Docker Engine 和 Compose v2；能通过私网访问执行节点的控制面和代理端口 |
| 执行节点 | Cube v0.7.3 和用户 VM | x86_64 Linux、`/dev/kvm`、管理员权限、Docker（构建用户模板）；与应用主机共享 Workspace 与 Skills 目录 |

两台角色可以在不同机器上，也可以在同一台 Linux 机器上使用嵌套开发节点。两种方式都必须先让 Cube 运行，再启动 Yuxi。如果同一台 Linux 机器既运行应用又提供 `/dev/kvm`，可以直接在这台机器上按方案 A 安装 Cube；方案 B 用于需要把开发节点放进独立容器或虚拟机的场景。

## 1. 启动 Cube 执行节点

### 方案 A：独立 Linux/KVM 节点（推荐）

在专用节点上执行：

```bash
test -e /dev/kvm && echo "KVM available"

git clone --branch develop/0-8-0 --depth 1 https://github.com/xerrors/Yuxi.git
cd Yuxi

sudo bash docker/cube/setup-node.sh
sudo cp docker/cube/Dockerfile.user docker/cube/build-template.sh /opt/yuxi-cube/
sudo bash /opt/yuxi-cube/build-template.sh

curl --fail http://127.0.0.1:3000/health
```

`setup-node.sh` 安装 Cube v0.7.3 并启动控制面；`build-template.sh` 构建 `yuxi-user` 用户模板，默认资源为 `--cpu 1000 --memory 1024`。脚本只用于专用执行节点，不要运行在应用容器或用户 VM 中。Cube 的安装依赖、平台要求和其他安装方式以 [CubeSandbox 官方仓库](https://github.com/TencentCloud/CubeSandbox) 为准；本仓库固定 v0.7.3，并提供上述封装脚本。

执行节点需要把应用主机的 `YUXI_STATE_DIR/yuxi/threads` 和 `YUXI_STATE_DIR/yuxi/skill-projections` 通过 NFS、bind mount 或其他共享文件系统挂到 `/data/shared/yuxi/threads` 和 `/data/shared/yuxi/skill-projections`。只填写环境变量不会创建共享；应用和节点必须看到同一份文件。共享目录的创建与验证见 3.1。

Cube 默认只允许 `/data/shared/` 下的宿主机挂载；使用其他目录时按[沙盒配置与运维](../advanced/sandbox-operations.md#原生执行节点)配置允许前缀。私网放行节点的控制面端口 `3000` 和数据代理端口（默认 `80`），只对应用主机开放。

### 方案 B：当前 Linux 机器的嵌套开发节点

只有一台 Linux 机器时，可以在本机运行嵌套 Cube。先确认本机具备 KVM：

```bash
test -e /dev/kvm && echo "KVM available"
grep -Eoc '(vmx|svm)' /proc/cpuinfo
```

`grep` 结果为 0 表示 CPU 未暴露虚拟化标志。如果 `/dev/kvm` 不存在，或者当前 Linux 本身是虚拟机且宿主机没有开启嵌套虚拟化，本机不能作为 Cube 节点。Docker Desktop 默认不能提供这个节点。此时改用方案 A 的独立 Linux/KVM 主机，或选择支持嵌套虚拟化的 Linux 云主机/裸金属实例。

嵌套模式的 `node.env`、Compose、Guest 内初始化和端口配置见[当前机器的嵌套开发节点](../advanced/sandbox-operations.md#当前机器的嵌套开发节点)。即使在同一台机器上，Cube 仍是独立的 Compose 项目，不由 Yuxi 根 Compose 启动。

## 2. 获取代码（应用主机）

本教程使用 `develop/0-8-0` 分支。0.8 仅支持全新部署，请使用独立数据目录；旧数据库与索引不会自动升级。变化与限制见[0.8.0 更新说明](../develop-guides/releases/0.8.0.md)，数据要求见[生产部署](../advanced/deployment.md)。

```bash
git clone --branch develop/0-8-0 --depth 1 https://github.com/xerrors/Yuxi.git
cd Yuxi
```

## 3. 初始化应用配置

### 3.1 确认共享目录

应用和 Cube 节点必须看到同一份 Workspace 与 Skills 文件。默认 `YUXI_STATE_DIR=./docker/volumes`；如果使用其他目录，替换下面的路径。

```bash
mkdir -p ./docker/volumes/yuxi/threads ./docker/volumes/yuxi/skill-projections
touch ./docker/volumes/yuxi/threads/.mount-check
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force docker/volumes/yuxi/threads, docker/volumes/yuxi/skill-projections | Out-Null
New-Item -ItemType File -Force docker/volumes/yuxi/threads/.mount-check | Out-Null
```

在执行节点确认：

```bash
ls /data/shared/yuxi/threads/.mount-check
```

文件不存在时先修正共享挂载；只填写 `.env` 不会创建共享。

### 3.2 生成 `.env` 并写入 Cube 配置

方案 B 的嵌套节点使用 Docker gateway 的控制端口 13001 和代理端口 18081，按[嵌套开发节点](../advanced/sandbox-operations.md#当前机器的嵌套开发节点)填写，不要套用下面的 3000/80。

Linux/macOS 先把 Cube 连接值导出为环境变量，再运行初始化脚本。脚本会把它们写入 `.env`，并在拉取和构建阶段用于 Compose 插值：

```bash
export CUBE_API_URL='http://<node-private-ip>:3000'
export CUBE_API_KEY=''  # 未启用控制面认证时留空
export CUBE_PROXY_NODE_IP='<node-private-ip>'
export CUBE_PROXY_PORT_HTTP=80
export CUBE_TEMPLATE_ID=yuxi-user
export CUBE_NODE_USER_DATA_DIR=/data/shared/yuxi/threads
export CUBE_NODE_SKILL_PROJECTION_DIR=/data/shared/yuxi/skill-projections

./scripts/init.sh
```

Windows PowerShell 先复制模板并填写 `.env`，再运行初始化脚本；`init.ps1` 不会把进程环境里的 `CUBE_*` 写入 `.env`：

```powershell
Copy-Item .env.template .env
# 编辑 .env，填写模型 Key、两个安全密钥和下面的 Cube 配置
.\scripts\init.ps1
```

也可以在任意平台复制 `.env.template` 为 `.env`，手动填写后跳过初始化脚本，直接执行下一步的 `docker compose up --build -d`。

需要写入 `.env` 的 Cube 配置：

```dotenv
CUBE_API_URL=http://<node-private-ip>:3000
# 未启用控制面认证时留空
CUBE_API_KEY=
CUBE_PROXY_NODE_IP=<node-private-ip>
CUBE_PROXY_PORT_HTTP=80
CUBE_TEMPLATE_ID=yuxi-user
CUBE_NODE_USER_DATA_DIR=/data/shared/yuxi/threads
CUBE_NODE_SKILL_PROJECTION_DIR=/data/shared/yuxi/skill-projections
```

初始化脚本还会生成以下内容：

- 必填的 `SILICONFLOW_API_KEY`；其他供应商在启动后于「智能体 → 模型供应商」接入。
- `JWT_SECRET_KEY` 和 `API_KEY_DERIVATION_SECRET` 两个相互独立的随机密钥，每个至少 32 个字符。
- `YUXI_INSTANCE_ID`，用于标识这套部署。

脚本还会拉取基础镜像并构建 MinIO 与 `storage-init`。镜像加速站失败时，Linux/macOS 脚本会提示并尝试原仓库；两处都失败时退出，可在网络恢复后重新运行。它不会把密钥打印到终端，Linux/macOS 下会把环境文件权限设为 `600`。已有配置中的安全密钥在未显式覆盖时保留。

最后在应用主机验证节点可达并检查 Compose 配置：

```bash
curl --fail http://<node-private-ip>:3000/health
docker compose config --quiet
```

## 4. 启动 Yuxi

```bash
docker compose up --build -d
```

这条命令只启动应用主机上的 Compose 服务，不会启动 Cube。第一次启动需要下载镜像并构建应用，耗时取决于网络和机器性能。用下面的命令查看状态和 API 日志：

```bash
docker compose ps
docker compose logs -f api
```

等 API 的健康检查完成后，检查就绪接口：

```bash
curl --fail http://localhost:5050/api/system/ready
```

返回 JSON 且 `status` 为 `ready`，表示 API、PostgreSQL、Redis 和兼容 worker 已达到接流量条件。它不代替一次真实登录或对话验证，也不证明用户 VM 已经创建成功。

如果 API 或 worker 反复重启，先查看 `sandbox_provider` 启动组件：Cube 不可达、`CUBE_API_KEY` 错误、模板别名不存在或代理端口不可达都会让启动失败。节点侧的健康检查和模板构建结果见步骤 1。

## 5. 打开 Yuxi

| 入口 | 地址 |
| --- | --- |
| Web 界面 | <http://localhost:5173> |
| API 文档 | <http://localhost:5050/docs> |
| API 存活检查 | <http://localhost:5050/api/system/health> |
| API 就绪检查 | <http://localhost:5050/api/system/ready> |

首次打开 Web 界面时，按页面提示初始化超级管理员账号。登录成功后，在「智能体 → 模型供应商」配置模型，再创建对话并发送测试消息。

第一次真正执行 Agent 时才会创建该用户的 Cube VM，启动应用本身不会预创建 VM。首次执行可能比后续请求慢；VM 空闲后按 `SANDBOX_IDLE_SECONDS`（默认 300 秒）休眠，状态在「设置 → Agent 环境」查看。收到该轮的最终回答后，再按[知识库入门](./knowledge-base.md)添加文档。

## 常见问题

### API 或 worker 启动失败，日志出现 `sandbox_provider`

按顺序检查：

1. 在应用主机执行 `curl --fail http://<node-private-ip>:3000/health`；失败时检查节点是否运行、私网路由和防火墙。
2. 确认 `CUBE_API_URL` 使用节点的控制面地址，`CUBE_PROXY_NODE_IP` 和 `CUBE_PROXY_PORT_HTTP` 指向数据代理。
3. 确认模板别名与 `CUBE_TEMPLATE_ID` 一致，默认是 `yuxi-user`；模板构建失败时重新执行步骤 1 的 `build-template.sh`。
4. 确认两个共享目录在节点上存在且与应用主机看到同一份文件。

### 本机没有 `/dev/kvm` 或无法开启嵌套虚拟化

本机不能运行 Cube。使用独立的 Linux/KVM 主机作为执行节点；云主机需要选择支持嵌套虚拟化的实例类型。macOS 和 Windows 的 Docker Desktop 默认不能替代执行节点。CubeSandbox 的平台要求和安装方式见[官方仓库](https://github.com/TencentCloud/CubeSandbox)。

### 容器没有变成 healthy

先确认 Schema 初始化进程、API 与 worker 的日志：

```bash
docker compose ps
docker compose logs --tail=100 app-init api worker
```

`storage-init` 准备挂载根权限；`app-init` 创建数据库基线并同步系统配置、内置 Agent、供应商、MCP 和 Skills。两个一次性服务成功后退出，这是正常状态。API 和 worker 等待 `app-init` 成功后启动。修改内置定义或升级镜像时，按[共享内容更新](../advanced/deployment.md#共享内容更新与失败重试)重新执行初始化。

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
