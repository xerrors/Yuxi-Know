# Yuxi 沙盒架构与设计

## 文档说明

本文描述的是 **Yuxi 当前已经落地的沙盒实现**，目标是解释它的职责边界、系统结构、运行机制与工程限制。

这不是理想化方案说明，也不是 API 参考手册。阅读本文时，应始终基于一个前提：

> Yuxi 当前的沙盒，定位是“为线程级 Agent 运行与文件访问提供受控工作区”，而不是“对外承诺强安全边界的通用多租户沙箱平台”。

::: warning 预发布
此部分涉及的技术路线与实现细节仍可能调整，文档会随实现演进而更新。
:::

## 1. 设计目标与边界

### 1.1 设计目标

Yuxi 的沙盒主要服务于以下场景：

- 为每个对话线程提供隔离的工作目录
- 为 Agent 提供有限的命令执行能力
- 为 Agent 文件工具提供受控文件系统访问
- 为工作台文件浏览器提供真实目录浏览与文件读取能力
- 将 Skills 以只读形式暴露给 Agent 与工作台

### 1.2 非目标

当前实现明确不覆盖以下目标：

- 强对抗场景下的高强度多租户隔离
- 完整的资源配额与调度系统
- 持久化的沙盒控制平面
- 审计级命令记录与合规追踪
- 面向终端用户的完整文件管理系统

这一点不是缺陷描述，而是范围定义。很多工程选择都建立在这个前提上。

## 2. 总体设计结论

当前沙盒方案可以概括为五个关键词：

- **线程级隔离**：资源归属以 `thread_id` 为核心，采用 `thread_id -> sandbox_id` 的映射
- **容器级执行**：默认使用独立 Docker 容器承载执行环境
- **固定命名空间**：Agent 与工作台通过 `/mnt/user-data`、`/mnt/skills` 访问文件系统
- **惰性获取**：不再依赖公开的 `/api/sandbox/*` 生命周期接口，首次使用时自动获取沙盒
- **双视图接入**：Agent 与工作台共享底层沙盒，但使用不同的文件系统语义与接口

这意味着 Yuxi 当前沙盒的本质是：

- 一个线程隔离的容器工作区
- 一个受限的文件访问模型
- 一个围绕 Agent 与 Viewer 场景设计的工程化执行环境

## 3. 系统架构

### 3.1 架构分层

从职责上，当前实现可以分为四层：

1. **Provisioner 层**
   负责创建、发现、复用和销毁沙盒实例。

2. **Executor 层**
   负责在已经存在的沙盒中执行命令、读写文件、列目录、下载文件。

3. **接入层**
   负责把沙盒能力接入 Agent 文件系统与工作台文件浏览器。

4. **HTTP/UI 层**
   负责将文件浏览能力暴露给前端页面。

### 3.2 关键模块

核心实现主要位于以下位置：

- `backend/package/yuxi/agents/backends/sandbox/`
- `backend/package/yuxi/agents/backends/composite.py`
- `backend/package/yuxi/services/filesystem_service.py`
- `backend/package/yuxi/services/viewer_filesystem_service.py`
- `backend/server/routers/filesystem_router.py`

### 3.3 调用关系

```text
Agent / Frontend
    |
    +-- Agent filesystem tool
    |       |
    |       +-- create_agent_composite_backend(...)
    |               |
    |               +-- default: sandbox backend
    |               +-- route /mnt/skills/: readonly skills backend
    |
    +-- Viewer filesystem panel
            |
            +-- /api/viewer/filesystem/*
                    |
                    +-- viewer_filesystem_service
                            |
                            +-- thread ownership check
                            +-- runtime context / selected skills
                            +-- provider.acquire(thread_id)

Sandbox Provider
    |
    +-- LocalContainerBackend
    |       |
    |       +-- create/discover/destroy docker container
    |       +-- YuxiSandboxBackend executes inside container
    |
    +-- RemoteSandboxBackend
            |
            +-- delegate lifecycle to remote provisioner
```

## 4. 核心抽象与职责划分

这一部分是理解整套实现的关键。当前代码中有多个名字相近的 backend，但职责并不相同。

### 4.1 `SandboxBackend`

定义于 `sandbox_provisioner_base.py`，是生命周期管理接口，负责回答四个问题：

- 如何创建沙盒
- 如何销毁沙盒
- 沙盒是否存活
- 是否可以发现已有沙盒

它只关心 **实例生命周期**，不关心文件访问和命令执行。

### 4.2 `LocalContainerBackend`

定义于 `sandbox_local_container.py`，是默认实现，负责：

- 使用 `docker run` 创建本地沙盒容器
- 使用 `docker stop` 销毁容器
- 发现现存的 `yuxi-sandbox-*` 容器
- 在本地模式下管理端口、容器命名与 warm pool

