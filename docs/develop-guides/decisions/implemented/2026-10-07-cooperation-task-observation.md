# 协作任务结果、恢复隔离与会话观察

状态：implemented
类型：architecture
Owner：backend/yuxi/modules/agents/services/cooperation.py

## 问题

同一协作成员开始下一轮后，调用者仍需要读取上一份工作的精确结果。某条恢复记录或慢沙盒清理不能阻断其他会话调度。观察协作树不需要读取 checkpoint 和全部结果正文。同一 Thread 在页面和侧栏显示时，需要共享运行状态与订阅。

本决定调整任务观察、恢复隔离、协作摘要查询和前端运行状态归属。沿用 Input、Turn、Run、同树授权及四个执行名额；不增加累计执行预算、任务表或通用事件平台。

## 决策

沙盒释放、树空闲计时和销毁重建部分由[工作区路径清理](./2026-10-15-workspace-path-cleanup.md)及[Cube 用户环境](./2026-10-15-sandbox-environment.md)取代；本记录继续拥有任务观察、失败隔离、Session 锁序与前端状态决定。

侧边栏活动状态从当前 Turn、等待点类型、当前 Run 和待派发 Input 批量读取，与 Run 已读标记独立。前台事件实时更新，后台沿用会话列表轮询；查看 interrupted Run 不清除等待批准、回答或协作标签。相比把所有 interrupted Run 当作新回复，独立投影准确表达需要用户介入的等待，并保留已有未读提示。

协作等待在 Turn 层保持非终态，前端以等待中的工作展示并保留停止入口。公开 item 的扩展 metadata 区分协作等待与真正中断，避免把协议的 `incomplete` 一律渲染为错误；恢复产生的结果按原调用 item 身份闭合工具状态。用户等待判断排除协作等待，使协作期间的普通输入仍按 FIFO 入队。

协作服务通过 Input 或 Turn 读取精确状态与 `result_run_id` 指向的输出。`wait_inputs` 等待已提交 Input，从持久事实判断完成，覆盖尚未创建 Turn 的排队取消，不依赖最新 Turn 或消费游标。`get_result` 只允许指定一种身份，并执行同树、用户与应用范围校验。已有 Session 事件等待保留。

协作树摘要一次返回全部成员，批量读取且不包含输出正文。HTTP 观察入口不读取 checkpoint；前端每次轮询只发出一次请求，用完整成员状态判断整树是否可继续。

恢复按阶段、按记录隔离失败，失败不续报完整恢复成功。取消已持久接受后，即时 checkpoint 清理失败仍返回接受结果，由后台重试并报告失败。用户 VM 的生命周期互斥由 provider 持有，Run 命令清理由持久句柄及 owner 校验负责。协作消息及状态通知不等待外部环境操作。

前端按 Thread 共享运行状态、历史、SSE、恢复查询及队列监控。最后一个观察者卸载时释放订阅；隐藏视图继续接收数据，但不标已读或滚动。终态历史重新读取事件发生后的快照，失败时保留流输出；异步结果同时校验状态实例和运行状态版本，避免卸载重挂及同一 SSE 跨 Run 恢复时被迟到查询覆盖。审批面板绑定共享等待点身份。视图保留独立输入草稿，首次进入从持久草稿初始化，同一视图切换后恢复自己的编辑。

标准 Turn 生命周期事件保留官方必需的 `subagent_id` 字段并固定为 `null`，因为每个 Session 都是独立主会话。该字段属于外部线协议；独立 schema 继续严格验证标准事件。

展示层连接同一 Turn 的相邻续跑；实时消息在 Run 快照尚未刷新时使用消息明确携带的 `turn_id` 和 `run_id` 连接。连续推理和工具调用合并为一个展示组，用户消息和助手正文保持边界，各消息的持久 Run 归属不变。未知归属或不同 Turn 保持独立，避免仅凭缺少用户消息猜测运行关系。

主对话中的协作工具采用会话入口展示，多个目标逐个显示，点击打开侧栏对应成员，参数与原始结果不展开。入口身份由工具结果中的 `session_id`、完整路径和已登记的 Input 回执映射拥有；同名成员保持独立，未解析目标打开协作列表。嵌入会话保留原工具结果展示。直接复用侧栏会话标签，避免在工具结果中重复整套进程界面。

### 实现方案

`cooperation` service/repository 拥有精确任务结果和整树摘要；Input、Turn 与 Run 继续拥有持久事实。`worker`、`leases`、`turns` 和 `scheduler` 拥有恢复错误传播。`sessionRuntime` 拥有前端共享运行数据，`SessionWorkspace` 负责展示和输入；无需增加数据库表或迁移。

## 替代方案

