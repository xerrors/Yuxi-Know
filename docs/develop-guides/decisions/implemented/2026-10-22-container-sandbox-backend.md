# Container 沙盒后端

状态：implemented
类型：feature
Owner：backend/yuxi/modules/agents/runtime/sandbox/provider.py

## 问题

现有 Agent 执行环境只有每用户持久的 Cube VM。没有 KVM 节点时，工作区文件工具仍可用，但 `execute`、依赖 shell 的 Skill 和用户环境验证全部不可用。需要一种轻量部署：不改变现有 Agent 工具面，用独立 runner 为每个 Run 提供用完即弃的容器执行环境；同时保留 Cube 作为默认强隔离后端。

## 决策

### 实现方案

`SANDBOX_BACKEND` 只接受 `cube` 与 `container`。`app-init` 和 provider 工厂校验业务进程连接配置，runner 校验镜像、挂载和资源；cube 缺节点变量、container 缺 token/镜像或生产镜像未固定 digest 都会在接流量前失败。provider 工厂在启动时选择 `CubeSandboxProvider` 或 `ContainerSandboxProvider`；两种后端复用 `UserSandboxBackend`、`execute` 工具、文件路由、审批、审计、结果驱逐与 Run lease。

Cube 的 Compose 变量从 `${...:?}` 改为默认空值，以便同一份 Compose 选择两种后端；缺失节点变量仍由 `app-init` 的 `validate_sandbox_configuration()` 在 api/worker 启动前拒绝，不会静默使用 localhost。

Container 模式由 `yuxi/sandbox_runner` 提供独立 HTTP 服务，只有它挂载 Docker/Podman socket 和宿主数据目录。API/worker 通过 Bearer token 调用 `POST /v1/runs/{run_id}/exec`、`POST .../exec/{command_id}/cancel`、`DELETE /v1/runs/{run_id}`、`GET /v1/runs` 和 `GET /v1/stats`。容器只由 exec 内部懒创建。`GET /healthz` 公开只读就绪状态；其余接口未认证返回 401。

容器按 Run 懒创建，确定性名称与 label 绑定部署 scope、`uid`、`run_id`、attempt owner 和 Workdir。Run 内复用，终态、取消、失败、lease 失效和 retry cleanup 删除；所有终态（包括 yielded）由统一的 `complete_run_runtime_cleanup` 保持持久清理责任，worker `maintain` 按 label 与 `agent_runs` 对账，最大存活时间只由 runner 兜底。清理及配置责任由[运行环境收敛决策](2026-10-23-sandbox-runtime-convergence.md)拥有。创建和删除幂等；标签不匹配返回 409。部署 scope、命令身份保留与对账快照的取舍见[清理边界决策](2026-10-23-container-sandbox-cleanup-boundaries.md)。

### 挂载与镜像

容器只挂载当前 Project Workdir（读写，目标保持 `/home/user/workspace/<workdir>`）和已存在的用户 Skill 投影（`/home/user/skills`，只读）。runner 从自身 bind mount 反查 Docker daemon 视角的宿主路径；API/worker 不传宿主路径。Workdir 逐段以 `O_NOFOLLOW` 校验，拒绝越界、符号链接和非目录。`/home/user` 与 `/tmp` 使用 tmpfs，根文件系统只读。

镜像只由 runner 配置决定；runner 在启动时解析并固定镜像 ID，配置 digest 时校验 `RepoDigests`/镜像 ID。Compose 的 `sandbox-image` 服务在部署时构建或预拉取镜像，runner 不隐式拉取。镜像基于 `python:3.13-slim`，包含 bash、python3、pip、uv、git、curl、jq、ripgrep、unzip 与常用 Python 库。

### 隔离、资源与审计

默认 `--network none`、非 root、`cap-drop ALL`、`no-new-privileges`、只读根、独立 PID/IPC/network namespace，不共享宿主 PID 或 Docker socket。CPU、内存、pids、Home/tmp tmpfs 和输出字节均有上限；runner 施加部署内全局容器数与单 Run 并发 exec 上限，超限返回 429。命令包装父进程保留身份，超时和取消固定所属进程组后终止并确认，不依赖子命令保留环境；runner 对每条命令设置绝对墙钟期限，未启动的取消不会被误认为成功；容器删除是最终兜底。长命令在专用线程池执行，健康检查和取消不会被并发 exec 饿死。

日志只记录 uid、run_id、container_id、镜像 ID、command_id、退出码、耗时和截断，不记录命令正文或环境变量值。普通 Docker 共享宿主内核，本模式只定位为单租户或可信代码的轻量执行层，不宣称多租户强隔离。

### 明确不做

不实现 none 模式、多镜像或模型选择镜像、模型自建沙盒工具、持久 Home、跨 Run 软件安装、VM 重建/磁盘 UI 的完整 parity、多租户强隔离承诺、gVisor/Kata/Firecracker，也不允许回退到宿主执行。

## 替代方案

- 继续只支持 Cube：无 KVM 节点时 `execute` 永久不可用，不满足轻量部署目标。
- 在 API/worker 内直接创建容器：需要把 Docker socket 暴露给业务进程，扩大信任边界，不采用。
- 复用 LangChain `ShellToolMiddleware`：会新增第二个 shell 工具、每 Run 固定启动容器，且不支持现有工具审批与取消语义，不采用。
- 为每个用户保留一个持久容器：与 Cube 语义相近但隔离更弱，生命周期和跨用户共享复杂度更高，不采用。
- 引入 gVisor/Kata：需要额外节点运行时与部署承诺，超出本任务范围。