它的定位是 **本地容器管理器**。

### 4.3 `RemoteSandboxBackend`

定义于 `sandbox_remote.py`，负责通过 HTTP 与远程 provisioner 交互。

它解决的问题是：如果运行环境不适合由当前进程直接管理 Docker 容器，就把生命周期操作交给外部服务。

它的定位是 **远程生命周期代理**。

### 4.4 `YuxiSandboxBackend`

定义于 `sandbox_executor.py`，继承 deepagents 的 `BaseSandbox`，负责：

- 在容器内执行 shell 命令
- 读写和编辑文件
- 列目录、glob、上传、下载
- 进行路径标准化与输出遮蔽

它不负责创建和销毁容器。它工作的前提是：沙盒实例已经存在。

它的定位是 **执行器**，不是生命周期管理器。

### 4.5 `YuxiSandboxProvider`

定义于 `sandbox_provisioner.py`，是实际的协调者，负责：

- 维护 `thread_id -> sandbox_id` 的内存态映射
- 首次访问时创建或发现沙盒
- 重复访问时复用已有沙盒
- `release()` 后放入 warm pool
- 在超时或进程退出时回收资源

它的定位是 **统一入口与资源调度器**。

## 5. 运行模式与部署拓扑

### 5.1 默认模式：本地 Docker 容器

在默认开发环境中，系统拓扑如下：

```text
宿主机
├── Docker Daemon
│   ├── api-dev
│   ├── web-dev
│   └── yuxi-sandbox-<sandbox_id>
└── project workspace

api-dev 容器
└── Yuxi 后端进程
    └── 通过 docker CLI 或 Docker API 管理 yuxi-sandbox-* 容器
```

关键点：

- `api-dev` 不直接执行用户命令
- 用户命令实际运行在独立的 `yuxi-sandbox-*` 容器中
- 后端承担的是控制面职责，而不是执行面职责

### 5.2 远程 provisioner 模式

如果设置了 `YUXI_SANDBOX_PROVISIONER_URL`，provider 会切换为 `RemoteSandboxBackend`。

此时：

- 当前进程不直接创建本地沙盒容器
- 生命周期由远程服务负责
- 本地主路径不再是 Docker 容器管理，而是 HTTP 协调

当前主路径与主要测试覆盖仍以本地容器模式为主。

### 5.3 Docker CLI 与 Docker API 双路径

当前实现支持两种与 Docker 交互的方式：

- 优先使用 Docker CLI
- 当环境中不可用时，回退到 Docker Unix Socket API

这是一种工程兼容设计，目的是提升不同运行环境下的可用性。

## 6. 生命周期模型

### 6.1 线程级资源归属

当前资源归属模型是：

```text
thread_id -> deterministic sandbox_id -> sandbox instance
```

`sandbox_id` 由 `thread_id` 的 SHA256 截断生成。这样做有两个直接收益：

- 同一个线程重复访问时更容易复用沙盒
- provider 重启后可以通过 `discover(sandbox_id)` 找回仍然存活的容器

### 6.2 `acquire()` 逻辑

`provider.acquire(thread_id)` 的核心流程如下：

1. 检查当前线程是否已绑定活跃沙盒
2. 若无，检查 warm pool 中是否存在对应 `sandbox_id`
3. 若无，尝试 `discover(sandbox_id)` 发现已有容器
4. 若仍不存在，则创建新沙盒
5. 将结果注册到 provider 的内存态映射中

这套流程兼顾了：

- 同线程复用
- provider 重建后的容器发现
- 空闲沙盒快速回收后的再利用

### 6.3 `release()` 与 `destroy()`

两者语义不同：

- `release(thread_id)`：解除线程绑定，把实例放入 warm pool，等待后续复用或超时清理
- `destroy(thread_id)`：直接销毁对应实例，不再保留

这一区分是为了兼顾响应速度和资源回收。

### 6.4 空闲回收

provider 内部有空闲检查线程，按固定周期清理：

- 长时间无访问的活跃沙盒
- 已经进入 warm pool 且超时的沙盒

相关默认值定义在 `sandbox_config.py`：

- `DEFAULT_IDLE_TIMEOUT = 600`
- `IDLE_CHECK_INTERVAL = 60`

### 6.5 为什么不再依赖 `/api/sandbox/*`

当前设计不再暴露公开的沙盒生命周期 API，原因很明确：

- 生命周期属于内部资源管理逻辑
- 前端不应承担“先准备沙盒、再访问文件”的协调责任
- 惰性获取可以减少状态同步与接口耦合

因此当前模式是：

- 首次访问文件系统时自动 `acquire()`
- 不再要求前端显式调用沙盒准备接口