- 保留会话最新结果：无法支持同成员多轮提交后的精确查询。
- 另建 Task 表：重复 Input/Turn 事实，扩大状态一致性成本。
- 分页摘要：增加游标、页面合并及不完整成员状态的控制判断；当前协作树不需要这一复杂度，采用一次批量读取轻量摘要。
- 全量 state 轮询：放大 checkpoint、数据库往返和结果正文成本；保留轮询方式并缩小读取契约即可解决当前问题。
- 释放沙盒时不持锁：会与新执行竞争；采用专用锁隔离生命周期，避免占用协作树锁；重复取消仍等待外部释放真实结束后交出锁。Session、Turn、Run 的非身份写入使用 PostgreSQL `FOR NO KEY UPDATE`，保持同记录写入串行，并允许通知插入所需的外键键共享锁，避免状态收敛和树通知形成反向等待。
- 重写整个工作区：扩大界面风险；提取共享运行状态即可闭合重复观察问题。

## 后果

整树摘要不提供结果正文，调用者需显式按任务身份查询。旧 `wait_sessions` 表示会话事件等待，精确提交等待使用 `wait_inputs`。某条恢复失败会使该轮健康时间不更新，但其他阶段及记录仍可继续处理。HTTP 取消接受表示取消请求已持久化，不等同于 checkpoint 清理已完成。前端后台观察不会提前消除未读状态。

## 验证

真实 PostgreSQL 测试验证 A 完成后 B 已启动仍读取 A、排队 Input 取消唤醒原 Turn、等待点经过真实执行适配器后保留 Input 身份、越权拒绝、摘要固定批量查询与完整成员集合、坏记录之后的恢复，以及阻塞沙盒释放时消息仍可提交而新执行暂缓。真实 HTTP 测试验证完整摘要和跨用户拒绝。

前端测试验证双视图单次 SSE、最后一个观察者释放、旧历史与旧恢复回调的隔离、同流跨 Run 状态进展、审批身份、隐藏页面副作用和独立草稿。浏览器在实际页面与嵌入视图中验证共享状态、单次 SSE 请求、关闭一个视图后继续接收终态；该检查使用协议注入，不能替代真实 worker E2E。

确定性协作 E2E 使用隔离环境的 superadmin 注册重放供应商，四项场景全部通过，验证精确 Input 等待、结果读取、人工回答、满容量调度、兄弟消息及整树停止与继续。根与成员主动压缩后，共享沙盒的临时文件仍保留；这组历史证据中的空闲销毁重建已由当前用户 VM 休眠恢复取代。具体入口为 `test_session_cooperation.py`、`test_agent_run_lease.py`、`test_session_cooperation_state_recovery.py`、`test_run_worker.py`、`test_session_cooperation_e2e.py`、`sessionRuntime.test.js`、`sessionWorkspaceVisibility.test.js` 与 `thread_draft.test.js`；实际命令和结果随交付记录。