## 后果

- 无 KVM 节点也能提供 `execute` 和 shell 依赖 Skill，但 Home 与容器内软件随 Run 消失；需要持久安装时使用 Workspace 或 Cube。
- 默认网络隔离使联网 Skill 失败；`SANDBOX_CONTAINER_NETWORK=bridge` 是显式的安全降级。
- 每个 Run 新建容器增加启动开销；runner 是执行链的单点，必须有健康检查与重启策略。
- 设置页在 container 模式隐藏重建和磁盘操作，状态显示任务级临时环境。
- 环境变量验证、远程 Skill CLI 安装等没有活动 Run 的操作显式失败。
- 单 runner 实例；多副本、跨节点调度和强隔离运行时需要独立设计。

## 验证

- `SANDBOX_CONTAINER_TEST=1 pytest test/integration/sandbox/test_container_sandbox.py -q`（在可访问 Docker socket、Docker CLI 和宿主路径的机器上运行）：10 passed。真实 Docker 覆盖 create/exec/remove 幂等、Workdir 双向字节与 SHA-256、其他用户/`.env`/Docker socket/云元数据不可达、只读根、非 root、cap-drop、network none、pids/memory/CPU cgroup 限制、OOM、fork、输出截断、超时/取消后的进程与容器清理，以及同一命令与普通 Docker 的输出内容/退出码对比；还覆盖 cancel 在 exec 创建延迟期间不产生副作用、持续输出命令的墙钟超时。
- `pytest test/unit/sandbox -q`：107 passed，包含 provider 归属/lease/status/maintain 和 runner 挂载/资源/幂等/cwd 校验。
- `pytest test/unit/config/test_docker_compose_service_boundaries.py test/unit/config/test_init_noninteractive.py -q`：75 passed，证明 API/worker 不挂载 socket、runner profile 与生产初始化分流。
- `pytest test/unit -m "not slow" -q`：3129 passed。
- 前端 `pnpm run test:unit`：780 passed，包含 container 模式隐藏重建/磁盘和任务级文案；`pnpm run lint:check` 与 docs build 通过。
- 手工 `docker inspect`：`ReadonlyRootfs=true`、`CapDrop=["ALL"]`、`SecurityOpt=["no-new-privileges"]`、`NetworkMode=none`、`PidsLimit=256`、`Memory=1GiB`、`NanoCpus=1e9`、`Init=true`，mounts 只有 Workdir 与只读 Skills。
- 配置责任的当前验证见[运行环境收敛决策](2026-10-23-sandbox-runtime-convergence.md)；业务侧连接校验与 runner 侧镜像校验分别拥有失败边界。
- 容器化 runner 的 stdin：runner 只挂载 `/sandbox-data`，本地 stdin 写入 `/sandbox-data/...`，Docker 使用反查的宿主 Source 挂载 Workdir；命令回读到完整输入，临时文件被删除。
- 容器化 runner：用 `yuxi-api:container-test` 以 `user=0:0` 挂载真实 Docker socket 与 `/sandbox-data`，`/healthz` 成功反查宿主路径；执行命令写入的宿主文件可回读，inspect 显示正确 Workdir/只读 Skills 挂载。
- runner 重启：杀掉并重启 runner 后，原容器仍被 `GET /v1/runs` 发现，后续 `exec` 成功，`DELETE` 删除容器。
- 40 个并发 exec 期间 `/healthz` 在 18 ms 内返回；`/v1/health` 缺 token 返回 401，错误 token 返回认证失败。
- 真实 PostgreSQL 对账：对不存在的 Run 创建容器后执行 `ContainerSandboxProvider.maintain`，容器被删除；`SandboxRepository.run_owner` 回读真实已完成 Run 的 uid/status。
- 完整 API/worker + PostgreSQL E2E：在隔离的 container Compose 栈（独立项目名、端口、`/tmp` 状态目录）上初始化真实管理员，注册确定性 OpenAI replay，通过 Session→Input→Run→Turn 让真实 worker 调用 `execute`。两个连续 Run 的 Turn/Run 均为 completed，`runtime_cleanup_pending=false`；Docker 观察到两个不同的 `yuxi-sandbox-<run_id>` 容器，均为 `1000:1000`、只读根、network none、cap-drop ALL、no-new-privileges，只挂载各自 Workdir 和只读 Skills；终态后两个容器都被删除。宿主文件内容为 `container-e2e-ok`、SHA-256 `aa2cac8bf7a9519b9b3f9189584d5589497a4867bb9c1e50a2968933d7ff70b2`；公开 Viewer API 回读同一内容。`sandbox_commands=0`、`user_sandboxes=0`；`/api/user/sandbox` 返回 `backend=container,state=not_created,busy=false`，VM 统计为 0/0。
- 可重复的 tracked E2E：`CONTAINER_E2E=1 TEST_BASE_URL=... E2E_USERNAME=... E2E_PASSWORD=... CONTAINER_E2E_REPLAY_URL_TEMPLATE='http://host.docker.internal:{port}/v1' pytest test/e2e/test_container_agent_execution_e2e.py -q`：1 passed（真实 API、worker、runner、PostgreSQL 和 Viewer 回读）。
