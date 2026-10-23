# 沙盒运行环境入口与清理责任收敛

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/services/run_lifecycle.py

## 问题

每 Run 容器同时使用持久 runtime cleanup 与终态尽力释放，yielded 不登记清理责任，接续 Run 可能先于旧环境清理开始执行。公共 provider 入口混合 Cube 实现，runner 存在无生产调用者的显式创建协议，镜像与 TTL 策略由多个进程重复解释。

## 决策

### 实现方案

所有 Run 终态（包括 yielded）登记现有 `runtime_cleanup_pending`，统一调用 provider 的 `cleanup_run`，确认成功后才清除责任。Cube 释放所属命令而保留用户 VM，container 删除所属 Run 容器。checkpoint 提交后先完成旧 Run 清理再投递 steer 接续；repository 的领取边界拒绝同 Thread 尚有清理责任的首次执行，覆盖补投提前到达的窗口。恢复沿用现有 pending Run 补投和 cleanup reconciliation，不增加表、状态或队列。

sandbox 的 provider 文件只拥有配置选择、工厂和健康入口，Cube 生命周期迁入模块内实现文件；外部消费者通过模块公共入口访问 provider、Backend 和可信上下文。保留每 Run 一个容器、当前挂载范围和管理能力限制，不引入新的短期执行作用域或能力框架。

runner 仅在 execute 内创建容器，删除显式创建 HTTP/client 协议及 include_skills 开关。镜像和资源配置由 runner 校验；业务进程只校验调用所需配置。业务 provider 对账 Run/owner/lease，最大容器寿命只由 runner 拥有。

runner 在每 Run 创建/删除锁内，使用既有 `SandboxRepository.run_owner` 只读 PostgreSQL 的 uid、状态、owner、lease 与 cleanup 标记，拒绝迟到的旧执行请求。查询不取得 PG 行锁，避免与持 Run 行锁等待删除的清理流程互等；业务 provider 不再重复校验，runner 不写业务表，也不保存独立准入状态。

## 替代方案

- 保留双重清理：重复副作用且 yielded 缺少持久责任，不采用。
- 引入通用执行会话或持久容器：增加状态及消费者迁移，超出基本命令执行需求。
- 每命令创建容器：失去同 Run 的临时 Home 和连续执行语义，不采用。
- 合并 API/worker 与 runner：扩大 Docker socket 边界，不采用。
- runner 保存已清理 Run 黑名单：需要过期、恢复和跨进程身份机制；直接读取现有 PostgreSQL 事实更小且可跨 runner 重启。

## 后果

yielded 在清理失败时保持新 Run pending，恢复延迟受已有周期补投影响。Cube 的用户环境和 container 的 Run 环境继续各自管理，业务生命周期不依赖后端类型。未新增表、状态、队列或依赖；runner 复用部署已有的 PostgreSQL 连接配置，增加只读准入依赖。容器的 Workdir 范围及无 Run 管理能力限制保持不变。

本决定部分取代 [container 后端决策](2026-10-22-container-sandbox-backend.md) 的双重清理与业务进程镜像校验；部署 scope、命令取消和不可变容器 ID 清理仍遵循[清理边界决策](2026-10-23-container-sandbox-cleanup-boundaries.md)。

## 验证

- 迟到请求四项真实 Docker 负控在修复前均失败；把 runner 校验临时移至创建锁外时，`test_run_owner_is_read_after_acquiring_creation_lock` 因旧快照仍被接受而失败，恢复锁内查询后通过。
- 负向测试在原实现执行：`test_thread_priority_inputs.py -k 'safe_handoff or successor_waits'` 两项分别因 yielded 缺少清理责任、提前领取成功而失败；修复后通过。
- 隔离 container Compose API 中执行 `uv run --no-sync --group test pytest test/integration/services/test_thread_priority_inputs.py test/integration/services/test_agent_run_lease.py test/integration/services/test_agent_stop_recovery.py -q --tb=short`：49 passed。真实 PostgreSQL 回读清理失败保留责任、接续 pending、重复清理及恢复后领取。
- 宿主执行 `SANDBOX_CONTAINER_TEST=1 SANDBOX_CONTAINER_IMAGE=yuxi-sandbox:container-e2e backend/.venv/bin/python -m pytest backend/test/integration/sandbox/test_container_sandbox.py -q --tb=short`：20 passed，包含认证 HTTP 懒创建、旧显式创建路径返回 404、跨部署与 attempt 隔离、超时及取消，以及创建前排队的旧请求在 yielded、pending、取消中和新 owner 下均无法复活容器。Docker 专项替代 PostgreSQL 查询结果；真实数据库接线由完整 E2E 验证。
- 对隔离栈提供临时测试账号、API 地址和 PostgreSQL URL，执行 `backend/.venv/bin/python -m pytest backend/test/e2e/test_container_agent_execution_e2e.py -q --tb=short`：2 passed。普通完成与 steer 接续均通过真实 API/worker/runner；Viewer 文件中的容器 hostname 证明接续更换环境且 Workdir 保留，数据库回读 yielded/completed、接续因果、结果 Run 和清理标记，状态接口回读 Docker 无活动容器。
- 隔离 Compose API 中执行 `uv run --no-sync --group test pytest test/unit -m 'not slow' -q --tb=short`：3033 passed、101 skipped；配置测试需仓库根文件，宿主补跑 `backend/.venv/bin/python -m pytest backend/test/unit/config -q --tb=short`：166 passed。
- 工程契约检查及其 66 项 unittest、后端 Ruff lint/format/import 检查、变更 Markdown 相对链接检查、docs build 和 `git diff --check` 均通过。
- 本轮验证拓扑为隔离 container 栈，未运行真实 Cube VM E2E；Cube provider 单测、共享生命周期 PostgreSQL 回归与完整 unit 覆盖入口迁移及清理契约，真实 VM 外部协议验证仍有缺口。

旧能力不存在：生产源码中无 `release_on_terminal`、`release_run`、显式创建路由及 `include_skills` 开关；API/worker Compose 环境不再消费容器镜像及 TTL 配置。

重新引入条件：出现真实外部创建消费者或新的非 Run 执行需求时独立设计；不能为测试方便恢复生产协议。
