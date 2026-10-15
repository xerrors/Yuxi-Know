# 生产部署

本页说明如何用 Docker Compose 全新部署 Yuxi 并验证服务状态。重要数据上线前请先在备份环境演练恢复。

## 前置条件

- Docker Engine 28.0 或更高版本；
- Docker Compose v2.33.1 或更高版本；
- 能访问所需镜像和模型服务的网络；
- 使用本地 GPU OCR 时准备 NVIDIA Container Toolkit。

生产 Compose 默认不把 PostgreSQL、MinIO、Neo4j 和 Milvus 管理端口发布到公网。维护这些服务时，优先使用 `docker compose exec` 或受控的内网入口。

::: danger 公网部署必须先配置 TLS
生产 Compose 自带的 Web 容器只监听 HTTP 80 端口，不负责证书和 HTTPS。把服务交给公网或接收登录、OIDC、API Key 请求前，必须在前面配置 TLS 反向代理，并只把 HTTPS 地址提供给用户和外部系统。HTTP 仅适合本机或受控内网调试。
:::

## 1. 准备生产配置

复制模板并编辑 `.env.prod`：

```bash
cp .env.template .env.prod
```

至少填写：

```dotenv
POSTGRES_PASSWORD=<strong-postgres-password>
NEO4J_PASSWORD=<strong-neo4j-password>
MINIO_ACCESS_KEY=<strong-minio-access-key>
MINIO_SECRET_KEY=<strong-minio-secret-key>
JWT_SECRET_KEY=<random-value-at-least-32-characters>
API_KEY_DERIVATION_SECRET=<another-random-value-at-least-32-characters>
CUBE_API_URL=http://<private-node-address>:3000
CUBE_PROXY_NODE_IP=<private-node-address>
CUBE_NODE_USER_DATA_DIR=/absolute/yuxi/threads
CUBE_NODE_SKILL_PROJECTION_DIR=/absolute/yuxi/skill-projections
YUXI_INSTANCE_ID=<stable-instance-name>
```

三个安全密钥必须彼此不同、没有首尾空白，并在重建或升级时保留原值。可以用下面的命令生成随机值，再把结果安全地写入 `.env.prod`：

```bash
openssl rand -hex 32
```

模型 API Key 按实际使用的供应商填写。生产 Compose 所有必填项都通过变量校验，缺失时会拒绝启动。

后续命令必须显式使用 `--env-file .env.prod`。Compose 的 `env_file` 负责把变量注入容器，但不会替代 Compose 文件插值所需的 `--env-file`。

### 环境隔离与自定义配置文件

开发配置的容器环境文件默认为 `.env`，生产配置默认为 `.env.prod`。使用其他文件时，同时指定 `YUXI_ENV_FILE` 和 `--env-file`，让容器注入与 Compose 插值读取同一份配置：

```bash
YUXI_ENV_FILE=.env.staging docker compose --env-file .env.staging -f docker-compose.prod.yml config --quiet
YUXI_ENV_FILE=.env.staging docker compose --env-file .env.staging -f docker-compose.prod.yml up -d --build
```

同机并行部署时，在各自的环境文件中设置不同的 `COMPOSE_PROJECT_NAME` 和 `YUXI_STATE_DIR`；项目名隔离容器、镜像、Compose 网络和动态沙盒名称，数据目录隔离持久文件。默认数据目录仍是 `./docker/volumes`，同一目录只允许一套运行中的环境写入。已有部署更换项目名或从固定容器名切换前，先结束任务和沙盒会话，用旧配置执行 `docker compose down`（保留数据，不加 `-v`），再用新配置启动；复用数据时保持状态目录和密钥不变。

生产 Web 端口通过 `YUXI_FRONTEND_PORT` 设置，默认 80；API 默认发布到 `127.0.0.1:6050`，管理服务端口也只绑定回环地址。具体默认值由 `docker-compose.prod.yml` 的 `ports` 定义；多套生产环境还需分别设置端口，启用 `all` profile 时包括 `YUXI_MINERU_PORT` 和 `YUXI_PADDLEX_PORT`。开发环境的端口隔离示例见[并行工作树与隔离运行环境](../develop-guides/parallel-worktree-environments.md)。