## 7. 文件系统模型

### 7.1 虚拟命名空间

当前沙盒对外暴露两个核心命名空间：

- `/mnt/user-data`
- `/mnt/skills`

其中：

- `/mnt/user-data` 是线程私有工作区
- `/mnt/skills` 是可见 Skills 的只读视图

### 7.2 `user-data` 目录结构

每个线程会在宿主机侧创建自己的 `user-data` 根目录，并确保以下子目录存在：

- `workspace`
- `outputs`
- `uploads`
- `large_tool_results`
- `uploads/attachments`

这套目录最终映射到容器内的 `/mnt/user-data/*`。

### 7.3 路径别名

为了兼容 Agent 使用习惯，当前实现保留了若干路径别名，会被统一映射到 `/mnt` 命名空间，例如：

- `/workspace` -> `/mnt/user-data/workspace`
- `/outputs` -> `/mnt/user-data/outputs`
- `/uploads` -> `/mnt/user-data/uploads`
- `/attachments` -> `/mnt/user-data/uploads/attachments`
- `/skills` -> `/mnt/skills`

这些别名是兼容层，不是推荐的长期抽象。新的系统语义应以 `/mnt/*` 为准。

### 7.4 路径安全约束

路径校验主要由 `path_security.py` 负责。核心规则如下：

- 仅允许访问 `/mnt/user-data` 与 `/mnt/skills`
- 禁止路径穿越
- 命令中的绝对路径只允许 `/mnt/*` 与少量系统运行时前缀

允许的系统前缀主要包括：

- `/bin/`
- `/usr/bin/`
- `/usr/local/bin/`
- `/usr/lib/`

这类放行是为了保证容器内基础命令与运行时依赖可用。

### 7.5 输出遮蔽

执行结果在返回前会做宿主机路径遮蔽，避免把宿主机真实路径直接暴露给 Agent 或前端。

这一步不是强安全措施，但它对保持虚拟路径语义一致非常重要。

## 8. Agent 与 Viewer 的双视图设计

### 8.1 为什么需要双视图

当前文件系统接入并不是一套接口复用到底，而是明确拆成两种语义：

- **Agent 视图**
  面向工具调用与 prompt 约束，强调“模型可以怎样访问文件”

- **Viewer 视图**
  面向工作台浏览、读取和下载，强调“用户可以怎样查看文件”

这不是重复建设，而是避免语义错位。

### 8.2 Agent 侧接入

Agent 侧通过 `create_agent_composite_backend(...)` 构建 composite backend：

- 默认 backend 为 sandbox backend
- `/mnt/skills/` 路由到只读的 `SelectedSkillsReadonlyBackend`

这保证了：

- 线程工作区来自沙盒
- Skills 只读且受当前 agent 配置约束

### 8.3 Viewer 侧接入

工作台不再直接复用 Agent backend，而是通过 `viewer_filesystem_service.py` 暴露独立能力：

- `/api/viewer/filesystem/tree`
- `/api/viewer/filesystem/file`
- `/api/viewer/filesystem/download`

它的特点是：

- 只暴露浏览、读取、下载语义
- 根目录视图明确展示 `user-data` 与 `skills`
- Skills 可见范围仍受当前 agent config 约束

### 8.4 旧 `/api/filesystem/*` 的定位

当前仍保留旧的 Agent 文件系统接口：

- `/api/filesystem/ls`
- `/api/filesystem/cat`

它们的定位是：

- 服务于 Agent 语义下的文件浏览
- 使用 composite backend
- 保持与 Agent 可见文件系统一致

因此，不应把它视为工作台浏览器的长期接口。

## 9. Skills 的挂载与可见性

Skills 不是简单的宿主机目录透传，而是受运行时上下文控制的只读视图。

当前模型有两个关键点：

- Skills 物理上以只读挂载方式进入沙盒
- 逻辑上只有当前 agent config 选中的 skills 对 Agent 和 Viewer 可见

这意味着：

- “挂载存在”不等于“对当前线程可见”
- Viewer 与 Agent 必须共享同一套可见性规则

这是当前设计中很重要的一条一致性约束。

## 10. 典型执行流程

### 10.1 Agent 首次访问文件系统

```text
Agent tool call
  -> resolve_sandbox_backend(thread_id)
  -> provider.acquire(thread_id)
  -> create or discover sandbox
  -> build composite backend
  -> execute ls/read/write/command inside sandbox
```

### 10.2 工作台首次打开文件浏览器

```text
Viewer request
  -> /api/viewer/filesystem/tree
  -> verify thread ownership
  -> load runtime context and selected skills
  -> provider.acquire(thread_id)
  -> list sandbox or skills namespace
```

