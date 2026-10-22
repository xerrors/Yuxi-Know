# Runtime CI 存储身份、独立测试装配与逐 job 构建预算

状态：implemented
类型：bug-fix
Owner：.github/workflows/system-tests.yml

实现位置更新：模型注册现由 `backend/yuxi/infrastructure/postgres/models.py` 拥有，见 [2026-10-21 后端边界收敛](./2026-10-21-backend-boundary-and-provider-catalog.md)。本记录保留当次 CI 证据。

## 问题

Runtime CI 使用全新 bind mount，Docker 创建的目录归 root 所有，UID 1000 的 API 与 worker 无法创建共享 Skill 源目录。冷构建预算检查只匹配任意一个 job，另一 job 缩短或删除预算仍可通过。

独立执行 后台作业 integration selector 时，部分 ORM 关系指向尚未导入的类，查询无法配置 mapper。完整测试收集时其他文件的导入会掩盖该缺陷。

知识统计 integration 仍要求已经退役的历史统计修复路由返回 200，导致当前 404 契约被判为失败。Runtime selector 还引用随旧 Session alias 一起删除的测试文件，pytest 因不存在的路径无法收集。归档与 lease 用例仍创建父子共享 Turn/runtime 的旧数据，并从 runner 调用已经移入 leases 的 reconciler。CORS 测试把显式空配置当作 Origin，Redis 用例仍依赖已经退役的事件封套与 key。环境准备还把仅支持 OpenAI 的 replay 配成 Langfuse，等待恢复 E2E 回读观察时收到 404。Workdir 用例使用不受支持的 UUID 目录名，文件边界按当前托管格式拒绝。

## 决策

### 实现方案

两个 Runtime job 在构建镜像后、启动服务前，使用一次性的 root API 容器把三个测试存储根目录设置为 UID/GID 1000、模式 0700。API、worker 和 schema-init 保持原有运行身份与权限。准备只作用于 CI 的隔离目录，无递归迁移或生产目录修改。

`scripts/test_release_workflows.py` 按顶层 job 分别检查至少 60 分钟的预算；负向测试逐个缩短或删除预算。Runtime workflow 以 readiness、HTTP、数据库与 worker 链路形成运行后果。

`backend/test/integration/conftest.py` 在 session fixture 中调用现有 `bootstrap.models.load_models`，为独立测试进程显式注册全部 ORM；fixture 不连接服务、不建表，实际 Schema 与连接仍由原 fixture 和迁移入口拥有。单个文件和完整 integration 使用相同的模型装配。

知识统计 integration 保留当前刷新与行锁回归，把退役修复路由用例改为真实 HTTP 404 与 PostgreSQL/Redis 无写入的负向契约。当前统计继续由现有刷新流程产生。Runtime workflow 与信任检查同步移除已删除的 alias 测试引用，保留当前认证、Key、Input、归档与 Redis 边界检查及其逐项删除负控。归档与 lease integration 按[现有子任务决策](2026-09-30-langgraph-agents-events.md)创建独立子 Turn/runtime，验证父失败不取消子任务、父 Thread 可独立归档而 Project 在子任务活跃时拒绝删除；lease 回归直接调用当前 leases Owner。CORS 用例使用当前开发默认 Origin 或显式配置；Redis 用例回读 v2 key、版本字段和完整公开事件，不恢复旧封套。CI 移除伪 Langfuse 凭据与地址；取消 E2E 无条件验证请求时间、数据库审计与终态，trace 断言与等待恢复中的 Langfuse 观察回读都只在配置真实服务时执行。Workdir fixture 使用现行时间戳加8位标识格式，并准确声明自身的 SQLite/真实目录证据范围。

## 替代方案

- CI 全程使用 root：会跳过 shipping 身份的真实文件权限语义，不采用。
- 恢复运行时 chmod 或把目录设为所有人可写：把部署准备带入业务边界，扩大访问范围，不采用。
- 仅延长一个 job：无法拒绝其他 job 的预算回退，不采用。
- 在 后台作业 测试中补一个 `AgentEnv` import：只覆盖当前首个错误关系，仍依赖导入顺序；选择现有完整模型装配入口。
- 恢复历史统计修复端点或跳过用例：前者重新承诺已删除能力，后者丢失删除的拒绝后果；采用当前不存在且无副作用的 HTTP 契约。

## 后果