MinIO 将同一宿主数据目录挂载到容器 `/data`，Neo4j 将日志目录挂载到 `/logs`；这两个容器内路径的调整不要求移动宿主文件。

## 2. 首次启动

新部署直接启动核心服务：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

需要本地 MinerU 或 PaddleX OCR 时，再启用 `all` profile：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml --profile all up -d --build
```

`schema-init` 为空库直接建立 business 版本 2 与 knowledge 版本 1 基线，包含当前表、索引、约束和 LangGraph checkpoint 表。当前版本直接结束，初始化成功后进程以退出码 0 结束，API 与 worker 才会启动。

## 3. 数据库与文件目录

新部署使用空 PostgreSQL 数据库和独立的 Yuxi 文件目录。已有当前版本数据库可以直接重启同版本服务。其他版本和包含未版本化 Yuxi 表的数据库会被明确拒绝，初始化器不执行历史升级、回填或自动清库。当前版本以全新部署为前提；需要保留的数据由部署者独立备份和处理，不通过手改版本标记绕过结构校验。

应用不写入身份操作日志，初始 Schema 不创建 `operation_logs` 表。

用户执行环境由专用 Linux/KVM 节点上的 Cube 提供。节点准备与 Workspace、Skills 共享目录要求见[沙盒配置与运维](./sandbox-operations.md)。

## 4. 验证部署

先看容器状态：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

生产 Web 入口默认是 `http://<host>/`。部署在反向代理后并配置 TLS 后，应使用 HTTPS。

```bash
curl --fail http://localhost/api/system/health
curl --fail http://localhost/api/system/ready
```

- `/api/system/health` 只表示 API 进程存活；
- `/api/system/ready` 表示启动完成、PostgreSQL/Redis 可用，并且兼容 worker 正在提供健康租约。

worker 的 Compose 健康检查通过 `python -m yuxi.services.worker_health` 轻量读取 `REDIS_URL` 中的 ARQ 心跳，不加载业务执行依赖。心跳缺失、过期、没有 TTL、TTL 超过约定上界或 Redis 连接失败时检查失败。该心跳表达共享队列的消费健康，多副本部署不能用它判断单个 worker 进程是否失活。

就绪接口返回 `ready` 后，再用浏览器完成登录和一次真实对话。健康或就绪状态不能证明知识库、模型、沙盒或外部服务的业务链路正确。

公开头像和智能体图片通过同源 `/minio/public/...` 只读代理访问。不要把 MinIO 的 9000 对象 API 或 9001 控制台暴露到公网；知识库等私有 bucket 不经过该代理。需要单独的静态资源域名时，设置 `MINIO_PUBLIC_URL`，并在域名侧保持同样的只读限制。

## 开发环境端口与入口

开发 Compose 发布到宿主机的端口如下；生产 Compose 默认只发布 Web 入口，其余服务通过 Compose 内网访问。

| 端口 | 服务 | 用途 |
| --- | --- | --- |
| 5173 | Web | 开发 Web 界面 |
| 5050 | API | API 和 Swagger 文档 |
| Cube 私网控制面/代理 | 专用 Linux/KVM 节点 | 由部署提供，仅 API/worker 访问 |
| 7474 / 7687 | Neo4j | HTTP 管理界面 / Bolt |
| 9000 / 9001 | MinIO | 对象 API / 管理控制台 |
| 19530 / 9091 | Milvus | gRPC / 健康检查 |
| 5432 | PostgreSQL | 本机数据库维护 |
| 6379 | Redis | 本机缓存和队列维护 |

`all` profile 下还有两个可选 OCR 服务：`mineru-api`（30001，`/file_parse` 接口）和 `paddlex`（8080，PP-Structure-V3）。etcd 只在 Compose 网络内供 Milvus 使用，没有发布到宿主机。