### 10.3 读取与下载文件

读取和下载都遵循同样的原则：

- `user-data` 路径走 sandbox backend
- `skills` 路径走只读 skills backend
- 非 `/mnt` 命名空间路径会被拒绝

## 11. 配置项

沙盒核心配置定义于 `sandbox_config.py`。常用项如下：

| 配置项 | 作用 |
| --- | --- |
| `YUXI_SANDBOX_IMAGE` | 沙盒镜像 |
| `YUXI_SANDBOX_BASE_PORT` | 本地沙盒基础端口 |
| `YUXI_SANDBOX_CONTAINER_PREFIX` | 容器名前缀 |
| `YUXI_SANDBOX_IDLE_TIMEOUT` | 空闲超时时间 |
| `YUXI_SANDBOX_MAX_REPLICAS` | 最大并发沙盒数 |
| `YUXI_SANDBOX_HOST` | 宿主机访问沙盒容器的地址 |
| `YUXI_SANDBOX_PROVISIONER_URL` | 远程 provisioner 地址 |
| `YUXI_SANDBOX_SECURITY_OPTS` | 传递给容器的安全选项 |
| `YUXI_HOST_PROJECT_DIR` | 宿主机项目目录映射辅助配置 |
| `YUXI_DOCKER_API_BASE` | Docker API base URL |
| `YUXI_DOCKER_API_SOCKET` | Docker Unix Socket 路径 |

## 12. 测试与验证

当前与沙盒相关的测试主要覆盖三类问题：

### 12.1 后端与 provider 行为

- `backend/test/test_sandbox_backends.py`

覆盖内容包括：

- composite backend 与 sandbox backend 的接入关系
- provider warm pool 与生命周期逻辑
- remote backend 的基础校验
- 路径规范化与异常输入处理

### 12.2 文件系统接口

- `backend/test/api/test_filesystem_router.py`
- `backend/test/api/test_viewer_filesystem_router.py`

覆盖内容包括：

- Agent 视图与 Viewer 视图接口行为
- 用户权限与线程归属校验
- 目录浏览、文件读取与错误分支

### 12.3 端到端验证

- `backend/test/api/test_sandbox_e2e.py`
- `backend/test/api/test_viewer_filesystem_e2e.py`

覆盖内容包括：

- 真实起沙盒容器
- 在容器内执行命令
- 验证文件写入、读取、附件复制与 viewer 行为

测试中会主动清理 `yuxi-sandbox-*` 容器，这本身也说明当前方案依赖真实容器资源，而不是纯内存 mock。

## 13. 当前限制

### 13.1 安全强度是工程化的，不是强安全承诺

当前实现通过容器隔离、路径约束、命名空间限制来降低风险，但它并不等同于强对抗场景下的高强度沙箱。

### 13.2 Provider 状态未持久化

当前 `YuxiSandboxProvider` 的核心状态保存在进程内存中，例如：

- `_sandboxes`
- `_sandbox_infos`
- `_thread_sandboxes`
- `_warm_pool`

这意味着它更适合当前产品架构，而不是完整的分布式控制面设计。

### 13.3 Viewer 仍以只读为主

当前工作台文件浏览器主要提供：

- 浏览
- 读取
- 下载

它不是完整的文件操作终端，也不是通用文件管理器。

### 13.4 兼容路径仍然存在

`/workspace`、`/uploads`、`/attachments` 等别名仍在使用，这说明路径模型尚处于兼容收敛阶段。

### 13.5 本地容器模式仍有工程折中

例如：

- 依赖 Docker 运行环境
- 兼容 Docker CLI 与 Docker API 双路径
- 依赖本地资源条件与端口可用性

这些都属于工程现实，而不是抽象层面的完美设计。

## 14. 后续演进方向

后续如需继续完善，优先方向应是：

1. **强化控制面**
   将沙盒元数据、生命周期和回收策略从单进程状态进一步抽离。

2. **收敛路径模型**
   逐步减少历史别名，统一到 `/mnt/user-data` 与 `/mnt/skills`。

3. **强化安全边界**
   在容器运行时、权限模型、配额控制和审计能力上继续补强。

4. **继续区分 Agent 视图与用户视图**
   保持两类接口语义清晰，避免再次把 Viewer 语义挤回 Agent backend。

## 15. 总结

Yuxi 当前的沙盒方案，本质上是一套 **线程级容器工作区 + `/mnt` 命名空间 + provider 惰性获取 + Agent/Viewer 双视图接入模型**。

它已经能够较好支撑当前产品中的 Agent 文件工具、工作台文件浏览和 Skills 只读挂载场景，但它依然是 **面向当前业务目标的工程化沙盒**，不是已经完成强安全、强控制面建设的通用沙箱平台。
