# Agent 自主创建 Sandbox 与 exec 工具模式调研

本文回答三个问题：现有产品如何提供“创建沙盒、执行 shell、挂载工作区、切换镜像”；这些实现分别把生命周期和隔离边界放在哪里；Yuxi 在已有 DeepAgents `execute` 工具和 Cube 用户 VM 的前提下，应选择透明 Backend 还是显式 `sandbox.create/exec/destroy` 工具集。本文是源码与官方文档调研，不修改业务代码，也不把厂商文档中的能力当作 Yuxi 已实现或已验证的能力。

调研日期为 2026-10-22。Yuxi 本地基线为 `6d84db563268c7c7c3f5765c219ec5aae2ad24fd`。外部事实优先采用官方文档、官方源码仓库和规范；文末列出实际访问的 URL。厂商托管服务没有在 Yuxi 环境中开通或压测，自托管方案没有安装对比。

## 结论摘要

1. **最成熟的模式是“平台预置沙盒 + Agent 只拿到 exec/文件工具”。Agent 只接收 exec/文件工具，创建、镜像和挂载权限留在平台代码。E2B、Daytona、Modal、Cloudflare、Vercel 都在应用或平台代码中创建沙盒，然后把 `commands.run`/`exec`、文件 API 暴露给 Agent；OpenHands、Kubernetes agent-sandbox 和 microsandbox 也是平台或工具服务器拥有生命周期。DeepAgents 官方文档同样把 provider adapter 作为 `backend` 传入，由应用在 `create_deep_agent` 外创建和销毁沙盒。[DeepAgents Sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes)、[DeepAgents Backends](https://docs.langchain.com/oss/python/deepagents/backends)

2. **“模型自主 `sandbox_create/exec/destroy`”有先例，但主要出现在面向开发者的 MCP/工具服务器**。microsandbox 的 MCP server 直接提供 `sandbox_create`、`sandbox_exec`、`sandbox_shell`、`sandbox_fs_*`、`sandbox_remove`，并默认用 `MICROSANDBOX_MCP_HOST_PATHS` 限制可挂载的宿主路径；它面向本机/开发环境，是可显式启用的工具面；多租户 SaaS 默认不采用。[microsandbox MCP](https://github.com/superradcompany/microsandbox-mcp)

3. **隔离强度分成四档**：普通容器（Docker/Podman，共享宿主内核）→ gVisor（用户态应用内核，仍是进程模型）→ Kata Containers（每容器/每 Pod 轻量 VM）→ Firecracker/microsandbox 等 microVM（每沙盒独立 guest 内核）。托管厂商中，E2B 和 Vercel 明确使用 Firecracker microVM，Cloudflare 使用每实例 microVM，Modal 提供 gVisor 或 VM runtime，Daytona 的容器沙盒是命名空间隔离、VM 沙盒有独立内核。[E2B Runtime](https://github.com/e2b-dev/runtime)、[Vercel Sandbox](https://vercel.com/docs/sandbox)、[Cloudflare Sandboxes](https://developers.cloudflare.com/sandbox/)、[Modal Sandboxes](https://modal.com/docs/guide/sandboxes)、[Daytona Isolation](https://www.daytona.io/docs/en/isolation)

4. **Docker 容器不足以承载不可信多租户 Agent 代码**。Docker 官方文档明确说明：Docker daemon 默认需要 root，只有可信用户才应控制 daemon；bind mount 默认可写，容器可以修改宿主文件；把宿主 `/` 挂进容器即可让容器改宿主。gVisor 的威胁模型也说明其目的正是减少不可信代码直接触达宿主内核 API。Rootless Podman 能把容器 root 映射到非特权用户，但不改变“共享宿主内核”这一事实。[Docker Engine security](https://docs.docker.com/engine/security/)、[Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)、[Podman rootless](https://docs.podman.io/en/latest/markdown/podman.1.html)、[gVisor Security Model](https://gvisor.dev/docs/architecture_guide/security/)

5. **LangChain 1.3.17 自带的 `ShellToolMiddleware` + `DockerExecutionPolicy` 是“显式 shell 工具 + 容器”的第一方先例**：它按每次 agent run 启动一个 Docker 容器，默认 `--network none`、`--rm`，可选 `--read-only`、`--user`、`--cpus`/`--memory`，并把 workspace 绑定挂载进容器。但容器和镜像由代码中的 policy 决定，模型只调用 `shell`，没有 `create/destroy` 或镜像选择权；它也不实现 DeepAgents 的 `SandboxBackendProtocol`。[Shell tool middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in#shell-tool)、[DockerExecutionPolicy 源码](https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/middleware/_execution.py)

6. **对 Yuxi 的首选方案是实现一个 Docker/Podman 的 `SandboxBackendProtocol`（通常继承 `BaseSandbox`），让现有 `FilesystemMiddleware` 的 `execute` 透明工作；不新增 `sandbox.*` 工具**。这与 DeepAgents 的 provider adapter 模式一致，能复用现有工具审批、结果驱逐、取消和产物回读。显式生命周期工具只在“必须让模型选择镜像/创建多个沙盒”时启用；一旦启用，应让所有 exec/文件工具都走同一个 sandbox 路由，避免两个执行面并存。

7. **无论选哪种 API，执行进程都不应放在 API/worker 进程内直接持有 Docker socket**。Docker socket 等价于宿主 root 控制面；正确做法是独立 `sandbox-runner` 服务或专用执行节点，API/worker 只通过窄 HTTP/Unix socket 调用，且 runner 与不可信负载分节点部署。`ShellToolMiddleware` 的 `DockerExecutionPolicy` 也是从 agent 进程直接调用 `docker` CLI，因此同样不能把 API/worker 当成无隔离的 Docker 控制面。

## 方案对比

下表中的“成熟度”指该能力在官方文档/源码中是否有稳定 API 和生命周期语义，不代表安全审计或生产验证。

| 方案 | 创建/生命周期 | shell 执行 | 文件 API | 镜像/模板 | 挂载/持久化 | 隔离边界 | 与 Agent 工具的关系 |
|---|---|---|---|---|---|---|---|
| E2B | `Sandbox.create(timeout=...)`、`connect`、`pause`、`kill`；`set_timeout`；运行上限 Hobby 1h / Pro 24h；暂停保留内存和文件，暂停实例无限期保留 | `sandbox.commands.run(cmd, background=True, envs=..., timeout=...)`；`commands.kill`；`commands.connect(pid)` 重连后台命令 | `files.read/write/write_files/get_info/make_dir`；上传、下载、watch、metadata 分页文档 | 模板由基础镜像 + 构建命令 + start/ready 命令构建成预启动 VM 快照；默认用户 `user`、工作目录 `/home/user`；模板可固定内核 | `volume_mounts={'/mnt': volume}` 创建时挂载；Volume 独立于沙盒；快照可派生多个沙盒 | Firecracker microVM；每沙盒独立 cgroup、网络命名空间和 guest 内核；`envd` 在 VM 内提供进程/文件 API | 应用/SDK 创建，Agent 通过工具包装 `commands.run`；官方 DeepAgents adapter 为 `E2BSandbox` |
| Daytona | `daytona.create(snapshot=..., image=..., resources=..., ephemeral=..., auto_stop_interval=...)`；`start/stop/delete`；容器沙盒默认 15 分钟自动停止、7 天自动归档 | `sandbox.process.exec(cmd, cwd=..., timeout=..., env=...)`，默认超时 10 秒；`process.code_run`；session + `run_async` 后台执行；`sandbox.code_interpreter.run_code` 有状态上下文 | `sandbox.fs.list_files/get_file_info/create_folder/upload_file/download_file/upload_files/download_files` | 从默认 snapshot、公开 OCI image（需 tag/digest）或自定义 snapshot 创建；VM 沙盒只能从已有 VM snapshot 创建 | FUSE volume，数据在 S3 兼容对象存储；多沙盒共享，支持 `subpath` 隔离；sandbox 可挂载多个 volume | 容器类：独立命名空间 + cgroup 硬限制；VM 类：独立内核；网络 egress 可按 CIDR/域名/全阻断配置 | 应用 SDK 创建；DeepAgents adapter 为 `DaytonaSandbox`；生命周期在 agent 外 |
| Modal | `modal.Sandbox.create(image=..., volumes=..., cpu=..., memory=..., timeout=300, idle_timeout=..., runtime="gvisor"\|"vm")`；`terminate`、`detach`、`from_id`、`list`；默认最长 5 分钟，可到 24 小时 | `sb.exec("cmd", "-c", ...)`；`stdin.write`；`p.stdout`/`stderr`；`returncode`/`poll`；`wait_until_ready` | `sb.filesystem.write_text/read_text/copy_from_local/copy_to_local/make_directory/list_files/stat/remove` | 任意 `modal.Image`；支持从 registry 构建、层缓存、私有 registry；VM runtime 可运行 Docker/FUSE/嵌套 cgroup | `volumes={"/data": modal.Volume.from_name(...)}`；CloudBucketMount；文件系统快照/目录快照 | `runtime="gvisor"` 为 gVisor 容器隔离；`runtime="vm"` 为独立 Linux 内核；GPU 沙盒要求 gVisor | 应用 SDK 创建；DeepAgents adapter 为 `ModalSandbox`；不是模型自动创建 |
| Cloudflare Sandboxes | 命名 sandbox → Durable Object → Container 实例；`ctx.container.start({image, entrypoint, enableInternet})`；`setInactivityTimeout()` 最长 6 小时；实例停止后磁盘文件删除 | `container.exec(["bash","-lc",cmd])`；`process.output()`；`kill()`/`AbortSignal`；没有内建 exec 超时；后台进程/终端/SSE 有独立指南 | 新版 `Files` 类：`readFile/writeFile/stat/lstat/readDirectory/mkdir/rename/remove`；`S3Mount` 通过 s3fs + Worker 网关挂 R2/S3 前缀 | 镜像由 Wrangler `containers.images` 的 Dockerfile 定义；`start({image})` 选择已构建镜像；镜像需包含 `sandbox-shim` | `S3Mount.mount({mountPath, ...})`；目录备份到 R2；Container snapshot 只保存可写根盘，不含内存/进程/独立挂载 | 每个 Container 实例是独立 microVM，拥有自己的内核和网络；Durable Object 负责路由和身份 | 应用/Worker 创建，Agent 通过 Worker 暴露的工具调用 `exec`；官方 coding-agent 指南按任务使用独立 sandbox |
| Vercel Sandbox | `Sandbox.create({image, timeout=5m, persistent=true, mounts, networkPolicy, ports, env})`；`get/getOrCreate/fork/stop/delete`；`extendTimeout`；按 name 恢复 | `sandbox.runCommand(cmd, args, {cwd, env, sudo, detached, stdin, signal})`；`Command.wait()`；`getCommand` | `sandbox.fs` 兼容 `node:fs/promises` 的 `readFile/writeFile/mkdir/readdir/rm/rename`；`readFileToBuffer/downloadFile/writeFiles` | Vercel Managed Images 或 Vercel Container Registry 中的自定义 OCI 镜像；默认 `vercel/sandbox/universal` | `mounts` 按绝对路径挂载 Drive；Drive 可持久、可只读快照；持久 sandbox 停止时自动快照文件系统 | Firecracker microVM，独立文件系统和网络；支持 root 级进程和 Docker/FUSE；多 Agent 可用 Linux user/group 隔离 | 应用 SDK 创建；DeepAgents adapter 为 `VercelSandbox`；生命周期在 agent 外 |
| OpenHands DockerWorkspace | `DockerWorkspace(server_image=..., volumes=[...])` 在构造时 `docker run -d --rm`，等待 `/health`，`cleanup()` 执行 `docker stop`；`pause()/resume()` 用 `docker pause/unpause` | Agent Server 在容器内；`RemoteWorkspace.execute_command` 走 HTTP `/api/bash/start_bash_command`，可停止命令；不是宿主直接 `docker exec` | 由 Agent Server 的 workspace/文件工具提供，宿主通过 HTTP 访问 | `server_image` 默认 `ghcr.io/openhands/agent-server:latest-python`；子类可在启动前构建镜像 | `volumes` 直接传给 `docker run -v`；`/workspace` 为容器工作目录；宿主侧 Docker CLI 创建容器，agent 容器内不挂 docker.sock | 普通 Docker 容器，隔离强度取决于宿主 Docker 配置；源码没有默认 seccomp/cap-drop 强化 | 平台按会话创建容器，Agent 只看到远程 workspace 的 exec/文件工具；这是“透明 workspace”而非模型建沙盒 |
| Kubernetes agent-sandbox | `Sandbox` CRD：`podTemplate`、`volumeClaimTemplates`、`shutdownTime/policy`、`operatingMode: Running\|Suspended`；`SandboxTemplate` + `SandboxWarmPool` + `SandboxClaim` 提供模板、预热池和认领 | CRD 本身不提供 exec API；通过 Pod 内 Agent Server、`kubectl port-forward`、sandbox-router 或集群网络访问 | 由 Pod 内 runtime 提供；PVC 持久化工作区 | Pod 模板中的任意镜像；模板由管理员定义；`SandboxTemplate` 可固定 `runtimeClassName` | `volumeClaimTemplates` 创建 PVC，Sandbox 挂起/过期后保留，删除 Sandbox 时回收；支持 headless Service/稳定身份 | 控制器只编排 Pod，不实现隔离；由 `RuntimeClass` 选择 gVisor/Kata 等；威胁模型建议默认禁止 ServiceAccount token、默认 NetworkPolicy 限制跨租户 | 平台创建/认领，Agent 通过 Pod 内 server 执行；OpenHands 已提供 `AgentSandboxWorkspace` 消费 warm pool |
| microsandbox | `Sandbox.create("name", image="python", cpus=1, memory=512)` 或 builder；`stop`；CLI `msb run/create/exec/stop`；MCP `sandbox_create/sandbox_run/sandbox_remove`；支持 detached 和 idle timeout | SDK `sandbox.exec("python", [...])`；MCP `sandbox_exec`（argv）、`sandbox_shell`（shell string）、`sandbox_exec_start/poll/write_stdin/signal/close` | MCP `sandbox_fs_read/write/list/mkdir/remove/copy/rename/stat/exists`；SDK 有文件 API | OCI 镜像（Docker Hub/GHCR）；`msb` 本地缓存镜像；支持 rootfs、资源、process、mounts、patches、network、secrets | `-v/--volume SOURCE:GUEST[:OPTIONS]`、`--mount-dir/file/disk/named`；命名 volume 独立于沙盒；快照/恢复；宿主路径受 MCP allowlist 限制 | libkrun microVM；KVM（Linux）/Hypervisor.framework（macOS）/WHP（Windows）；每 VM 独立内核；宿主进程非特权，virtio 设备为唯一通道；默认拒绝私网/宿主/元数据地址 | 显式工具服务器模式：MCP 直接暴露 create/exec/destroy，是“Agent 自主建沙盒”的最直接先例；也可作为 SDK 由应用管理 |
| LangChain `ShellToolMiddleware` + `DockerExecutionPolicy` | 由 `ShellToolMiddleware` 在 agent run 开始时启动一个持久 shell 容器，run 结束时清理；`DockerExecutionPolicy` 配置镜像、`--rm`、`--network none`、`--read-only`、`--user`、`--cpus`、`--memory`、额外 `docker run` 参数；不是模型可调用的 create/destroy API | 模型调用中间件注册的 `shell` 工具，命令写入同一个持久 shell 会话；`command_timeout` 默认 30 秒，超时杀进程组 | 没有独立的文件 API；通过 workspace bind mount 让容器直接读写宿主目录；不挂载时不暴露宿主目录 | `image` 由 policy 配置，默认 `python:3.12-alpine3.19`；没有模型侧镜像选择 | 默认 `--network none`；workspace 仅当是已存在的非临时目录才绑定挂载；可选 `read_only_rootfs`、`user`、`cpus`、`memory`；不默认加 `--cap-drop`/`--pids-limit` | 普通 Docker 容器；安全取决于 daemon 配置，官方 docstring 建议 rootless、AppArmor/SELinux；不提供 VM/gVisor 边界 | 显式 shell 工具中间件；第一方先例，但不是 DeepAgents backend，且与现有 `execute` 是两套工具面 |
| Docker/Podman | `docker run`/`podman run -d` 创建；`exec` 在运行中容器启动新进程；`stop/rm`；无内建空闲回收，需要平台自己实现 | `docker exec [-u user] [-w dir] [-e env] [-d] container cmd`；`podman exec` 类似；`docker exec` 无超时，客户端被杀不等于容器内进程终止 | 通过 bind mount 或 `docker cp`/容器内 shell；没有统一文件协议 | 任意 OCI 镜像；`--runtime=runsc` 使用 gVisor，`--runtime=kata` 使用 Kata；`--read-only`、`--tmpfs`、`--user`、`--cap-drop`、`--security-opt no-new-privileges`、`--pids-limit`、`--memory`、`--cpus`、`--network` | `-v host:container[:ro]` 或 `--mount type=bind,src=...,dst=...,readonly`；bind mount 默认可写，能修改宿主文件；rootless Podman 用 user namespace 和 subuid/subgid | 普通容器共享宿主内核；rootless 降低宿主 root 风险但不消除内核攻击面；gVisor 提供用户态应用内核；Kata/FC 提供 VM 边界 | 最底层原语；可作为透明 Backend 的实现，也可被 runner 服务包装成显式工具 |

## 逐方案关键事实

### E2B

E2B 的公开 SDK 以 sandbox 为生命周期单位。`Sandbox.create(timeout=60)` 后得到运行中的沙盒，`Sandbox.connect(sandbox_id)` 可重连，`pause()` 保留文件系统和内存，`kill()` 释放资源；`get_info()` 返回 `state`、`lifecycle`、`volumeMounts` 等字段。文档写明 Hobby 连续运行上限 1 小时、Pro 24 小时，暂停会重置运行窗口且暂停实例无限期保留。[Sandbox lifecycle](https://docs.e2b.dev/sandbox)、[Sandbox persistence](https://docs.e2b.dev/sandbox/persistence)

命令 API 是 `sandbox.commands.run()`。后台命令通过 `background=True` 立即返回句柄，`commands.kill()` 终止；后台命令在 SDK 断开后仍可在沙盒内运行，之后可用 `commands.connect(pid)` 从另一进程重连并读取输出。文档示例把不可信输入放进 `envs`，而不是拼进 shell 字符串。[Commands](https://docs.e2b.dev/commands)、[Background commands](https://docs.e2b.dev/commands/background)、[Streaming](https://docs.e2b.dev/commands/streaming)

文件 API 包括 `files.read()`、`files.write()`、`files.write_files()`、`files.get_info()`、`files.make_dir()`，另有目录 watch、上传、下载和自定义 metadata 的独立页面。[Read & write files](https://docs.e2b.dev/filesystem/read-write)、[File info](https://docs.e2b.dev/filesystem/info)

模板表示构建后的预启动 VM 快照，不只包含镜像名：模板定义基础镜像、环境变量、复制文件、构建命令和 start/ready 命令；构建时启动沙盒并快照整个文件系统和运行进程，之后创建沙盒相当于恢复快照。默认用户是 `user`，默认工作目录是 `/home/user`。[Template quickstart](https://docs.e2b.dev/template/quickstart)、[How templates work](https://docs.e2b.dev/template/how-it-works)、[User and workdir](https://docs.e2b.dev/template/user-and-workdir)

挂载使用创建时的 `volume_mounts`，键是沙盒内路径，值可以是 `Volume` 对象或 volume 名称；写入该路径的文件持久化到 volume。[Mounting volumes](https://docs.e2b.dev/volumes/mount)

隔离边界由 E2B Runtime 官方仓库说明：每个 sandbox 一个 Firecracker microVM，位于独立 cgroup 和网络命名空间；模板是预启动 VM 的内存、磁盘和机器状态，创建沙盒是恢复快照而不是启动内核；VM 内 `envd` 提供进程、PTY、文件、watch 和端口转发 API。[E2B Runtime README](https://github.com/e2b-dev/runtime)、[Architecture](https://github.com/e2b-dev/runtime/blob/main/docs/ARCHITECTURE.md)

### Daytona

Daytona 的 `daytona.create()` 接受 `snapshot`、`image`、`resources`、`env_vars`、`ephemeral`、`auto_stop_interval`、`auto_archive_interval`、`auto_delete_interval` 等参数；`sandbox.start()/stop()/delete()` 是显式生命周期方法。自动停止默认 15 分钟，自动归档默认 7 天且只适用于容器沙盒；自动删除支持 `-1` 禁用、`0` 停止后立即删除。资源默认 1 vCPU/1 GiB/3 GiB 磁盘，组织上限示例为 4 vCPU/8 GiB/10 GiB。[Sandboxes](https://www.daytona.io/docs/en/sandboxes)

执行 API 有两类：无状态 `sandbox.process.exec()`（默认超时 10 秒，支持 `cwd`、`timeout`、`env`）和 `sandbox.process.code_run()`；有状态代码解释器用 `sandbox.code_interpreter.run_code(context=...)`；长任务用 session + `run_async`，日志可通过 HTTP 或 WebSocket 跟随。[Process & code execution](https://www.daytona.io/docs/en/process-code-execution)

文件 API 是 `sandbox.fs.list_files()`、`get_file_info()`、`create_folder()`、`upload_file()`、`download_file()`，以及批量上传/下载和流式传输。[File system operations](https://www.daytona.io/docs/en/file-system-operations)

镜像与快照：`snapshot.create(CreateSnapshotParams(name=..., image="ubuntu:22.04"))` 可从公开 OCI 镜像或 Dockerfile 构建；VM 沙盒只能从已有 VM snapshot 创建，不能直接用 Dockerfile/declarative build。也可以从运行中的 sandbox 捕获 snapshot。[Snapshots](https://www.daytona.io/docs/en/snapshots)

挂载是 FUSE volume，数据在 S3 兼容对象存储，多个 sandbox 可挂同一个 volume；官方建议一个用例/环境共享一个 volume，并用 `subpath` 让每个 sandbox 只看到自己的前缀。[Volumes](https://www.daytona.io/docs/en/volumes)

隔离边界分层清楚：容器沙盒是独立命名空间和 cgroup 硬限制；VM 沙盒有独立内核；网络 ingress/egress 可分别配置，默认 sandbox-to-sandbox 不互通。[Isolation](https://www.daytona.io/docs/en/isolation)、[Architecture](https://www.daytona.io/docs/en/architecture)

### Modal Sandboxes

Modal 的 `modal.Sandbox.create()` 参数包括 `image`、`volumes`、`cpu`、`memory`、`timeout`（默认 300 秒，最大 24 小时）、`idle_timeout`、`workdir`、`runtime`、`block_network`、`outbound_cidr_allowlist`、`outbound_domain_allowlist`、`inbound_cidr_allowlist`、`pty`、`readiness_probe` 等。`terminate()` 发送 SIGKILL，`detach()` 断开客户端但保留沙盒，之后可用 `from_id` 重连。沙盒在 `exec` 运行、stdin 写入或 TCP tunnel 打开时视为活跃；`idle_timeout` 到期自动终止。[Sandboxes guide](https://modal.com/docs/guide/sandboxes)、[Python SDK Sandbox](https://modal.com/docs/sdk/py/latest/Sandbox)

执行用 `sb.exec()`，返回类似 `asyncio.subprocess.Process` 的对象，可读 `stdout/stderr`、写 `stdin`、查 `returncode`/`poll`。生命周期状态为 `Created → Scheduled → Started → Ready → Finished`，`wait_until_ready()` 配合 readiness probe 使用。

文件访问有独立 `sb.filesystem` API：`write_text`、`read_text`、`copy_from_local`、`copy_to_local`、`make_directory`、`list_files`、`stat`、`remove`。[File access](https://modal.com/docs/guide/sandbox-files)

挂载使用 `volumes={"/data": modal.Volume.from_name(...)}`，也支持 CloudBucketMount。快照分三类：`snapshot_filesystem()` 生成可复用 Image（默认 30 天 TTL）、`snapshot_directory()` 生成目录快照（默认 30 天）、内存快照默认 7 天；文件系统快照可设置 `ttl=None` 永久保留。[Sandbox snapshots](https://modal.com/docs/guide/sandbox-snapshots)

隔离由 `runtime` 选择：`gvisor` 是容器级强隔离，适合多数负载；`vm` 使用独立 Linux 内核，适合 Docker、FUSE、嵌套 cgroup 等需要内核能力的场景；GPU 沙盒要求 gVisor。[Sandboxes guide](https://modal.com/docs/guide/sandboxes)

### Cloudflare Sandboxes

Cloudflare 的模型是“命名 sandbox → Durable Object → Container 实例”。Worker 通过 `getByName()` 找到同一个 Durable Object；Durable Object 用 `ctx.container.start({image, entrypoint, enableInternet})` 启动实例。实例在 Durable Object 活跃期间运行；Durable Object 不活跃后，实例还会按 `setInactivityTimeout()` 保留最多 6 小时，之后停止。停止实例会删除其磁盘文件；需要保留时由应用显式创建 Container snapshot 或备份到 R2。[Sandbox lifetime](https://developers.cloudflare.com/sandbox/concepts/lifetime/)、[Sandboxes overview](https://developers.cloudflare.com/sandbox/)

Container API 的 `exec()` 直接启动可执行文件，不解释 shell、管道或重定向；要 shell 语义必须显式 `["bash","-lc",cmd]` 或 `["sh","-c",cmd]`。`exec()` 没有内建超时；`kill()`/`AbortSignal` 只作用于 `exec()` 启动的那个进程，子进程可能继续运行。文档建议用进程组/额外停止逻辑处理整棵进程树。[Durable Object container API](https://developers.cloudflare.com/containers/api/durable-object-container/)

新版 `@cloudflare/sandbox` 包不负责启停容器，而是在已运行容器上提供 `Files`、`S3Mount`、`DirectoryBackup` 等类。`Files` 提供 `readFile`、`writeFile`、`stat`、`lstat`、`readDirectory`、`mkdir`、`rename`、`remove`；镜像必须包含 `/usr/local/bin/sandbox-shim`，该 helper 从对应版本的 `cloudflare/sandbox` 镜像复制。[Package reference](https://developers.cloudflare.com/sandbox/reference/)、[Files API](https://developers.cloudflare.com/sandbox/reference/files/)

`S3Mount` 用容器内 `s3fs` 把 R2/S3 前缀挂到路径，存储请求经 Worker 内的 `S3Gateway` 校验和签名，容器不持有凭据；`S3Mount` 不启动/停止容器。`snapshotContainer()` 只捕获可写根文件系统，不含内存、运行进程或独立挂载；快照句柄有 30 天 TTL，恢复时重新执行 entrypoint。[S3Mount API](https://developers.cloudflare.com/sandbox/reference/s3-mounts/)、[Container API](https://developers.cloudflare.com/containers/api/durable-object-container/)

隔离方面，官方文档明确每个 Container 实例是独立 microVM，有自己的内核和网络；同一 sandbox 的代码可以访问 Worker 放进去的所有东西，因此安全建议是每个 sandbox 只放该任务必需的文件、凭据和网络权限。[Sandboxes overview](https://developers.cloudflare.com/sandbox/)、[Security model](https://developers.cloudflare.com/sandbox/sdk/concepts/security/)

### Vercel Sandbox

Vercel 用 `Sandbox.create()` 创建 microVM，参数包括 `image`、`source.snapshot`、`timeout`（默认 5 分钟）、`persistent`（默认 true）、`mounts`、`networkPolicy`、`ports`、`env`、`snapshotExpiration`、`keepLastSnapshots`。停止时持久 sandbox 自动快照文件系统，下次按 name 恢复；`persistent: false` 则一次性。`sandbox.stop()` 返回快照元数据，`sandbox.delete()` 永久删除实例但快照继续存在到过期或显式删除。[JS SDK reference](https://vercel.com/docs/sandbox/sdk-reference)、[Vercel Sandbox](https://vercel.com/docs/sandbox)

`runCommand()` 支持阻塞和 `detached` 两种模式，参数包括 `cwd`、`env`、`sudo`、`stdin`、`signal`、`stdout/stderr`；`Command.wait()` 取最终结果。文件侧 `sandbox.fs` 是 `node:fs/promises` 兼容接口，另有 `readFile/readFileToBuffer/downloadFile/writeFiles/mkDir`。[JS SDK reference](https://vercel.com/docs/sandbox/sdk-reference)

镜像可以是 Vercel Managed Images 或 Vercel Container Registry 中的自定义 OCI 镜像；`Sandbox.create({image: 'my-repository:latest'})`。[Images](https://vercel.com/docs/sandbox/concepts/images)、[Working with Sandbox](https://vercel.com/docs/sandbox/working-with-sandbox)

挂载用 `mounts`，按绝对路径挂载 Drive（持久文件系统）或 `drive.snapshot()`（只读时点快照）；也可以挂载 S3 兼容对象存储的 FUSE 驱动。[Vercel Sandbox](https://vercel.com/docs/sandbox)、[JS SDK reference](https://vercel.com/docs/sandbox/sdk-reference)

隔离是每 sandbox 一个 Firecracker microVM，独立文件系统和网络；官方明确支持系统级特权进程、Docker、VPN、FUSE，并提供多 Agent 的 Linux user/group 隔离。[Vercel Sandbox](https://vercel.com/docs/sandbox)、[Concepts](https://vercel.com/docs/sandbox/concepts)

### OpenHands runtime

当前 OpenHands 的运行时事实由 `software-agent-sdk` 拥有，而不是旧版 `openhands/runtime` 目录。`DockerWorkspace` 在构造时执行 `docker run -d --rm --ulimit nofile=65536:65536 -p 127.0.0.1:<port>:8000 <server_image> --host 0.0.0.0 --port 8000`，把 `volumes` 原样传给 `-v`，等待容器 `/health`，`cleanup()` 时 `docker stop`。容器内运行的是 OpenHands Agent Server，宿主通过 HTTP 调用 `/api/bash/start_bash_command` 等接口执行命令，而不是宿主直接 `docker exec`。[DockerWorkspace source](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-workspace/openhands/workspace/docker/workspace.py)、[RemoteWorkspace source](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/workspace/remote/base.py)

`volumes` 的推荐用法是 `volumes=['/host/dir:/workspace']`；源码明确拒绝旧的 `mount_dir` 参数。`pause()/resume()` 使用 `docker pause/unpause`。该实现没有把 `docker.sock` 挂进 agent 容器；Docker CLI 在宿主/服务进程侧运行，因此风险集中在服务进程对 Docker daemon 的访问，而不是 agent 代码可直接控制 daemon。[DockerWorkspace source](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-workspace/openhands/workspace/docker/workspace.py)

OpenHands 还提供 `AgentSandboxWorkspace`：它用 `k8s_agent_sandbox` 从 `SandboxWarmPool` 认领 Pod，默认用 `kubectl port-forward` 连接 Pod 内的 Agent Server；`pause()/resume()` 通过修改 Sandbox 的 `operatingMode` 实现；`shutdown_after_seconds` 作为防泄漏 TTL。源码注释明确说 Pod 可通过 `SandboxTemplate` 的 `runtimeClass` 使用 gVisor 或 Kata，这是基础设施选择而不是 Python 层实现。[AgentSandboxWorkspace source](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-workspace/openhands/workspace/agent_sandbox/workspace.py)

OpenHands 顶层 README 的部署说明也写明：多 Docker 沙盒模式下每个新会话有自己的容器和 Agent Server；容器挂载该会话的 workspace 和持久状态，因此替换容器后工作文件和会话历史仍在。[OpenHands README](https://github.com/OpenHands/OpenHands)

### Kubernetes agent-sandbox

该项目的核心是 `Sandbox` CRD，加上扩展 CRD `SandboxTemplate`、`SandboxClaim`、`SandboxWarmPool`。`SandboxSpec` 包含 `podTemplate`、`volumeClaimTemplates`、`shutdownTime`、`shutdownPolicy`（Retain/Delete）和 `operatingMode`（Running/Suspended）。挂起时控制器终止 Pod 但保留 Sandbox 对象和 PVC；恢复时按当前 podTemplate 新建 Pod 并重新挂载 PVC。[README](https://github.com/kubernetes-sigs/agent-sandbox)、[Sandbox types](https://github.com/kubernetes-sigs/agent-sandbox/blob/main/api/v1beta1/sandbox_types.go)、[API reference](https://github.com/kubernetes-sigs/agent-sandbox/blob/main/docs/api.md)

`SandboxWarmPool` 通过 `replicas` 和 `sandboxTemplateRef` 维护预热 Sandbox；`SandboxClaim` 从池中认领，认领后所有权转移给 Claim，池不再替换它。Claim 可以设置环境变量或 volumeClaimTemplates，但设置这些字段会强制冷启动而不是使用预热 Pod。[WarmPool types](https://github.com/kubernetes-sigs/agent-sandbox/blob/main/extensions/api/v1beta1/sandboxwarmpool_types.go)、[API reference](https://github.com/kubernetes-sigs/agent-sandbox/blob/main/docs/api.md)

项目明确把自己定位为“sandbox orchestrator”，不实现底层隔离，而是通过 Pod 的 `RuntimeClass` 交给 gVisor、Kata 等安全运行时。威胁模型建议：默认 `automountServiceAccountToken=false`；用 NetworkPolicy 默认阻断跨 Sandbox 网络并限制 egress；用 Pod 的 `resources.limits` 限制 CPU/内存；管理员通过 `SandboxTemplate` 固定镜像和 runtimeClass。[README](https://github.com/kubernetes-sigs/agent-sandbox)、[Threat model](https://github.com/kubernetes-sigs/agent-sandbox/blob/main/docs/security/threat_model.md)

CRD 本身没有 exec API。执行能力来自 Pod 内运行的 Agent Server 或其它服务；OpenHands 的 `AgentSandboxWorkspace` 就是通过 port-forward 访问 Pod 内的 OpenHands Agent Server。这一层与 Yuxi 的 `UserSandboxBackend` 很像：CRD 负责生命周期，业务代码负责把 exec/文件协议接到 Agent 工具。

### microsandbox

microsandbox 用 libkrun 在本地启动 microVM：Linux 需要 KVM，macOS 用 Hypervisor.framework，Windows 用 WHP；每个 sandbox 有独立 guest 内核和内存，宿主进程非特权，guest 只能通过 virtio console/net/fs/disk 与宿主交互。[README](https://github.com/superradcompany/microsandbox)、[Isolation boundary](https://docs.microsandbox.dev/security/isolation)

SDK 的典型用法是 `Sandbox.create("name", image="python", cpus=1, memory=512)`，然后 `sandbox.exec("python", ["-c", "..."])`，最后 `sandbox.stop()`。镜像来自 OCI registry，本地缓存；CLI 支持 `msb run/create/exec/stop`、`--volume`、`--mount-dir/file/disk/named`、网络 profile/规则、detached、idle timeout。[SDK overview](https://docs.microsandbox.dev/sdk/overview)、[CLI sandbox commands](https://docs.microsandbox.dev/cli/sandbox-commands)

文件系统安全文档说明：guest 默认只看到镜像和显式挂载；共享宿主目录通过 virtio-fs，宿主侧 broker 用 `openat2 RESOLVE_BENEATH`（Linux 5.6+）阻止 `..`、symlink 逃逸和 procfs magic-link；只读挂载在宿主侧强制；默认虚拟化 guest 看到的 uid/gid/mode。命名卷是“沙盒间隔离的有意缺口”，挂载同一卷的 sandbox 能看到彼此写入。[Filesystem security](https://docs.microsandbox.dev/security/filesystem)

网络默认拒绝私网、loopback、link-local、云元数据和宿主，只允许公网和 DNS；入站只到显式发布端口，发布端口默认绑定宿主 `127.0.0.1`。[Network defenses](https://docs.microsandbox.dev/security/network)

MCP server 是“Agent 自主建沙盒”的直接先例。它提供 `sandbox_run`（临时创建-执行-删除）、`sandbox_create`（持久沙盒，支持 rootfs、资源、process、mounts、patches、network、secrets、lifecycle）、`sandbox_start/stop/remove`、`sandbox_exec/sandbox_shell`、完整 `sandbox_fs_*`、volume/image/snapshot 工具。宿主路径默认使用 `MICROSANDBOX_MCP_HOST_PATHS` allowlist，策略默认 `allowlist`，可显式改成 `unrestricted`；危险操作另有开关。[microsandbox MCP](https://github.com/superradcompany/microsandbox-mcp)

需要保留的限制：项目 README 自述仍是 beta；安全文档说 snapshot 只捕获可写层和基础镜像清单，不捕获内存、进程或网络状态，恢复得到新的独立沙盒；CLI 另有 full snapshot/fork 能力，二者语义不能混为一谈。[README](https://github.com/superradcompany/microsandbox)、[Filesystem security](https://docs.microsandbox.dev/security/filesystem)

### Docker/Podman、gVisor、Kata、Firecracker

Docker 的 `exec` 是在运行中容器里启动一个新命令，命令只在 PID 1 存活期间运行；参数支持 `-d`、`-e`、`-i`、`-t`、`-u`、`-w`、`--privileged`。`docker exec` 不做 shell 解释，链式命令必须显式 `sh -c`。[docker exec](https://docs.docker.com/reference/cli/docker/container/exec/)

`docker run` 提供 `--mount`/`-v`、`--read-only`、`--user`、`--userns`、`--cap-drop`、`--security-opt`、`--pids-limit`、`--memory`、`--cpus`、`--network`、`--runtime` 等隔离和资源参数；`--use-api-socket` 甚至可以直接把 Docker API socket 挂进容器，这正说明它是高风险能力而不是默认安全配置。[docker run](https://docs.docker.com/reference/cli/docker/container/run/)

Docker 官方安全文档的核心事实：daemon 默认需要 root（除非 rootless）；只有可信用户才应控制 daemon；bind mount 默认对宿主文件有写权限，容器可以创建、修改、删除宿主文件；把宿主 `/` 挂进容器，容器就能无限制修改宿主文件系统。Docker socket 的证书/密钥等同于宿主 root 访问，官方原文是“giving them root access to the machine hosting the daemon”。[Docker Engine security](https://docs.docker.com/engine/security/)、[Protect the Docker daemon socket](https://docs.docker.com/engine/security/protect-access/)、[Bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)

Rootless Docker 在 user namespace 内运行 daemon 和容器，daemon 与容器都不以 root 运行，但依赖 `newuidmap/newgidmap`、`/etc/subuid`、`/etc/subgid` 和 cgroup delegation；它降低宿主 root 风险，不改变共享宿主内核。[Rootless mode](https://docs.docker.com/engine/security/rootless/)

Podman 的 rootless 模式在用户 namespace 中运行，子 UID/GID 来自 `/etc/subuid`、`/etc/subgid`；非 root 用户创建的容器对其他用户不可见，也不由 root 的 Podman 管理。[Podman rootless](https://docs.podman.io/en/latest/markdown/podman.1.html)、[podman exec](https://docs.podman.io/en/latest/markdown/podman-exec.1.html)

gVisor 是用户态应用内核 `Sentry`，通过 `runsc` 接入 Docker/Kubernetes；它拦截应用对宿主内核的系统调用，自己实现 Linux-like ABI，目的是降低容器逃逸和宿主内核漏洞利用面。官方明确说它不是 VM，安全模型与 VM 有不同权衡。[What is gVisor](https://gvisor.dev/docs/)、[Security Model](https://gvisor.dev/docs/architecture_guide/security/)、[Docker quick start](https://gvisor.dev/docs/user_guide/quick_start/docker/)

Kata Containers 是兼容 OCI 的 runtime，用轻量 VM 承载容器，提供硬件虚拟化作为第二层隔离；每个 Kata 容器/Pod 有 guest 内核，通过 shimv2 与 containerd/CRI-O 集成。[Kata README](https://github.com/kata-containers/kata-containers/blob/main/README.md)、[Architecture](https://github.com/kata-containers/kata-containers/blob/main/docs/design/architecture/README.md)

Firecracker 是 KVM-based microVM，最小设备模型（官方称 5 个 emulated devices）、<125ms 启动、<5 MiB 内存开销，面向多租户 serverless/容器负载。[Firecracker](https://firecracker-microvm.github.io/)

### LangChain middleware 与 DeepAgents 扩展点

LangChain 的自定义中间件通过 `AgentMiddleware` 的 node-style hooks（`before_agent`、`before_model`、`after_model`、`after_agent`）和 wrap-style hooks（`wrap_model_call`、`wrap_tool_call`）扩展；`create_agent` 的 `middleware=[...]` 注册中间件，`tools=[...]` 注册工具。中间件可以自带工具，但“中间件”本身不是沙盒生命周期协议。[Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom)

DeepAgents 0.7.9 的协议在 `deepagents/backends/protocol.py`：`SandboxBackendProtocol` 继承 `BackendProtocol`，新增 `id` 属性和 `execute(command, *, timeout=None) -> ExecuteResponse`；`BaseSandbox` 实现所有文件操作，子类只需实现 `execute`、`upload_files`、`download_files` 和 `id`。`BaseSandbox` 的 docstring 特别说明：它不缩小也不划分 `execute` 的信任边界，文件 helper 只是建立在子类命令执行原语之上的便利封装。[protocol.py](https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/backends/protocol.py)、[sandbox.py](https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/backends/sandbox.py)

`FilesystemMiddleware` 在每次模型调用时检查 backend 是否支持 `SandboxBackendProtocol`；不支持时 `execute` 工具会被过滤掉。`execute` 工具的签名只有 `command` 和可选 `timeout`，没有 `sandbox_id`；它把命令交给构造时传入的单一 backend，并返回 `ToolMessage`，其中 `status="success"` 只表示命令运行过，退出码在 artifact 中。[filesystem.py](https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/middleware/filesystem.py)

DeepAgents 官方文档把沙盒描述为 backend：配置 sandbox backend 后，Agent 得到标准文件工具和 `execute`；provider adapter（`LangSmithSandbox`、`DaytonaSandbox`、`E2BSandbox`、`ModalSandbox`、`RunloopSandbox`、`VercelSandbox`、`AgentCoreSandbox`、`OpenShellSandbox`）由应用创建后作为 `backend=` 传入 `create_deep_agent`。文档还给出 thread-scoped 与 assistant-scoped 两种生命周期，并提醒在 thread 结束或 TTL 到期时销毁沙盒。[Sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes)、[Backends](https://docs.langchain.com/oss/python/deepagents/backends)

#### LangChain `ShellToolMiddleware` 与 `DockerExecutionPolicy`

Yuxi 锁定的 LangChain 1.3.17 已经包含这条路径，不需要额外依赖。`ShellToolMiddleware` 注册一个名为 `shell` 的持久 shell 工具；`before_agent` 启动 shell 会话，`after_agent` 执行 shutdown 命令并释放资源。它的 `execution_policy` 支持：

- `HostExecutionPolicy`：宿主直接执行，默认值，无文件系统/网络隔离。
- `CodexSandboxExecutionPolicy`：复用 Codex CLI sandbox 的 syscall/文件限制。
- `DockerExecutionPolicy`：为**每次 agent run** 启动一个独立 Docker 容器，`docker run -i --rm`，默认 `--network none`；workspace 是已存在的非临时目录时以 `-v <path>:<path>` 绑定挂载并设为工作目录；支持 `read_only_rootfs`、`user`、`cpus`、`memory_bytes`、`extra_run_args`；默认镜像 `python:3.12-alpine3.19`。[Built-in middleware: Shell tool](https://docs.langchain.com/oss/python/langchain/middleware/built-in#shell-tool)、[_execution.py](https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/middleware/_execution.py)

它和 DeepAgents backend 的关键差异：

- **工具面不同**：这是显式的 `shell` 工具，不是 `FilesystemMiddleware` 的 `execute`；文件工具不会自动跟它走，只有 bind mount 的文件系统效果。
- **生命周期不同**：容器是 per-run，不是 per-user/per-session；run 结束容器删除，Home 和安装的软件不保留。需要持久环境时，这个模型不适用。
- **模型权限不同**：镜像、网络、挂载、资源全部由代码中的 policy 决定；模型只能执行命令，不能创建/销毁沙盒或选择镜像。这是“显式 shell 工具”而不是“自主 sandbox 管理”。
- **安全默认值有限**：默认 `--network none` 和 `--rm` 是好的；但没有默认 `--cap-drop ALL`、`--pids-limit`、`no-new-privileges`、seccomp 自定义；docstring 明确说安全性取决于 Docker daemon 配置，建议 rootless 和 AppArmor/SELinux。
- **控制面风险**：`spawn()` 在 agent 进程内通过 `subprocess` 调用 `docker` CLI，因此 API/worker 必须能访问 Docker daemon。若直接在生产 API/worker 使用，等于把 Docker 控制面放进业务进程；应放到独立 runner 或专用节点。
- **中断/审批限制**：官方文档明确写“Persistent shell sessions do not currently work with interrupts (human-in-the-loop)”。Yuxi 已有工具审批和取消中间件，直接采用前必须验证审批等待、取消和恢复不会破坏持久 shell 会话。

对 Yuxi 的含义：如果只需要一个显式 shell 工具，`ShellToolMiddleware(DockerExecutionPolicy(...))` 是最小可运行原型；但它与现有 `execute` 并存会产生两个 shell 工具，且 per-run 容器不满足“用户跨对话保留软件/Home”的现有产品语义。若目标是替换 Cube 的透明执行后端，仍应走 `SandboxBackendProtocol` 而不是这个中间件。

## 横向模式：什么成熟，什么是产品差异

### 成熟模式

1. **生命周期由平台拥有**：创建、空闲回收、TTL、孤儿清理、快照都在应用/控制面完成。Agent 看到的是 `exec`/文件工具，而不是“创建任意容器”的权限。E2B、Daytona、Modal、Cloudflare、Vercel、OpenHands、k8s agent-sandbox 都是这一模式。
2. **执行是 session 级而不是 per-exec**：先创建/恢复一个 sandbox，再在它上面多次 `exec`。per-exec 创建只适合一次性任务（microsandbox `sandbox_run`、CI 场景）；对交互式 Agent，每次命令都启动容器会破坏 Home、依赖缓存和并发语义。
3. **文件传输与执行分离**：`exec` 适合命令，文件读写有独立 API（E2B `files.*`、Daytona `fs.*`、Modal `filesystem.*`、Vercel `fs.*`、Cloudflare `Files`）。Yuxi 的 `BaseSandbox` 也是这个结构，但文件操作可以走宿主共享挂载而不必全部走 exec。
4. **镜像/模板是受控构建产物**：E2B 模板、Daytona snapshot、Modal Image、Vercel Managed Image/OCI、Cloudflare Dockerfile、k8s PodTemplate 都由平台/管理员定义。允许自定义镜像的产品通常也要求预构建、registry 权限和平台侧配置，而不是让模型在运行时传一个字符串。
5. **快照语义必须显式**：E2B 区分 pause（内存+文件）与 snapshot（可派生多实例）；Modal 区分 filesystem/directory/memory snapshot；Cloudflare snapshot 只含根盘；Vercel 持久 sandbox 停止时自动快照；microsandbox 的普通 snapshot 是磁盘态。把这些混称为“持久化”会导致恢复后进程、内存或挂载内容与预期不符。

### 产品化差异

- **隔离技术**：Firecracker（E2B、Vercel）、每实例 microVM（Cloudflare）、gVisor/VM 二选一（Modal）、容器命名空间/VM 两类（Daytona）、libkrun microVM（microsandbox）、纯 Docker（OpenHands DockerWorkspace）。这决定了能否承载真正的不可信多租户代码。
- **启动延迟**：E2B 用预启动 VM 快照做到约 80ms 恢复；Daytona 有 warm pool；k8s agent-sandbox 用 `SandboxWarmPool`；microsandbox 宣称 <100ms。Docker 冷启动通常更慢，但可通过预拉镜像、预热容器池缓解。
- **持久化模型**：per-thread 临时（DeepAgents 默认建议）、per-user 持久（Yuxi Cube 当前）、per-sandbox 持久（E2B pause、Vercel persistent、Cloudflare snapshot/R2）是不同产品承诺。
- **网络出口**：E2B 默认有公网但可配 allow/deny；Daytona 按 tier 限制并可 CIDR/域名 allowlist；Modal 可 `block_network`；microsandbox 默认拒绝私网/宿主；Cloudflare 通过 Worker/网关控制；Docker 需要平台自己实现。
- **多租户身份**：Daytona 以 organization 为边界；Cloudflare 以 Durable Object 名称/Worker 为边界；Vercel 支持每 sandbox 多 Linux user；Yuxi 以本地用户与 Workspace 为边界。沙盒 API 本身不自动继承 Yuxi 的用户授权。

## 对 Yuxi 的适用性

### Yuxi 当前事实

Yuxi 的 Agent backend 是 `UserSandboxBackend`，继承 DeepAgents `BaseSandbox`，通过 `CubeSandboxProvider` 把命令发到每用户持久 Cube VM；`create_agent_composite_backend()` 把它作为 `CompositeBackend.default`，`routes={}`，并设置 `artifacts_root`。`backend/yuxi/modules/agents/runtime/sandbox/backend.py`、`backend/yuxi/modules/agents/runtime/sandbox/provider.py`

`execute` 工具由 `FilesystemMiddleware` 在检测到 backend 实现 `SandboxBackendProtocol` 后提供；Yuxi 的 `YuxiFilesystemMiddleware` 只额外处理大工具结果驱逐，并显式保留 `ls/read_file/write_file/edit_file/glob/grep/execute`，排除 `delete`。`backend/yuxi/modules/agents/runtime/middlewares/filesystem.py`、`backend/yuxi/modules/agents/runtime/agent_backends/chatbot/graph.py`

文件边界是混合的：`/home/user/workspace` 和 `~/workspace` 由宿主 UserWorkspace 直接读写，`/home/user/skills` 是只读共享投影，其他路径通过 Cube VM 的普通账号进程访问；模型不能指定执行账号。[sandbox.md](../../mechanisms/sandbox.md)

生命周期是每用户一个持久 VM：PostgreSQL 保存实例引用、代次和凭据；用户锁协调创建/恢复/休眠/重建；命令句柄保存 Run/attempt、进程组和清理状态；空闲默认 300 秒暂停；API/worker 重启不删除环境；重建保留 Workspace/Skills，清除 Home 和软件。[sandbox.md](../../mechanisms/sandbox.md)、[sandbox-operations.md](../../advanced/sandbox-operations.md)

标准部署需要专用 Linux/KVM 节点和 Cube 控制面；模板固定为 `CUBE_TEMPLATE_ID`（默认 `yuxi-user`），每个用户 VM 只挂载自己的 Workspace 子目录和只读 Skills，平台来源目录、数据库目录、`.env`、Docker socket 都不挂载。[sandbox-operations.md](../../advanced/sandbox-operations.md)、`backend/yuxi/modules/agents/runtime/sandbox/cube.py`

### 选项 A：Docker/Podman 的透明 `SandboxBackendProtocol`（推荐作为第一步）

做法：新增一个 `ContainerSandboxBackend(BaseSandbox)`（或复用 `UserSandboxBackend` 的接口，provider 可切换），实现 `execute`、`upload_files`、`download_files`、`id`；`execute` 调用独立 runner 的 `exec` API，文件操作优先走宿主 Workspace 挂载，Home 路径走容器内进程。`create_agent_composite_backend()` 根据部署配置选择 Cube 或 Container provider。

优点：

- 不改变 Agent 工具面：模型仍然只有 `execute` 和文件工具，不需要学习 `sandbox_create` 等新工具。
- 复用现有 `FilesystemMiddleware` 的 `execute` 参数校验、超时上限、结果驱逐、ToolMessage/artifact 语义；复用 Yuxi 的审批、取消和 Run 归属。
- 默认不把镜像和挂载暴露给模型，符合 E2B/Daytona/Modal/Vercel/OpenHands 的成熟模式。
- DeepAgents 官方已有 E2B/Daytona/Modal/Vercel adapter 作为同构先例；Yuxi 只是把 Cube provider 换成容器 provider。

限制：

- 一个 Agent graph 构造时绑定一个 backend，`execute` 没有 `sandbox_id` 参数，因此不能在运行中让模型切换沙盒。若要“每个任务一个沙盒”，应在 Run/Thread 维度创建 backend，而不是在工具调用维度切换。
- 需要自己实现空闲回收、孤儿清理、命令取消、文件 UID/GID 和 Workspace 挂载一致性；这些在 Cube provider 已有，不能假设 Docker 自动提供。
- Docker 容器隔离弱于 Cube VM；安全等级必须由部署配置明确，而不是把“能执行”当成“安全隔离”。

### 选项 B：显式 `sandbox.create/exec/destroy` 工具中间件

先例：microsandbox MCP 的 `sandbox_create`/`sandbox_exec`/`sandbox_remove`，以及 Cloudflare/OpenHands 的 coding-agent 按任务创建 sandbox。它们共同点是生命周期由工具服务器或平台拥有，且工具有明确的宿主路径 allowlist、镜像/网络策略。

如果 Yuxi 要做，必须同时满足：

1. **单一执行面**：要么禁用 `FilesystemMiddleware` 的 `execute`，只保留 `sandbox_exec`；要么让 `sandbox_create` 选中的沙盒成为 backend 的“当前沙盒”，使 `execute` 和文件工具都路由到它。两者同时可用会让模型面对两个等价的 shell 工具，审批、超时、结果驱逐和取消逻辑分叉。
2. **服务端策略**：镜像只能从 allowlist（最好 digest）选择；挂载路径只能由认证用户和 Workspace 记录推导，模型不能传宿主路径；网络、CPU/内存/pids、TTL 由服务端强制。
3. **资源归属**：每个 sandbox 绑定 user/thread/run，数据库记录 owner、generation、状态；API 崩溃后能按 label 清理孤儿；不能让模型创建后不销毁就泄漏。
4. **文件工具一致性**：`read_file`/`write_file`/`glob` 默认指向哪个 sandbox 必须明确；如果模型创建了第二个 sandbox，现有文件工具仍指向第一个，会造成“命令在 A、文件读 B”的错位。

结论：显式工具集是成熟的产品模式，但更适合作为**独立的 sandbox MCP/工具服务器**，而不是直接塞进现有 `FilesystemMiddleware` 旁边。对 Yuxi 首版，不建议同时提供两套 exec。

### 两者能否共存

技术上可以：在 `create_deep_agent` 的 `middleware` 中注册一个带 `sandbox_create/exec/destroy` 工具的中间件，同时保留 `FilesystemMiddleware`。但只有以下两种一致形态可接受：

- **形态 1（推荐）**：显式工具只做生命周期（create/destroy/list/status），exec 和文件仍由 `execute` 工具走同一个 router backend；router backend 从 Run/Thread 状态解析“当前 sandbox”。模型看到的是一个 shell 工具加生命周期管理。
- **形态 2**：显式工具包含 `sandbox_exec`，同时关闭 `FilesystemMiddleware` 的 `execute`（通过 `tools=` 排除或使用不支持 `SandboxBackendProtocol` 的 backend），文件工具也改为按 sandbox id 路由。模型看到的是沙盒工具集，不是 DeepAgents 标准文件工具。

不推荐“标准 `execute` + 独立 `sandbox_exec`”并存；两者是语义不同的执行面，同时暴露会制造双重语义。LangChain 的 `ShellToolMiddleware` 也属于同一类显式 shell 面：如果启用它，就应把它当作唯一的 shell 工具，或者让它背后的 runner 与 `execute` 共用同一个 sandbox 路由；不能同时把 `shell` 和 `execute` 都暴露给模型而不解释二者关系。

### 推荐架构

1. **独立 `sandbox-runner` 服务**：API/worker 不直接持有 Docker/Podman socket；runner 在专用节点或至少独立进程中运行，暴露窄 API：`create(user, workspace, image_digest, limits)`、`exec(user, command, cwd, timeout, cancel_token)`、`put/get files`、`stop/remove/status/list`。API/worker 只传认证后的用户和 Workspace 记录，不传模型给出的宿主路径。
2. **Backend 适配层**：`ContainerSandboxBackend(BaseSandbox)` 实现 `execute/upload_files/download_files/id`；`create_agent_composite_backend()` 按 `SANDBOX_BACKEND=cube|container` 选择。保留 Cube 作为强隔离生产后端，容器作为轻量部署后端。
3. **生命周期**：优先“每 Run 临时容器 + 宿主 Workspace 持久化”，适合不可信一次性任务；如果产品要求保留用户安装的软件和 Home，则“每用户持久容器 + 空闲 stop + 显式 rebuild”，并明确 rebuild 清除 Home。两种都比 per-exec 创建更符合现有 Agent 语义。
4. **镜像**：固定默认镜像，预拉取并 pin digest；如允许选择，只允许服务端 allowlist 中的镜像，禁止模型传任意 registry/tag。不要在容器内放私有 registry 凭据。
5. **挂载**：只挂载认证用户的 Workspace 子目录（读写）和只读 Skills 投影；不挂 `/`、`/home` 根、`/var/run`、`/proc`、`/sys`、`/dev`、Docker socket；路径在 runner 侧用已解析的绝对路径 + allowlist 校验，拒绝 `..` 和 symlink 逃逸。
6. **执行取消**：Docker `exec` 没有内建超时，杀客户端不等于杀容器内进程。runner 应在容器内运行一个小 supervisor（启动进程组、记录 pgid、按 cancel token 杀整个组），或使用 Agent Server 模式（OpenHands 的做法），保证 Yuxi 现有“取消/超时清理进程组”的语义不退化。
7. **资源与网络**：`--memory`、`--cpus`、`--pids-limit`、`--ulimit nofile`；`--network none` 或自定义网络 + egress allowlist；默认阻断私网、link-local、云元数据 `169.254.169.254` 和宿主；需要公网装包时显式放行代理。
8. **容器硬化**：`--user 1000:1000`、`--read-only` 根文件系统、`--tmpfs /tmp`、`--cap-drop ALL`、`--security-opt no-new-privileges`、`--init`、不使用 `--privileged`、不共享 host PID/IPC/network、不挂设备。Home 若需可写，用独立 volume 而不是放开根盘。

### 安全结论

**Docker 容器是否足以承载不可信 Agent 代码？**

- 对**单租户、可信代码、开发/演示**：硬化后的 rootless Podman/Docker 可以作为轻量执行环境，但必须明确它是“进程隔离”，不是“安全边界”。
- 对**多租户、不可信 Agent 代码**：不够。Docker 共享宿主内核，容器逃逸/内核漏洞会影响宿主；官方文档也承认 daemon 和 bind mount 的宿主级风险。应使用 gVisor、Kata 或 microVM（Firecracker/microsandbox/Cube）作为真正边界。
- Rootless Podman 降低了“容器内 root 直接变宿主 root”的风险，但不消除共享内核攻击面；它适合作为最低成本基线，不应被宣传为强隔离。

**在 API/worker 进程内挂 docker.sock 的风险**

- Docker daemon 默认 root，控制 daemon 等价于控制宿主；把 socket 挂进 API/worker 后，任何能影响该进程的漏洞、路径穿越、SSRF 或依赖供应链问题都可能升级为宿主 root。
- 把 socket 挂进 Agent 容器更糟：Agent 生成的代码可以直接创建 `--privileged` 容器、挂载宿主 `/`、读取宿主文件或启动任意容器。
- 因此：API/worker 不挂 socket；runner 持有运行时控制面，但 runner 与不可信负载分离，且优先 rootless；强多租户场景把 runner 放到专用节点或用 microVM 隔离。

**推荐的最小隔离方案**

| 场景 | 最小方案 | 残余风险 |
|---|---|---|
| 单机开发/单租户 | rootless Podman + 硬化参数 + 仅 Workspace 挂载 + 无 docker.sock | 共享宿主内核；内核漏洞可逃逸；不适合不可信多租户 |
| 无 KVM、需要更强隔离 | rootless Podman + gVisor `runsc`（若镜像/系统调用兼容） | gVisor 兼容性限制；仍是进程模型；需验证网络/文件语义 |
| 有 KVM、多租户 | Kata Containers 或 microVM（Firecracker/microsandbox）或现有 Cube | 资源开销、镜像构建、运维复杂度更高 |
| 已有 Kubernetes | agent-sandbox CRD + gVisor/Kata RuntimeClass + 默认 NetworkPolicy + 禁用 ServiceAccount token | 控制器本身不提供隔离；PodTemplate 权限必须管理员控制 |

对 Yuxi 的现实建议：**Cube 继续作为强隔离生产后端；轻量部署增加容器后端，但默认只承诺“单租户/可信代码”安全等级；如果轻量部署也要承载不可信多租户，则必须把容器后端升级为 gVisor/Kata/microVM，而不是仅加 Docker。**

## 未核实与不确定

1. **E2B 的命令默认超时、CPU/内存默认值、`commands.run` 的完整参数集**：本次阅读的官方页面没有给出完整签名；需要查 SDK 源码或 API reference 才能确认，本文只记录文档明确出现的 `background`、`envs`、`timeout` 和回调。
2. **Daytona 容器沙盒的底层 runtime**：官方文档只写“独立命名空间 + cgroup”和“VM 类独立内核”，没有说明是否使用 runc/Kata/gVisor 或具体 VMM；不能从文档推断其内核共享细节。
3. **Modal 的 `runtime="vm"` 具体虚拟化技术**：官方只写“VM with its own Linux kernel”，没有在本次页面中命名 Firecracker/Kata/Cloud Hypervisor；`gvisor` 的边界较明确，VM 的具体实现未核实。
4. **Cloudflare Container 的 microVM 实现细节**：官方写“each instance is isolated as a microVM with its own kernel and network”，但没有在本次页面中命名底层 VMM；不能假设是 Firecracker。
5. **Vercel 的快照是否包含内存**：官方说持久 sandbox 停止时快照文件系统，`snapshot()` 捕获文件系统和已安装包；本次页面没有明确内存快照语义，不能把“persistent”理解为保留运行进程。
6. **OpenHands DockerWorkspace 的安全默认值**：源码显示 `docker run` 只显式设置 `--ulimit`、端口、volume、GPU/network 等，没有默认 `--cap-drop`、`--security-opt no-new-privileges`、`--read-only`；实际隔离强度取决于调用方和宿主 Docker 配置，本文不把它视为强隔离实现。
7. **k8s agent-sandbox 的 exec 协议**：CRD 本身没有 exec API；实际执行由 Pod 内 runtime 提供。OpenHands 用 port-forward + Agent Server，其他实现可能用 sandbox-router；本文没有验证所有路径。
8. **microsandbox 的 snapshot 内存语义**：安全文档明确普通 snapshot 是磁盘态、不含内存/进程/网络；README 和 CLI 另有 full snapshot/fork 能力，二者关系需要按版本核对，本文不把 full snapshot 当作默认行为。
9. **Docker/Podman 的 rootless 与 gVisor 组合在 Yuxi 目标内核/发行版上的可用性**：未在 Yuxi 部署环境安装验证；`runsc` 对镜像系统调用、文件系统、网络和 GPU 的兼容性需要真实 E2E。
10. **Yuxi 现有取消语义在 Docker exec 下的等价实现**：Cube provider 已用进程组和持久命令句柄实现取消；Docker exec 没有内建超时，必须新增 supervisor 或 Agent Server。本文没有实现或压测该方案。
11. **Workspace 挂载的 UID/GID 与文件所有权**：Cube 固定 UID/GID 1000；容器若使用不同用户或 rootless 映射，可能出现宿主文件不可写或属主变化，需要在原型中验证。
12. **Yuxi 的审批/取消与 `ShellToolMiddleware` 的兼容性**：官方文档明确持久 shell 会话目前不支持 interrupts；Yuxi 的 `create_tool_approval_middleware` 和 Run 取消路径是否能在该中间件上保持现有语义，未做原型验证。
13. **镜像 supply chain 与多租户镜像构建**：本文只讨论 allowlist/pin digest，没有评估镜像签名、扫描、私有 registry 隔离和构建节点的供应链安全。

## 实际访问的关键来源

以下 URL 均为本次调研实际访问的官方文档、官方仓库或规范页面（访问日期 2026-10-22）。

### E2B

- https://github.com/e2b-dev/runtime
- https://github.com/e2b-dev/runtime/blob/main/docs/ARCHITECTURE.md
- https://docs.e2b.dev/sandbox
- https://docs.e2b.dev/sandbox/persistence
- https://docs.e2b.dev/sandbox/snapshots
- https://docs.e2b.dev/sandbox/connect
- https://docs.e2b.dev/commands
- https://docs.e2b.dev/commands/background
- https://docs.e2b.dev/commands/streaming
- https://docs.e2b.dev/filesystem/read-write
- https://docs.e2b.dev/filesystem/info
- https://docs.e2b.dev/template/quickstart
- https://docs.e2b.dev/template/how-it-works
- https://docs.e2b.dev/template/user-and-workdir
- https://docs.e2b.dev/volumes/mount

### Daytona

- https://www.daytona.io/docs/en/sandboxes
- https://www.daytona.io/docs/en/process-code-execution
- https://www.daytona.io/docs/en/file-system-operations
- https://www.daytona.io/docs/en/snapshots
- https://www.daytona.io/docs/en/volumes
- https://www.daytona.io/docs/en/isolation
- https://www.daytona.io/docs/en/architecture

### Modal

- https://modal.com/docs/guide/sandboxes
- https://modal.com/docs/guide/sandbox-files
- https://modal.com/docs/guide/sandbox-snapshots
- https://modal.com/docs/sdk/py/latest/Sandbox

### Cloudflare

- https://developers.cloudflare.com/sandbox/
- https://developers.cloudflare.com/sandbox/concepts/lifetime/
- https://developers.cloudflare.com/sandbox/reference/
- https://developers.cloudflare.com/sandbox/reference/files/
- https://developers.cloudflare.com/sandbox/reference/s3-mounts/
- https://developers.cloudflare.com/containers/api/durable-object-container/
- https://developers.cloudflare.com/sandbox/sdk/concepts/security/

### Vercel

- https://vercel.com/docs/sandbox
- https://vercel.com/docs/sandbox/sdk-reference
- https://vercel.com/docs/sandbox/concepts/images
- https://vercel.com/docs/sandbox/concepts/persistent-sandboxes
- https://vercel.com/docs/sandbox/working-with-sandbox

### OpenHands

- https://github.com/OpenHands/OpenHands
- https://github.com/OpenHands/software-agent-sdk
- https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-workspace/openhands/workspace/docker/workspace.py
- https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-workspace/openhands/workspace/agent_sandbox/workspace.py
- https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/workspace/remote/base.py

### Kubernetes agent-sandbox

- https://github.com/kubernetes-sigs/agent-sandbox
- https://github.com/kubernetes-sigs/agent-sandbox/blob/main/api/v1beta1/sandbox_types.go
- https://github.com/kubernetes-sigs/agent-sandbox/blob/main/docs/api.md
- https://github.com/kubernetes-sigs/agent-sandbox/blob/main/docs/security/threat_model.md
- https://github.com/kubernetes-sigs/agent-sandbox/blob/main/extensions/api/v1beta1/sandboxwarmpool_types.go

### microsandbox

- https://github.com/superradcompany/microsandbox
- https://github.com/superradcompany/microsandbox-mcp
- https://docs.microsandbox.dev/sdk/overview
- https://docs.microsandbox.dev/security/isolation
- https://docs.microsandbox.dev/security/filesystem
- https://docs.microsandbox.dev/security/network
- https://docs.microsandbox.dev/cli/sandbox-commands
- https://docs.microsandbox.dev/cli/volume-commands

### Docker/Podman/gVisor/Kata/Firecracker

- https://docs.docker.com/engine/security/
- https://docs.docker.com/engine/security/protect-access/
- https://docs.docker.com/engine/storage/bind-mounts/
- https://docs.docker.com/reference/cli/docker/container/exec/
- https://docs.docker.com/reference/cli/docker/container/run/
- https://docs.docker.com/engine/security/rootless/
- https://docs.podman.io/en/latest/markdown/podman.1.html
- https://docs.podman.io/en/latest/markdown/podman-exec.1.html
- https://gvisor.dev/docs/
- https://gvisor.dev/docs/architecture_guide/security/
- https://gvisor.dev/docs/user_guide/quick_start/docker/
- https://github.com/kata-containers/kata-containers/blob/main/README.md
- https://github.com/kata-containers/kata-containers/blob/main/docs/design/architecture/README.md
- https://firecracker-microvm.github.io/

### LangChain / DeepAgents

- https://docs.langchain.com/oss/python/langchain/middleware/custom
- https://docs.langchain.com/oss/python/langchain/middleware/built-in#shell-tool
- https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/middleware/shell_tool.py
- https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/middleware/_execution.py
- https://pypi.org/pypi/langchain/1.3.17/json
- https://docs.langchain.com/oss/python/deepagents/sandboxes
- https://docs.langchain.com/oss/python/deepagents/backends
- https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/backends/protocol.py
- https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/backends/sandbox.py
- https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/middleware/filesystem.py
- https://pypi.org/pypi/deepagents/0.7.9/json

### Yuxi 本地基线

- https://github.com/xerrors/Yuxi/blob/main/docs/mechanisms/sandbox.md
- https://github.com/xerrors/Yuxi/blob/main/docs/advanced/sandbox-operations.md
