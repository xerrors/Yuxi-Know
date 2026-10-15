# Tool 审计遵循 Thread 到 Run 的锁顺序

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/agents/repositories/tool_audit.py

## 问题

Tool lifecycle 审计先锁定 `AgentRun`，再插入引用 `Conversation` 的 `Message`；Langfuse trace 绑定按 Thread、Turn、Run 顺序锁定。并发子 Agent 工具与父 Run trace 绑定会形成 Run→Conversation 和 Conversation→Run 的反向顺序，PostgreSQL 可检测到死锁并中断 Run。

## 决策

Tool 审计在获取 Run lease 行锁前，先锁定其 `thread_id` 对应的 Conversation，再复用 `lock_output_persistence` 校验当前 owner 并锁定 Run。Thread 行锁由 ConversationRepository 持有到审计事务提交，与 Langfuse 的 Thread→Turn→Run 顺序一致；审计由短事务写入，Run 所有权检查保持；工具双投影由[工具执行收敛](./2026-10-15-tool-execution-convergence.md)取代。

### 实现方案

`ToolMessageAuditRepository._lock_run` 是 Tool lifecycle 写入的统一入口，先通过 `ConversationRepository.lock_conversation_by_thread_id` 锁定 Thread，再调用 `AgentRunRepository.lock_output_persistence`。不存在的 Thread 显式失败；Run lease owner 校验仍在原 Repository 边界执行。Tool start、complete、fail 与 error-observation 均复用该锁序。

## 替代方案

- 对 PostgreSQL deadlock 自动重试：可以缓和单次冲突，但保留反向锁序，不能证明冲突已消除，也会扩大重放边界。
- 移除 Langfuse Thread 锁：会削弱 Turn 根观察与并发执行段绑定的一致性。

## 后果

Tool 审计写入会短暂串行化同一 Thread 的 Langfuse/Tool 持久化事务，但减少死锁风险，不新增持久状态、配置或重试语义。锁序的责任归 Tool 审计 Repository 与 Langfuse 执行事务各自的写入 Owner。

## 验证

- Docker E2E `test_child_end_is_public_while_parent_waits_for_slow_child` 覆盖同一父 Turn 委派的两个独立子 Turn、父审计与子 Run 写入；真实 PostgreSQL 完成状态与公开输出由本例回读。
- 负向证据：修复前上述 E2E 在真实 PostgreSQL 重现 `DeadlockDetectedError`，冲突涉及 `INSERT messages` 与 `UPDATE agent_runs.langfuse_observation_id`；目标测试复跑结果记录在 PR。
