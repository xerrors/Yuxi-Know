# 收敛 Run 终态与清理职责

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/services/run_lifecycle.py

## 问题

Run 完成、checkpoint 输出、失败和失联恢复分别准备 Thread、Turn、Input 与 Run 锁，测试还复制一份准备逻辑。终态写入已经共享，但调用方仍需自行维护锁序和 steer 裁决；取消清理在 turns 与 leases 之间通过惰性导入互相调用，事务及清理责任分散。

## 决策

### 实现方案

本决定沿用[Agent 事务与生命周期的共同契约](2026-10-12-agent-transaction-lifecycle.md)中的用例提交、消息归属与通知时序，并将终态锁准备与清理职责收敛到共同 Owner。

`services/run_lifecycle.py` 统一拥有 Thread→Turn→Input→Run 的结算锁序、steer 裁决及 Run/Turn 终态投影。checkpoint 消息用例先取得该事务边界，在同一事务对账输出并结算；runner 使用生产结算入口，失联恢复复用相同锁准备，并由 repository 在 Run 锁下独立判断 lease 是否过期。测试直接调用生产入口，独立回读数据库事实。

checkpoint、runner 与 lease 恢复用例继续拥有各自提交与发布时序：输出和终态同事务提交，提交后投递 steer 接续 Run，命令清理成功后发布终态。正常执行、终态重投和 cleanup 恢复共用清理及派发/observation 边界；终态重投只在补偿 pending cleanup 时重发终态，清理后重读新快照再派发。

生命周期 Owner 同时拥有命令清理、等待 checkpoint 清理和 cancelling 补偿。命令清理持有 Run 锁直到外部命令确认停止，退出该事务后才取得 Thread/Turn 锁结束取消；等待取消持有 Thread/Turn 锁完成 checkpoint 清理，防止新轮与迟到清理交叉。`turns` 保留取消接收、恢复和查询，`leases` 保留领取、续租及恢复扫描；生命周期层不反向依赖这两个模块。

Run 的 interrupted、yielded 仍是执行段终态，所属 Turn 继续等待或运行。取消 Run 必须完成持久 cleanup 后才结束 cancelling Turn。queue pause、指定 Turn 取消和后代独立工作、attempt/audit fencing 及失联的可观察失败继续由原有 repository 约束和各阶段维护。公开协议、状态词表和持久 schema 保持现有契约。

## 替代方案

- keep：保留分散锁准备与清理调用，继续承担当下重复维护和环依赖。
- narrow：仅提取锁 helper，无法消除 turns/leases 环和测试专属结算入口。
- replace：采用聚焦 lifecycle Owner，复用 repository 状态转换；事务内准备结果只保存已锁对象，不建立独立状态机或阶段配置。
- remove：删除 cleanup 或失联专属阶段会使外部命令或等待 checkpoint 失去可恢复的 Owner，不能接受。

## 后果

调用方不再复制终态锁序；输出持久化仍在 repository 验证当前有效 lease。不同阶段保留明确入口和提交点，发布触发条件由真实用例维护。runtime_cleanup_pending 继续属于 PostgreSQL，清理失败可重试且可观察；外部副作用仍按 at-least-once 语义核对。

## 验证

测试在隔离 PostgreSQL/Redis 和独立 Compose 槽位执行；E2E 使用真实 API、worker、持久化、SSE 与 Cube，通过 deterministic replay 提供模型响应，并回读 Turn/Run/Input、消息、等待点和产物。

| 观察边界 | 直接证据 | 结果 |
|---|---|---|
| 生命周期事务、归属与锁序 | `test_run_lifecycle.py` 验证跨连接提交前仍为 running、调用方 rollback、错误 Thread/Turn、错误 worker，以及持有 Input 时 Run NOWAIT 仍可取得 | Passed：5 项 |
| lease、checkpoint、steer、FIFO、取消恢复与协作 | 下列九文件 PostgreSQL integration，独立回读最终状态、attempt/audit 与 cleanup | Passed：131 项 |
| shipping 生命周期及协作 | 下列三文件 Compose E2E，包含完成、运行与等待取消、steer、恢复、失败、审批和协作 | Passed：30 项，无 skip |
| 重投与提交后收尾 | runner 单测证明 pending cleanup 才发布、清理后新快照派发，以及 cleanup→publish→dispatch→trace 顺序 | Passed：相关 unit；host 完整 unit 3039 项 |
| E2E 收尾事实 | 独立 PostgreSQL 回读 nonterminal_runs、cleanup_pending_runs、cancelling_turns、active_turns | Passed：四项均为 0 |
| 仓库与文档 | 工程契约、66 项 verifier unit、全部 18 个变更 Python 文件 Ruff check/format、docs build、diff check | Passed |

PostgreSQL integration 的实际命令（测试进程预先配置隔离连接）：

```bash
uv run --project backend --no-sync --group test pytest \
  backend/test/integration/services/test_run_lifecycle.py \
  backend/test/integration/services/test_agent_run_lease.py \
  backend/test/integration/services/test_agent_run_manifest_and_attempts.py \
  backend/test/integration/services/test_thread_priority_inputs.py \
  backend/test/integration/services/test_session_cooperation.py \
  backend/test/integration/services/test_agent_stop_recovery.py \
  backend/test/integration/services/test_agent_input_concurrency.py \
  backend/test/integration/services/test_checkpoint_concurrency.py \
  backend/test/integration/services/test_steer_checkpoint_boundary.py -q --tb=short -ra
```

Compose E2E 的实际命令（Compose 已指向独立槽位，测试凭据由环境注入）：

```bash
docker compose exec -T -e E2E_USERNAME api uv run --no-sync --no-dev pytest \
  test/e2e/test_agent_lifecycle_e2e.py \
  test/e2e/test_agent_lifecycle_extended_e2e.py \
  test/e2e/test_session_cooperation_e2e.py -q --tb=short -ra
```

负控通过仅在测试子进程内恢复缺陷验证：将 Run 锁提前到 Input 前，锁序测试因 Run NOWAIT 的 PostgreSQL 55P03 失败；分别移除错误 Thread/Turn 检查，对应案例因未拒绝错误归属失败。磁盘源码和运行服务保持原实现。

容器标准 `uv run --group test pytest test/unit -m "not slow"` 在依赖同步阶段因镜像内 yuxi.egg-info 不可写失败；复用已安装依赖的 `--no-sync --group test` 运行结果为 2940 passed、99 skipped。99 项因容器缺少仓库根部署文件跳过，由 host 完整 3039 项 unit 覆盖；标准同步命令不计通过。PG 的 fixture rewrite warning 与 E2E 的 pytest cache 权限 warning 不影响断言。真实 provider 探针未执行，deterministic replay 证明当前装配路径，未验证外部模型服务漂移。

旧能力不存在：生产与测试中已删除 settle_locked_run、各调用方重复终态锁准备和 turns↔leases 惰性导入环；负向符号搜索和完整 diff Review 均核对。独立 Reviewer 核对源码、测试、锁顺序、提交点和实际结果。

重新引入条件：只有新的实际消费者需要独立生命周期边界，且具备事务、锁与清理的直接证据时重新裁决。
