# 用户工作区固定路径与沙盒遗留清理

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/workspace/runtime_paths.py

## 问题

Cube 用户环境仍以历史根挂载工作区，再把普通用户的 workspace 变成别名。文件工具接受别名而产物协议拒绝它，提示词、客户端和部署配置继续传播不同路径。旧线程沙盒身份、回收字段、checkpoint 对象兼容及 Docker 沙盒资源采样也未随用户 VM 生命周期收敛。

## 决策

### 实现方案

Workspace runtime 路径固定为 `/home/user/workspace`，共享 Skill 投影固定为只读 `/home/user/skills`，个人 Skill 位于工作区 `agents/skills`。provider 直接挂载固定根；模板、文件路由、附件与产物、模型提示和客户端使用同一契约，删除前缀环境配置与路径别名。旧路径不转换、不回退。宿主文件布局保持由 Workspace Owner 管理。

用户 VM 只按 uid 标识，文件工具不再接收沙盒 Thread 身份或回退到 checkpoint Thread。协作树仍拥有执行名额和停止状态，删除其已无消费者的空闲及释放字段，business Schema 提升为版本 2，knowledge 保持版本 1，API、worker 和初始化器在产生业务写入前明确拒绝旧版本；不回填或自动迁移。产物 state 与 wire 只传字符串路径，前端明确构建展示模型。删除 Docker 沙盒采样与废弃部署文档；ToolCall 双投影保留。

本记录取代[协作维护](./2026-10-06-cooperation-runtime-lifecycle.md)和[任务观察](./2026-10-07-cooperation-task-observation.md)中的线程沙盒身份、空闲回收与销毁重建部分；原记录的 Session 锁序、任务观察与成员可见性决定继续适用。

## 替代方案

- 保留旧根和别名：继续产生两套文件协议，拒绝。
- 只改默认前缀：保留任意前缀配置和下游硬编码，不满足固定根及删除兼容的要求，拒绝。
- 增加长期旧路径转换：重新制造兼容表面，拒绝。
- 统一固定根并删除无消费者分支：采用。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 新 VM 直接挂载固定 Workspace 与只读共享 Skills | 仍生成旧挂载或符号链接 | runtime_paths / provider / Cube 模板 | 路径 unit、真实 Cube integration（2 passed）与宿主字节回读 | 旧根不被路由或登记为产物；旧配置不能改变根 | Passed |
| 文件、附件、产物、Skills 与客户端使用同一根 | 新路径可写不可下载 | Workspace / Agent services / frontend | 后端 unit、共享 Skill HTTP、Cube E2E、前端 unit/lint/build 与 Demo 浏览器检查 | 旧路径读取及旧对象格式拒绝 | Passed |
| 无效身份、回收字段与旧资源采样被删除 | 兼容分支继续被生产调用 | sandbox Backend / cooperation / performance | 调用搜索、真实 PostgreSQL schema/协作（72 passed）、压测 unit、工程契约 | 不再接受沙盒 thread_id 或旧 Docker 参数 | Passed |

旧能力不存在：当前代码、配置、测试正向 fixture 与当前文档不提供旧路径别名、任意虚拟根、旧产物对象及 Docker 沙盒资源采集；历史归档和负向测试可以记录被删除的行为。

重新引入条件：存在明确用户需求与独立决策及证据，不通过静默兼容恢复。

## 后果

旧 VM 挂载、旧附件路径和旧 checkpoint 不兼容；本变更不操作现有用户数据或自动重建环境。部署者使用符合当前基线的数据与新建环境，保留资料需离线备份并显式处理。删除协作字段改变新库模型；旧 business 版本 1 会被当前版本校验拒绝，代码不在运行时改表。真实验证只创建并清理自己的测试资源。

本次真实验证在独立空 PostgreSQL 数据库、独立 Redis 与临时 API/worker 中执行，未重启现有服务或改写用户库。数据库由当前初始化入口从空库建立，回读 `session_cooperation_runtimes` 只含树 ID 与 `stopped`。