标准事件回归覆盖 created、in_progress、completed、failed 和 cancelled，修复前五项均因缺少协议必需字段失败；修复后适配器测试文件 12 项通过。字段语义对照 [官方事件参考](https://developers.openai.com/api/reference/resources/beta/subresources/agents/streaming-events)与[主 Agent 字段语义](https://developers.openai.com/api/docs/guides/agents-api/multi-agent)，不通过改写 oracle 接受缺失字段。

硅基流动真实探针使用 `siliconflow-cn:deepseek-ai/DeepSeek-V4-Flash`，经过公开 HTTP、ARQ worker、PostgreSQL checkpoint、共享沙盒和严格 schema 校验的 SSE，在约 121 秒内完成根会话与成员的两份任务。持久执行段为 chat/interrupted → resume/interrupted → resume/completed；回读 91 条根 checkpoint，消费 474 条标准及扩展事件。独立查询在 B 仍 running 时准确匹配 A 的 Input、Turn、result Run 与输出，并验证读取发生于 B.started_at 与 B.finished_at 之间。共享环境由根实际写入的随机临时 marker、成员实际依赖该 marker 的成功命令及宿主文件正文共同证明；协作成员集合与持久成员准确一致且无重复、无正文。清理后回读临时 Agent 不存在、无活跃 Run、成员全部归档、Workdir 不存在和沙盒 discover 为空。

探针的根正文预期允许步骤摘要，要求最后一行是固定完成标记；子任务正文、身份、状态、文件及协议断言继续严格校验。该预期经过独立 Review；此前严格全文标记检查失败的运行不计为通过。实际命令使用 `docker compose exec -T api uv run --no-sync python -` 在标准输入执行独立探针；协议测试使用 `docker compose exec -T api uv run --no-sync pytest test/unit/services/test_openai_event_adapter.py -q`，12 项通过。工程检查及其 64 个回归、Ruff 与文档构建通过。`--no-sync` 复用容器已安装环境，常规同步安装在现有 editable build 目录遇到权限错误。

该真实模型探针补充正常协作路径的实际执行证据；四个名额容量、整树停止、失联租约和 SSE 断线续传等分支由各自用例承担。

协作重放器仅在明确摘要标记、单 user 消息、无 tools 和非流式请求同时成立时返回固定摘要 completion，普通请求继续要求完整协作工具集，鉴权与模型限制保持有效。新增协议测试在旧实现上因缺少 tools 导致断连，修复后四项通过；独立 LangChain 调用能够解析摘要响应。后端 unit 使用 `docker compose exec -T api uv run --no-sync --group test pytest test/unit -m "not slow" -q -p no:cacheprovider`，2509 项通过、55 项跳过。

摘要分页移除前的完整 Agent 确定性 E2E 使用已验证的隔离环境 superadmin 执行：`docker compose exec -T api uv run --no-sync --group test pytest test/e2e/test_session_cooperation_e2e.py test/e2e/test_agent_lifecycle_e2e.py test/e2e/test_agent_lifecycle_extended_e2e.py test/e2e/test_agent_lifecycle_key_scope_e2e.py test/e2e/test_openai_events_e2e.py -m e2e -x -q -p no:cacheprovider`，25 项全部通过，耗时约 421 秒。覆盖协作、FIFO、steer、等待恢复、工具审计、取消、附件重建、限流后继续、审批、SSE、定时任务及终端用户与 APP 隔离。模型请求由重放器提供，外部真实模型执行由硅基流动探针证明。完整摘要契约的最终 E2E 复验范围为下段的四项协作场景，其余 21 项沿用分页移除前的验证结果。

完整摘要契约的 PostgreSQL 回归建立 107 个成员，与独立持久查询核对完整有序集合，摘要读取保持四次批量 SQL 且无正文。旧实现因截断为 50 项而失败，工具 schema 与前端请求测试也因仍携带分页参数而失败；相关后端 49 项、真实 HTTP 一项通过。协作 E2E 使用 `docker compose exec -T api uv run --no-sync --group test pytest test/e2e/test_session_cooperation_e2e.py -m e2e -x -q -p no:cacheprovider`，四项通过，约 224 秒。前端全量 unit 484 项通过，lint 和 build 通过；真实页面与 PostgreSQL 的 107 个成员一致，没有分页入口或分页请求参数，1024、768、375px 下的长标题省略、浅色与暗色展示通过。独立 Review、工程检查及其 64 项回归、文档构建和 diff 检查通过。

交付复验在全新隔离 PostgreSQL 上执行 `pytest test/integration/services/test_session_cooperation.py -q -p no:cacheprovider`，43 项通过。恢复旧 Session/Run 写锁的独立进程负控在 dispatch、metadata、continue、run owner 和 run terminal 五条路径均触发真实数据库死锁；正控同时验证 Turn 外键与事件持久化。连续两次取消的旧实现因外部释放尚未结束却可领取生命周期锁而失败，修复后锁在外部释放完成前保持占有，并最终传播取消。后端全量 unit 重新执行，2509 项通过、55 项跳过。原隔离数据库恢复期间产生的环境错误不计为通过，保留原数据后以临时 PostgreSQL 补齐验证。

实时协作恢复的分组回归通过 `docker compose exec -T frontend node --test test/unit/messageGrouping.test.js test/unit/agentInputQueue.test.js`（13 项），覆盖等待工具与恢复推理连续展示、不同 Turn、未知归属及用户消息边界；相关文件 ESLint 通过。真实会话页面核对协作入口及成员嵌入展示，组件状态页面以固定测试数据核对等待与失败状态、长名称及浅暗主题。

协作工具入口的最小验证：`docker compose exec -T frontend node --test test/unit/cooperationToolView.test.js`（2 项通过），覆盖多个等待目标、同名成员精确匹配和未知任务不误跳转；修改文件 ESLint 与 `git diff --check` 通过。前端全量 unit 491 项、lint 和 build 通过；固定测试数据的浏览器页面覆盖同名多目标导航、产物折叠与等待终态转换，并在 1280、1024、768、375px 下核对浅暗主题与溢出。

活动状态的真实 HTTP 验证由协作 E2E 在持久等待点核对：Thread 快照、viewed 回执与列表一致保留等待回答、等待协作；停止整树后暂停的 FIFO 输入保持 pending，活动投影为空闲，继续队列产生独立 Turn 并最终完成。`docker compose exec -T api uv run --no-sync --group test pytest test/e2e/test_session_cooperation_e2e.py -m e2e -x -q -p no:cacheprovider` 四项通过。父子执行与周期恢复的终态等待预算为 180 秒，整项预算保留 240 秒；该预算不定义产品时延承诺。