默认 Runtime CI 验证完整核心 worker 链路，不宣称验证可选 Langfuse 导出。配置真实 Langfuse 时仍执行原有观察回读与 trace 断言；没有真实服务的本轮验证明确记录此范围未验证。

目录准备命令仅供隔离 CI 环境使用，会修改指定根目录的 Owner 与模式。它不提供已有部署的数据迁移，也不修改生产入口。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| UID 1000 可写三个 CI 存储根目录 | 目录归 root，启动失败 | Runtime workflow 的准备步骤 | 同一 Compose 镜像以 UID 1000 写文件并回读；Runtime CI | 未准备目录时同一写入因 PermissionError 失败 | Passed |
| 每个 Runtime job 预算至少 60 分钟 | 一个正确 job 掩盖另一个短预算 | release workflow 单测 | `python3 -m unittest scripts.test_release_workflows` | 逐个缩短或删除预算 | Passed |
| 后台作业 selector 独立执行可配置 ORM | 缺少关系目标模型 | integration session fixture、bootstrap models | 独立进程执行 `pytest test/integration/services/test_durable_task_repository.py` | 未装配时16项因 AgentEnv mapper 缺失失败 | Passed |
| 退役统计修复入口无可调用能力 | 旧路由被恢复或写入统计 | knowledge 路由与统计 integration | 真实 HTTP 404、PostgreSQL/Redis 回读 | 注册可匹配旧 URL 的路由返回 200，测试应失败 | Passed |
| MCP PR 的真实运行链路通过 | startup gate 掩盖业务回归 | Runtime workflow、MCP service/runtime | 真实 HTTP/PostgreSQL MCP integration；完整 Runtime CI 在 PR 中记录 | 非法配置不落库，stdio 无文件副作用 | Passed |

- 同一 Compose API 镜像以 UID 1000 在未准备的空目录创建 `shared` 因 PermissionError 失败；执行 workflow 的准备命令后，三根目录 Owner/模式均为 1000/0700，独立文件写入与内容回读通过。
- 隔离 Compose 的 API/worker readiness 通过；真实 MCP HTTP、Schema 和 stdio E2E 回归 31 passed。复用现有镜像，GitHub 冷构建与完整 Runtime CI 在 PR 中另记实际结果。
- release workflow 6 项、工程契约和信任 64 项通过；前端 lint、432 项 unit、生产 build 与文档 build 通过。

- 同一独立 `uv run --no-sync --no-dev pytest test/integration/services/test_durable_task_repository.py -q --tb=short` 进程：缺少模型装配时16 failed/1 passed，加入完整模型装配后17 passed；原有测试回读 PostgreSQL 的 claim、lease 与终态，不以 mapper 配置完成替代行为证据。

- 独立 后台作业 worker 链路：停止隔离 API/worker 后，`test_prepare_task_with_failed_initial_arq_publication` 1 passed；重新启动真实 worker 后，`test_shipping_worker_startup_recovers_pending_publication` 与 `test_shipping_worker_failure_runs_domain_hook` 2 passed，回读 Task 与领域终态。

- 独立 `pytest test/integration/services/test_knowledge_stats_refresh.py -q --tb=short`：4 passed。仅在新测试进程中临时注册旧路径返回 200，退役路由回归因 `200 != 404` 失败；源码路由未改动，PostgreSQL/Redis 回读断言保留。

- 归档与 lease 在真实 PostgreSQL 上共 12 passed；旧数据分别因 runtime scope 的 CHECK、Turn/Thread 组合外键失败，旧 reconciler 路径因 AttributeError 失败。修复不改变生产约束或生命周期实现。

- 移除伪 Langfuse 配置后，真实 API/worker 的核心生命周期 E2E 13 passed；等待恢复与模型取消仍回读 PostgreSQL 终态、审计和输出。可选 Langfuse 导出未验证。环境脚本在临时目录运行时正确保留包含特殊字符的三个测试 secret，且不配置 Langfuse；临时加回旧配置会被检测为错误配置。

- 主 Runtime 剩余 selector 按 workflow 分组独立执行：确定性真实 worker E2E 32 passed（核心13、扩展4、子任务11、Key作用域1、公开事件3）；identity/secret19 passed；Workdir/Skill3 passed（Workdir为SQLite与真实目录，Skill为PG/HTTP）；真实Sandbox隔离6 passed。完整最终SHA的GitHub结果在PR另记，不以本地预检代替冷构建门禁。
