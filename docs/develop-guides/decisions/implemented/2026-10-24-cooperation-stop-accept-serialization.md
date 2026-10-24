# 协作工具副作用与来源执行身份在持久边界串行化

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/agents/services/cooperation.py

## 问题

`submit_input`/`create_session` 只在工具入口（`caller()`）检查整树停止状态，真正持久写入 Input 前不再裁决。停止扫描若发生在入口检查与写入之间，迟到的提交会进入一个未暂停的成员队列；取消清理结束后用户仅向主会话发新消息恢复时，这份旧子任务可能被消费并创建新 Run。复现结果：停止后 Input 仍 `pending`、成员 `queue_paused=False`，恢复主会话后旧 Input 被消费。

仅在工具入口检查来源 Run 的状态和租约也不足以授权副作用。工具等待数据库锁期间，同一 Run 可以取消或释放 retry 租约并被新 attempt 领取；若写入前只刷新而不持锁，后续 await 又会暴露同一个竞争窗口。提交工作、投递协作消息和取消目标 Turn 都必须把来源执行身份保护到副作用提交。

整树停止意图是共享工作目录的执行屏障。Turn 终态只证明业务结算，不证明旧 Run 的命令与环境已释放；整树“继续”若只查询活动 Turn，就会在另一成员仍承担运行时清理责任时消费旧队列并启动新执行。用户新消息与显式继续分别维护可恢复判断，也会使同一停止状态出现两个不同的安全边界。

## 决策

### 实现方案

两个清除整树停止意图的入口共用一项恢复前置条件：授权整树没有活动 Turn、非终态 Run 或尚未完成的运行时清理。查询归 `CooperationRepository`，service 在已持有 Session → 树锁的事务内统一拒绝；尚未消费的 Input 是被恢复的工作，不属于阻止恢复的执行责任。显式继续恢复全部成员队列，用户新消息仅恢复目标会话队列，两者保留各自现有用户语义。幂等回执重放先于该前置条件，只返回已接受事实，不清除后来再次生效的停止意图。

`_accept` 在领取目标 Session 行锁（`lock_session_by_thread_id`）之后、写入 Input 之前，重读 `CooperationRuntime.stopped`（`populate_existing` 避免会话缓存）并拒绝迟到提交（`StateConflictError`）。它同时以 `FOR NO KEY UPDATE` 锁定并刷新来源 Run，持锁直至 Input 与 Receipt 提交，要求仍在运行、租约有效且 `worker_id` 与工具执行上下文中的 attempt Owner 相同，避免整树停止清理后被用户恢复时，旧异步工具调用随 `stopped=False` 重新获得写入资格，也避免同一 Run retry 后旧工具借用新 attempt 的租约。

整树停止（`control_tree`）以 `FOR NO KEY UPDATE` 锁定全部成员行后才提交停止意图，因此接收方持有同一行锁即可与停止提交串行化：要么停止先提交、接收在写入边界看到 `stopped=True` 被拒绝；要么接收先提交、停止扫描随后取消该成员的活动 Turn 并保留队列暂停。接收不另加树锁，继续遵守 Session → 树通知锁的顺序。停止与来源 Run 检查位于幂等 receipt 重放之前，失效来源不再返回旧回执，但不会制造第二次副作用。

`create_session` 的串行化依赖其事务持有的调用方行锁；调用方是停止扫描的必然成员，全成员行锁扫描必须等待该锁。未提交的新子行不在停止扫描的查询快照中，由提交后的 `reconcile_stopped_trees` 与 `claim_next_input` 的停止门禁补齐。用户侧消息接收链路不受影响。

协作工作接收遵守目标 Session → 来源 Run → 工具回执及目标 Turn 的顺序。来源 Run 取消、retry 释放和新 attempt 领取也领取同一 Run 行锁，因此接收检查后到提交前的 await 不会让新 Owner 或取消状态穿过事务边界。follow-up 接收只再锁定目标 Turn，目标 Session 行锁已串行化该 Turn 的生命周期；不额外锁第二个 Session。

协作消息先只读解析目标，再锁定来源 Run、校验身份，最后取得树事件锁并写入事件；来源 Run 行锁随事务保持到提交。取消工具先锁目标 Session 与指定 Turn，再按稳定 Run ID 顺序锁定来源与目标 Run，校验来源后复用 `cancel_turn` 的持久事务及幂等回执。两成员同时互相取消也按同一 Run 顺序领取，不会各自持有来源 Run 等待对方；目标 Turn 终态不在工具层提前拒绝，原取消回执仍可在有效来源 Run 中重放。三类副作用共用最小私有 Run 锁定与来源校验入口。

## 替代方案

- 在 `accept_locked` 内部加入树运行时检查：接收主链路被协作树概念侵入，且用户直接发消息本就允许（`resume_tree_for_user_input` 语义）。
- 只在入口或写入前刷新来源状态：后续 await 仍允许 retry 或取消提交；必须持有来源 Run 的生命周期行锁。
- 取消时各自先锁来源 Run、再锁目标 Run：双向取消可形成两 Run 环，必须在已锁定目标 Turn 后统一排序。
- 停止后给整树成员强制 `queue_paused=True`：`pause_pending_queue` 有意只在仍有待办时保留暂停（无待办成员不需要暂停）；迟到 Input 写入发生在暂停判定之后，暂停标志本身挡不住写入。

