# LangGraph 原生事件与 Agents API 公开协议

状态：implemented
类型：architecture
Owner：backend/yuxi/modules/agents/services/openai_events.py

## 问题

执行、公开流和历史分别表达同一模型输出，工具完成和业务完成容易混淆。子执行借用父 Turn 与 runtime，父结束会影响子任务恢复，无法用真实独立的会话展示和审批子任务。

## 决策

### 实现方案

Runtime 保留 LangGraph v3 ProtocolEvent，checkpoint 通过执行结果返回。agents service 的唯一适配入口将原生内容转换为 OpenAI Agents API 事件，Redis 保存逐条公开事件，public_v1 只负责 SSE 和 cursor。生命周期通知读取已提交的 PostgreSQL 事实。标准事件遵循官方结构，业务扩展使用 `yuxi` 与 `yuxi.*`。

子任务通过持久 Input、Receipt 和 FIFO 调度创建自己的 Thread、Turn、Run。自身 Turn 拥有结果、等待点和恢复，runtime 使用自身 Thread，父子共享 Project Workdir。父取消按委派关系递归取消相应子 Turn；父完成或失败不取消子任务。Thread 授权与本轮委派分开：独立用户 follow-up 不继承旧创建者，仍使用已授权的子 Thread 和 Project。委派事务固化子 Thread 的实际模型和审批默认值，各 Input 冻结本次配置。

Message 保存可公开 item 的稳定身份及索引，实时和历史复用公开投影。前端和 CLI 直接消费公开 item 与 Turn 事件，按 item 身份合并重放和快照。普通用户恢复可见工具过程，完整审计权限保持独立。已完成块的索引边界进入 Message 快照，重连补回漏收的 done，展示平滑不覆盖恢复后的完整值。取消快照只允许有效 lease Owner 更新已公开的 assistant message，不开放新的输出、工具或 Memory 写入。执行消费者等待下一事件和停在 yield 时分别通过 CancelledError 与 GeneratorExit 关闭；两条路径在同一取消分支保存正文，仍要求持久 cancel_requested 和相同 worker Owner，随后重新抛出关闭异常。附件绑定在同一输入事务内保存于公开用户 item。

保留现有 HTTP 路径、单事件提交及幂等键。省略 mode 时在 Thread 锁内固定有效 mode 和目标，取消同样在事务内固定目标。仅支持新初始化的 Schema、Redis 格式和 cursor，不读取旧数据或协议。

## 替代方案

- 保留 chunk 和事件双重包装：增加协议维护和恢复分歧。
- 仅更换事件名称：不能解决独立子 Turn、公开 item 回读及业务完成边界。
- 全量实现 OpenAI 托管 Agents 服务：超出当前执行能力；不支持的官方输入明确拒绝。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 父子 Turn 与结果独立，取消仅沿委派关系传播 | 共享 Turn 或父完成中止子任务 | models / scheduler / runner | PostgreSQL、HTTP 和 deterministic E2E 回读 | 父先结束、子恢复、无关后续 Turn | Passed |
| 原生事件直接适配官方公开事件 | 嵌套包装、伪造工具能力或参数增量 | runtime / event adapter / transport | 官方 fixture 与协议测试 | 多内容块、Command、失败工具、无推理 | Passed |
| 公开实时与历史 item 一致且无审计泄漏 | 刷新丢工具、done 重复、内部 prompt 外泄 | messages / public serializer | HTTP、数据库、浏览器 DOM | 过期 cursor、迟到 delta、跨用户/APP | Passed |
| 输入接收批次与取消目标在事务内固定 | 重试重新入队、并发串 Turn | inputs / turns | 真实 HTTP / PostgreSQL integration | 并发 steer、waiting/cancelling、幂等重试 | Passed |
| 两种取消关闭路径保留已展示正文 | yield 关闭漏存正文 | execution / public_items | adapter unit、PostgreSQL integration、公开事件 E2E | 恢复旧 except 实际失败；无持久取消、错误 Owner、过期 lease 不写快照 | Passed |
| 前端与 CLI 消费同一协议并独立恢复子任务 | 父终态关闭子流、旧协议残留 | frontend / yuxi-cli | lint、unit、build、浏览器与 CLI tests | 刷新工具、子审批、Redis 过期 | Passed |

普通消息目标与模式回传的公开契约由[Thread 优先输入队列决策](2026-10-01-thread-priority-input-queue.md)接续。

旧能力不存在：负向搜索检查 `make_chunk`、`map_chunk_to_run_event`、`dispatchRunEventChunks`、`agent.thread.output` 及父子同 Turn 约束，核对测试、探针和当前文档。