- `python -m pytest /app/test/integration/services/test_schema_migration_version.py /app/test/integration/services/test_session_cooperation.py -q -p no:cacheprovider`：72 passed。恢复旧版本 1 和旧回收列的负控在修复前因未拒绝而失败，修复后 API/worker 共用检查与初始化器都拒绝。
- `python -m pytest /app/test/integration/sandbox/test_cube_user_environment.py -k 'concurrent_first_use or shared_workspace_skills' -q -p no:cacheprovider`：2 passed，核对直接挂载、普通用户、只读投影、暂停恢复和重建后字节。
- `python -m pytest /app/test/e2e/test_cube_agent_execution_e2e.py -q -p no:cacheprovider`：1 passed，核对真实并发取消、崩溃恢复、字符串产物登记、新根下载字节和旧根 403。
- `python -m pytest /app/test/integration/api/test_skill_artifact_authorization.py -q -p no:cacheprovider`：1 passed，撤权提交后新根上的原 URL 被拒绝，仍授权用户可读。
- `docker compose exec -T api uv run --group test pytest test/unit -m 'not slow' -q -p no:cacheprovider`：2632 passed、59 skipped；跳过项为容器未挂载仓库根目录的既有配置检查。Schema 版本及适配器随后相关 unit 50 passed。
- 前端完整 unit 620 passed，lint 与 build 通过；Demo unit 13 passed，lint/build 与下载浏览器测试 2 passed。

首次隔离库协作测试 56 项行为通过，但缺有效管理员前置导致清理最后管理员被真实约束拒绝；补齐专用测试管理员后完整集合通过。旧路径固定根负控修复前 3 failed，修复后通过。历史测试结果只证明各自版本，当前验收以本记录的观察边界为准。

补充验证：正式附件跨 Backend 实例及公开 HTTP 字节链路 1 passed。实际 Vue 组件浏览器检查确认字符串产物渲染与 `~/projects/...` 路径缩写，浅色和深色截图使用合成文件名，不含用户数据。额外旧 E2E 的首次执行因隔离重放子进程缺少模块搜索路径而失败；修正测试环境并通过真实取消链路收敛残留后，附件场景复验通过。

最终复验：`python -m pytest /app/test/e2e/test_session_cooperation_e2e.py::test_sessions_use_public_state_and_shared_sandbox -q -x -p no:cacheprovider`：5 passed；正式附件 E2E 1 passed。最终工作区后端完整非慢速 unit 2648 passed、59 skipped；前端完整 unit 620 passed。工程契约、自测 65 项、生产 Ruff、文档构建及 diff 检查通过。独立 Reviewer 指出的版本拒绝、旧 E2E 调用、授权 fixture 与决策取代关系均已修正并复验。

Run 清理在同一 Run 行锁内复核持久责任、等待外部命令结束并清除标志；取消清理协程也持锁直到外部动作完成，迟到候选不能清理新 attempt。Guest grep/glob 在有界结果中明确返回截断信号。以下补充验证使用独立 PostgreSQL 数据库与测试自己的 Cube VM：

- `python -m pytest /app/test/integration/services/test_agent_run_lease.py --confcutdir=/app/test/integration/services -k cancelled_cleanup -q -p no:cacheprovider`：1 passed，回读实际 PG 锁冲突 SQLSTATE 55P03、新 attempt Owner 与命令存活文件。
- `python -m pytest /app/test/integration/sandbox/test_cube_runtime_toolchain.py --confcutdir=/app/test/integration/sandbox -k partial_results -q -p no:cacheprovider`：1 passed，真实 Home 文件的部分与完整搜索结果。
- 上述清理与 Guest 搜索 unit 的负控在修复前为 3 failed、11 passed，修复后 14 passed；全后端复验 2648 passed、59 skipped。
- Bash 镜像导出脚本通过 `bash -n` 与替身 Docker 完整执行，验证 14 个基础镜像和 Compose MinIO 镜像参数并回读归档；真实全量镜像下载/导出及 PowerShell 执行未运行。