PostgreSQL、Redis、MinIO、Milvus 和 Neo4j 的端口只绑定 `127.0.0.1`，不要把它们暴露到公网；Web 与 API 发布到所有接口。各端口可用环境变量覆盖（`YUXI_FRONTEND_PORT`、`YUXI_API_PORT`、`YUXI_NEO4J_HTTP_PORT`、`YUXI_MINIO_API_PORT`、`YUXI_MILVUS_PORT`、`YUXI_POSTGRES_PORT`、`YUXI_REDIS_PORT`），完整映射以 [docker-compose.yml](https://github.com/xerrors/Yuxi/blob/main/docker-compose.yml) 为准。

常用入口：Web <http://localhost:5173>，API 文档 <http://localhost:5050/docs>，Neo4j <http://localhost:7474>。用户执行环境状态在“设置 → Agent 环境”查看；health 与 ready 接口的语义见上方「验证部署」。

## 跨域（CORS）

生产环境不会默认允许浏览器跨域请求：

```dotenv
YUXI_CORS_ORIGINS=https://frontend.example.com
```

多个来源用逗号分隔：

```dotenv
YUXI_CORS_ORIGINS=https://a.example.com,https://b.example.com
```

前端与 API 同源时留空即可。设置为 `*` 会关闭 credentials，浏览器不会携带登录态，因此不适合需要 JWT Cookie/凭证的前端。开发环境在 `YUXI_ENV=development` 且未设置该变量时，默认允许 `http://localhost:5173` 和 `http://127.0.0.1:5173`；生产环境不会采用这个默认值。修改后重启 API。

## 维护与故障排查

### 查看日志

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=200 api worker
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f api worker
```

### Redis 重建后恢复 worker

ARQ worker 不会在 Redis 容器重建后自动恢复连接。重建 Redis 后重启 worker：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d redis
docker compose --env-file .env.prod -f docker-compose.prod.yml restart worker
```

再次检查 `/api/system/ready`，确认 worker 健康租约恢复。

### 轮换历史默认凭据

更换 `.env.prod` 中的 PostgreSQL、Neo4j 或 MinIO 凭据，不会自动修改已经写入数据卷的服务凭据。请先使用对应服务的官方管理流程修改数据卷内的凭据，再更新 `.env.prod`，重新创建相关服务，并用旧凭据验证登录已被拒绝。不要把真实密码写进命令历史、日志或文档。

PostgreSQL 可以在数据库容器内使用交互式命令修改，避免新密码出现在 shell 历史和进程参数中：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  exec postgres psql -U postgres -d yuxi -c '\password postgres'
```

Neo4j 使用 `cypher-shell` 的当前用户密码修改流程；MinIO 使用 `mc admin` 或部署采用的密钥管理流程。完成轮换后，把新值写入 `.env.prod`，再重建依赖这些凭据的服务：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  up -d --force-recreate postgres graph minio api worker
```

最后分别用新凭据和旧凭据执行一次受控登录验证；API/worker 的 `API_KEY_DERIVATION_SECRET` 也必须保持为持久、独立且至少 32 个字符的值。

### 常用检查顺序

1. `docker compose ps`：确认 Schema 初始化成功、API 与 worker 在运行。
2. `docker compose logs`：从最先失败的服务开始看，不只看最后一条 API 错误。
3. `/api/system/ready`：确认接流量前置条件。
4. 真实登录、对话和文件操作：确认业务链路。
5. 知识库、OCR、Langfuse 等可选能力：单独检查其配置和外部服务。

### Milvus 3 全新部署

Milvus 3.0.2 与 PyMilvus 3.0.2 配套部署，知识库与图向量通过 `MILVUS_DB` 使用同一个数据库，默认 `yuxi`。Compose 使用 Woodpecker 的对象存储模式，MinIO 固定到支持条件写入的版本；`milvus-storage-init` 在 Milvus 启动前设置绑定目录的 UID/GID，初始化失败会阻止启动。

允许丢弃全部数据时，停掉当前 Compose project，在对应环境文件中把 `YUXI_STATE_DIR` 指向一个新的空目录，例如 `/srv/yuxi/state-milvus3`，然后重新构建并启动完整拓扑。开发使用 `docker-compose.yml`，生产使用本页的 `.env.prod` 与 `docker-compose.prod.yml`。新目录同时重置 PostgreSQL、对象存储、图谱、工作区及向量索引；需要重新初始化管理员、模型供应商和知识库，再上传、解析、索引文档。不要把旧的 PostgreSQL 文件记录与空的 Milvus 索引混用。

检查 `milvus-storage-init` 和 `schema-init` 已成功退出，并确认 `/api/system/ready` 返回就绪。再按[知识库教程](../intro/knowledge-base.md#3-验证检索)确认文件为 `indexed`，三个检索模式返回目标文件的片段。集合的模型或 schema 不匹配时会显式报错，查询不会自动删除集合；需要修正部署状态并重新建立知识库。

## 第三方组件和许可证

Yuxi 本体使用 MIT License。Compose 依赖以独立进程运行，Yuxi 通过公开协议访问它们；第三方组件的许可证不会因为使用 Compose 就变成 MIT。

当前 Compose 引用的主要组件如下。表中的版本是镜像 tag；只有明确写死的 tag 才能提供对应的版本预期，`postgres:16`、`mineru-vllm:latest` 和 `paddlex:latest` 仍可能随重新拉取而变化：

| 组件 | 镜像引用 | 许可证 |
| --- | --- | --- |
| Neo4j Community | `neo4j:5.26.29` | GPL-3.0-only |
| MinIO | 本地构建：`<项目名>-minio:RELEASE.2024-12-18T13-15-44Z`（`docker/minio/Dockerfile`；项目名取 `COMPOSE_PROJECT_NAME`，默认 `yuxi`） | AGPL-3.0 |
| Milvus | `milvusdb/milvus:v3.0.2` | Apache-2.0 |
| etcd | `quay.io/coreos/etcd:v3.5.25` | Apache-2.0 |
| PostgreSQL | `postgres:16` | PostgreSQL License |
| Redis | `redis:7.4.10-alpine` | RSALv2 / SSPLv1（均非 OSI 许可证） |
| MinerU / PaddleX（可选） | `mineru-vllm:latest` / `paddlex:latest` | 以各自 Dockerfile 和上游声明为准 |

MinIO 的镜像由本仓库构建：MinIO 在 Docker Hub 与 quay.io 上的镜像已不再公开分发（同一 registry 上其他镜像仍可匿名拉取），`dl.min.io` 返回 410。Compose 按 `docker/minio/Dockerfile` 构建该镜像，构建时从官方 GitHub Release 下载固定版本的二进制并校验 sha256；它运行与下架前镜像逐字节相同的 MinIO 二进制，基础镜像与镜像内附带文件则不同（不再包含 `mc`、`minisig` 与 `*_FILE` 变量默认值）。

这张表只覆盖 Compose 的主要镜像本体，不是完整的软件物料清单，也不承诺 `latest` 镜像的内容固定。镜像还可能包含各自的基础系统和传递依赖，离线交付前要按实际 digest 核对许可证、版权声明和对应源码。

如果通过 `docker/save_docker_images.sh` 或其他方式向第三方再分发包含 GPL/AGPL 软件的镜像，需要保留许可证文本和上游声明，并按对应许可证第 6 节提供匹配的完整对应源码或有效的书面源码要约。通过网络提供服务、修改 AGPL 组件或把组件集成进同一程序时，义务可能不同，不能只附一个上游链接就视为完成。

商业部署可以评估 Neo4j Enterprise、MinIO 商业订阅或其他兼容替代品，但这会带来新的协议、迁移和运维条件。

需要 Neo4j 企业版功能或商业支持时，可以将图谱服务镜像替换为 `neo4j:5.26-enterprise`，并设置：

```dotenv
NEO4J_ACCEPT_LICENSE_AGREEMENT=yes
```

同时按 Neo4j 官方订阅协议确认许可范围；替换镜像不会自动迁移或改变现有数据卷。以上是工程侧边界，不构成法律意见；再分发、修改组件或对外托管前请让法务按具体版本和交付方式确认。
