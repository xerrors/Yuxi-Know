# Agent 停止收尾与用户恢复队列

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/agents/services/turns.py

## 问题

运行中取消的 Run 完成清理后，Turn 仍依赖周期补偿结束。取消和失败无条件暂停空队列，之后的用户消息只能入队。整任务超时与 worker 退出共用取消处理，可能释放为 pending 并被重复投递。

## 决策

### 实现方案

Turn service 拥有取消完成判断，正常 runtime 清理和恢复扫描共用该判断；只有当前 Run 已停止、必要清理完成后才结束 Turn。等待取消在同一 Thread/Turn 锁内复查、清理 checkpoint 并提交终态，阻止迟到清理改写下一轮 checkpoint。Input repository 提供待办存在性查询，queue_control 在调用方事务中派生暂停，取消、失败和整树停止仅暂停已有待办；删除最后一条待办后清除暂停。暂停派生与恢复标记的当前归属见[用例职责决定](2026-10-21-architecture-convergence.md#队列暂停与恢复)。scheduler 在前轮清理未完成时阻止新轮执行。

用户消息接收事务在 Thread 锁内保存恢复触发输入的持久标记，并解除该队列暂停；调度器优先单独消费这条消息，附件未就绪时不越过它。恢复 Turn 从已消费 Input 的接收序号派生引导边界，旧 steer 等待本轮完成，之后新提交的 steer 仍可接管。成功后沿用原调度规则处理旧队列，再次失败或取消时暂停剩余待办。幂等重放、协作和定时输入不产生新的恢复意图。

整树停止在同一事务中按序锁定成员、暂停已有队列并保存门禁，再请求各成员取消和执行等待清理；用户恢复早于扫描时其他成员队列也已暂停。用户在整树停止后发消息，必须等待全树取消完成，解除整树门禁但仅恢复目标会话的队列，其他成员的旧待办保持暂停。runner 使用现有执行时限识别整任务超时并持久失败，ARQ 保留外层清理余量；worker 退出沿用原有恢复语义。失败与迟到的取消竞争时，原 owner 确认持久取消并完成收尾。Turn 详情的 `cancellation_pending` 从持久取消状态派生，前端据此重连和核对请求异常；本地停止等待只属于同一 Turn，迟到等待快照不撤销请求等待。

## 替代方案

缩短扫描周期会保留正常路径缺失的结束动作。取消一律不暂停队列会违背用户停止已有待办的意图。直接解暂停会先运行旧队头；复用 steer 会把新消息与旧引导合批。重做 Input/Turn/Run 状态模型超过当前问题需要。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 正常取消清理后直接结束 Turn | 补偿扫描掩盖缺失步骤 | turns / leases | PostgreSQL integration、worker E2E | 不运行扫描仍结束；等待取消先确认外部清理，checkpoint 改写期间其他 Thread writer 的 NOWAIT 取锁被拒绝 | Passed |
| 空队列不留暂停，有待办则保留 | 无条件暂停导致后续消息滞留 | input / runs / threads | PostgreSQL integration | 空、有待办及删除末条 | Passed |
| 新用户输入独立优先，旧队列顺序保留 | 旧 steer 抢先、附件或重试丢顺序 | inputs / scheduler | HTTP integration、E2E | 新消息 completed 后旧 steer 才开新轮，重放不再次恢复 | Passed |
| 超时有终态且基础设施退出可恢复 | 超时回到 pending 反复执行 | runner / worker settings | runner unit、真实 ARQ / PG integration | 阻塞执行触发短时限、迟到取消仍收敛 | Passed |
| 停止整树不被单会话恢复唤醒旧子任务 | 整树门禁或恢复范围错误 | cooperation | PostgreSQL integration、E2E | 扫描尚未开始时用户恢复，旧子任务仍 pending 且不能领取 | Passed |
| 等待取消可断线恢复，停止状态仅属于目标轮次 | Run interrupted 无法表达取消、旧快照或异常覆盖已确认状态 | Turn HTTP / run stream | 真实 HTTP / PostgreSQL、前端 unit、浏览器协议 fixture | 等待取消快照、迟到等待事件、跨轮恢复及请求响应丢失 | Passed |

相关集成命令 `docker compose exec -T api uv run --group test pytest test/integration/services/test_agent_stop_recovery.py test/integration/services/test_thread_priority_inputs.py test/integration/services/test_agent_input_concurrency.py test/integration/services/test_agent_run_lease.py test/integration/services/test_session_cooperation.py -q` 通过 117 项。整树暂停窗口和 checkpoint 清理缺锁分别先因旧子任务被领取、NOWAIT 未拒绝而失败，等待取消 HTTP 用例先因缺少停止事实失败。超时用例使用独占 Redis 队列、真实 YuxiWorker 和 PostgreSQL，以受控执行流替代模型及外部环境准备；取消、失败、等待取消与旧 steer 恢复由真实 HTTP / worker E2E 补充。

生命周期 E2E selector `test/e2e/test_agent_lifecycle_e2e.py -k 'cancel_running_model or cancel_waiting_turn or model_rate_limit_failure' -q` 通过 4 项，`test/e2e/test_session_cooperation_e2e.py::test_full_tree_capacity_control_and_sibling_tools[True] -q` 通过 1 项。通过 `docker compose exec -T api uv run --group test python -` 的临时账号装配调用 pytest，模型重放地址设为 Compose API 的 8765 / 8766 端口；账号绑定当前测试管理员的部门并在测试后删除。原共享测试账号因历史项目目录重叠被清理器拒绝，没有删除或改写这些历史目录。

后端全量 `docker compose exec -T api uv run --group test pytest test/unit -m 'not slow' -q` 通过 2720 项、跳过 62 项；宿主 `uv run --project backend --no-sync --group test pytest backend/test/unit/config -q` 通过 104 项，补齐容器缺仓库根目录的配置验证。前端事件及人工等待可见性测试、全量 unit、lint、build 和真实页面协议 fixture 检查覆盖停止反馈、重复点击、暂停提示及明暗主题。外部真实模型故障和长时限耗尽未探测，业务超时采用短时限受控用例验证。

## 后果

取消完成、队列恢复与新提交需遵守 Thread→Turn/Input→Run 的锁序；副作用仍须确认清理。恢复标记随 Input 持久化，避免附件准备、响应丢失和进程退出改变执行顺序。公开消息优先恢复行为需要同步更新现有协议说明和回归预期。