重新引入条件：只有新的真实 consumer 和明确协议/数据承诺可以提出独立决策；不为已放弃的历史格式添加兼容路径。

### 实际证据

验证拓扑为独立 Compose 项目 `yuxi-events`，API / worker / PostgreSQL / Redis / MinIO / sandbox 使用专用环境。最终 Schema 在全新数据库 `yuxi_events_final` 初始化，既有环境未修改。实际执行通过本地私密配置包装器 `tmp/events/compose` 与 `tmp/events/test`；这些文件、凭据、运行数据与构建产物不进入版本库。

- `tmp/events/compose exec -T -u 0 api uv run --group test pytest test/unit -m 'not slow' -q`：2408 passed，55 skipped。
- `tmp/events/test test/integration/services/test_agent_input_schema.py test/integration/services/test_agent_input_concurrency.py test/integration/services/test_delegated_turn_cancellation.py -q`：18 passed。包含同键并发取消、有效取消快照及错误 Owner / 过期 lease / 新 item / 工具写入拒绝、跨 Turn 精确级联。
- `tmp/events/test test/integration/api/test_public_agent_auth.py test/integration/api/test_turn_result_causality.py test/integration/api/test_subagent_state_recovery.py test/integration/api/test_chat_router.py -q`：29 passed。普通用户通过真实 worker 生成并回读公开工具参数与结果，审计仍为 403；跨用户 / APP / 结果归属覆盖真实 HTTP 与 PostgreSQL。
- `tmp/events/compose exec -T frontend pnpm run test:unit`：381 passed；随后工具中断组件相关测试 16 passed。`pnpm run lint:check` 与 `pnpm run build` 通过；build 保留现有大 bundle 提示。
- 在 `packages/yuxi-cli` 执行 `.venv/bin/python -m pytest tests -q`：115 passed，包含活动多块 resync、保留的迟到增量和 done 完整替换。
- 工程契约、64 项脚本单测、文档相对链接及 VitePress build 已通过，最终决策状态检查与构建通过。
- 真实浏览器验证聊天 / 刷新、父先结束后的子问答与工具审批恢复、断线与过期 Redis 重同步。最终补验附件回执 / 刷新均仅一张卡片、取消工具刷新显示“已中断”且无 spinner，页面脚本错误为空；截图保存在本地 `tmp/events/browser-*.png`。

完整 assembled-path 使用 CI 同样四个生命周期文件加 `test_openai_events_e2e.py`，实际命令为 `tmp/events/test test/e2e/test_agent_lifecycle_e2e.py test/e2e/test_agent_lifecycle_extended_e2e.py test/e2e/test_agent_lifecycle_subagent_boundaries_e2e.py test/e2e/test_agent_lifecycle_key_scope_e2e.py test/e2e/test_openai_events_e2e.py -q --durations=10`：32 passed。新测试接入现有 `run_tests.sh` 与 `system-tests.yml`。

负向证据包含：同键并发取消必须重放原目标；错误 Owner、过期 lease、新 item 与工具不能借取消快照写入；父取消不能影响子 Thread 的无关后续 Turn；已完成正文不能因后续失败降级。正文负向测试在未修复代码上实际失败，修复后完整 unit 通过。工具 call_id、漏收 done、迟到增量与附件回执均通过实时、数据库回读或真实 DOM 验证。

测试中新建供应商后等待当前模型缓存的 5 秒跨进程传播窗口，只准备模型环境；实际模型 gate、PG / HTTP 终态与产物仍为独立验收事实。没有修改模型缓存协议。外部真实模型、外部 Langfuse 导出与性能负载测试不属于本次已执行证据。

### 取消关闭路径补验

执行边界 adapter 单测 47 项通过，新增 chat/resume 两种关闭与 Owner 负向组合共 12 项；旧异常分支实际失败 2 项。真实 PostgreSQL 并发测试 11 项通过。专属 Skill、公开事件、生命周期与权限撤销 assembled path 共 47 项通过，包含取消后正文历史回读；本次准确命令见 PR。

## 后果

Schema、公开输入和输出均为不兼容切换，必须使用全新初始化环境。持久化索引分配、取消遍历和重放合并涉及并发，需要真实数据库和 worker 证据。LangGraph v3 流协议仍为上游实验性接口；适配范围由独立官方 fixture、原生块案例和真实 assembled-path 测试约束。不支持的官方输入动作显式拒绝。

此决定接续[生命周期框架](2026-09-29-agent-lifecycle-framework.md)的子任务身份与恢复部分，以及[线程事件归属](2026-09-30-thread-event-routing.md)的原生协议职责；两份当前决定同步指向本记录。