## 后果

极小概率下（停止提交恰好插在入口检查与行锁领取之间），模型会收到明确的"协作树已停止"错误而不是静默排队；该 tool call 失败由模型在下一轮可见树状态后自行决策。`caller()` 的入口检查保留，用于拦截大多数明显已停止或已换 Owner 的调用。SessionCooperationService 显式要求调用上下文的 `worker_id`，不会用数据库当前 Owner 代替调用者身份；所有协作工具及模型边界都执行该比对。

业务已失败但运行时尚未清理的成员仍阻止整树恢复。拒绝恢复不会改变停止意图、暂停队列、Input、Receipt 或 Turn/Run；清理完成后显式继续消费原待办，用户新消息保留其他会话旧待办的暂停状态。

## 验证

- 真实 PostgreSQL 集成测试：monkeypatch 行锁领取，在接收入口检查后、行锁领取前提交整树停止；断言 `submit_input` 抛 `StateConflictError`，数据库无新增 Input（成员仍只有初始输入），树运行时 `stopped=True`。旧代码上该测试因提交未被拒绝而失败（负向验证）。
- 停止、取消清理及新用户工作全部经真实服务完成后继续旧工具调用；数据库确认树已恢复且旧 Run 已取消，旧调用仍明确拒绝，不新增成员 Input。
- 并发创建与停止使用真实 PostgreSQL 连接；从 `pg_blocking_pids` 确认停止正在等待创建事务的父行锁，放行提交后回读新成员为暂停、Input 为 pending，且没有创建 Run。
- 真实 PostgreSQL retry 测试：旧 Owner 释放租约、完成运行时清理，新 Owner 重新领取同一 Run；旧工具创建成员、提交 Input、投递消息全部拒绝，独立连接回读没有新增 Session/Input/Event，而当前 Owner 的相同操作成功。入口校验后、目标 Session 行锁前切换 Owner 时，创建和提交仍被第二次检查拒绝。仅在独立测试进程撤回两处 Owner 比对的负控运行中，5 个案例全部因未抛出预期拒绝而失败。
- 真实 PostgreSQL 并发测试在来源身份检查之后、回执领取之前阻塞接收；独立连接的 retry 或取消通过 `pg_blocking_pids` 证明等待来源 Run 行锁。放行接收后独立回读 Input/Receipt 已先提交，再确认 retry 或取消生效。仅在测试进程将锁定退回普通读取、保留 Owner/状态/租约校验的负控中，Input 的 retry、取消及消息的 retry 三项都因缺失来源 Run 阻塞边而失败。
- 真实 PostgreSQL 消息并发测试持有树事件 advisory lock，使消息在来源 Run 已锁定后等待；`pg_blocking_pids` 同时确认消息等树锁、retry 等来源 Run。放行后从独立连接确认事件先提交，再由新 Owner 领取。来源锁前已经完成接管的消息明确拒绝且不产生 Event。
- 取消并发测试在精确目标 Turn 锁上阻塞，期间来源 Run 经真实 retry 接管；旧工具在放行后拒绝，目标 Run、Turn、暂停标志与回执均保持未取消。双向取消让两事务同时持有相反的目标 Turn，按相同 Run 顺序领取后恰一成功、另一方来源失效；数据库只有一份取消回执、一条 cancel_requested Run，测试超时限制拒绝死锁。仅将锁序改为各自先来源、后目标的负控在 PostgreSQL 中触发 `DeadlockDetectedError`，证明稳定排序不可省略。
- 真实 PostgreSQL 参数化测试覆盖根与子成员分别承担清理责任，以及显式继续与用户新消息两个入口。Run/Turn 经真实服务结算后恢复被拒绝，独立连接回读全部停止、暂停、Input、Receipt、Turn/Run 事实不变；调用实际清理 Owner 后原待办可消费并取得执行资格，新用户消息只恢复目标队列。后来再次停止后重放同一恢复回执，全部新状态不变。`pytest test/integration/services/test_session_cooperation.py -q` 的 84 项通过；仅在独立测试进程恢复旧的活动 Turn 判定后，两个显式继续案例均因缺少预期拒绝而失败，负控未改共享源码。
- 真实 HTTP 回归分别向两个恢复入口提交事件，清理未确认时返回 409；独立连接确认停止、暂停、原 Input 归属及 Turn/Run 保持不变，未新增回执。`test/integration/api/test_session_cooperation_state_recovery.py` 三项通过；相关服务联合 PostgreSQL 回归共 126 项通过。
- 真实 API、worker 与 container 沙盒的容量及整树停止/继续 E2E 两项通过，验证清理后的合法恢复与兄弟工具调用。实际命令为 `docker compose exec -T -e COOPERATION_REPLAY_URL=http://api:8766/v1 api uv run --no-sync --group test pytest test/e2e/test_session_cooperation_e2e.py::test_full_tree_capacity_control_and_sibling_tools -q -p no:cacheprovider`。该证据不包含真实 Cube 或故意保留的外部残留命令；未清理责任的拒绝由独立 PostgreSQL 与 HTTP 负向用例证明。
