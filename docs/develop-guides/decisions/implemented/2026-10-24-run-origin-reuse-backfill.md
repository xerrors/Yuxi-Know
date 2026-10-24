# 复用会话时回填 Run origin 来源快照

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/agent_request_service.py

## 问题

`submit_agent_request` 只在**新建** Conversation 时把本次 Run 的来源快照（`origin_metadata + source + channel`）写入会话 `extra_metadata`；命中既有会话直接复用时没有任何写入。agent-eval / call / channel 等外部入口常用 `create_conversation=False` 复用既有线程，会话因此长期缺失 `source`。而 `ConversationRepository._exclude_source_conditions` 按 `extra_metadata["source"]` 把 `agent_call`/`agent_evaluation` 会话从普通用户列表、搜索结果与项目统计中排除，缺失 `source` 的外部会话被错误地当作普通 Chat 会话展示与计数。

## 决策

### 实现方案

回填实现在 `_persist_request` 取得会话行锁之后：`get_thread_conversation(lock=True)` 经 `FOR UPDATE + populate_existing` 重读会话最新已提交值，再按 `{**origin_metadata, source, channel}` 对 `extra_metadata` **仅补缺失键、不覆盖既有值**，有变化才 flush；请求与 Run 在同一事务内提交。锁内重读保证并发不同入口复用同一会话时，后到事务基于先提交者的结果合并，不会整体覆写丢失键。来源事实仍由每次请求的 `RunOrigin` 拥有；会话上最早的来源优先保留，后续不同入口复用不改写历史归属。请求与 Run 侧的既有写入路径不变。

## 替代方案

- 只在创建 Run 时写、会话不回填：拒绝。列表/统计排除的读取方就是会话投影，Run 归属已正确，缺的是会话级来源。
- 复用会话时覆盖 `source` 为最近一次入口：拒绝。会把既有会话的归属翻面，历史 Run 与列表口径互相矛盾。
- 在 `submit_agent_request` 无锁读取的会话快照上直接合并回填：拒绝。实测两个不同来源并发 submit 同一无来源会话时，后提交事务用陈旧快照整体覆写会丢失先提交者的键；必须放进 `_persist_request` 的行锁重读之后。

## 后果

外部入口复用会话后，该会话立即被列表/统计排除口径正确识别；同一会话被多个来源复用时保留首次来源。无 schema 迁移、无接口契约变化。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 复用无来源会话时 origin 键被补写且不破坏既有元数据 | 复用路径完全不写来源，会话被误计入普通列表 | `_persist_request` 锁内回填分支 | `test/integration/services/test_agent_run_origin_backfill.py::test_reused_conversation_backfills_missing_origin` | 移除复用回写分支后该用例失败（`source/channel/evaluation_batch` 缺失） | Passed |
| 已有来源的会话不被后续请求覆盖 | 覆盖改写历史归属 | 同上（仅补缺失键） | `::test_reused_conversation_keeps_existing_origin` | 移除回写分支后 `channel` 断言 KeyError；改为覆盖语义则 `source` 断言失败 | Passed |
| 两个不同来源并发复用同一无来源会话时不丢键、不整体覆写 | 陈旧快照合并导致 lost update | `_persist_request` 锁内回填 | `::test_concurrent_reuse_merges_both_origins_without_lost_update`（gather 两个 submit，断言 batch_a/batch_b 并存） | 把合并移到锁前无锁快照（M1）或禁用 populate_existing 重读（M2）后，该用例分别以 4/4、5/5 稳定失败于先提交者键丢失；恢复后通过 | Passed |
| 回归 | 队列与请求写入漂移 | `test/integration/services/test_agent_request_queue_concurrency.py` 等既有队列集成用例 | 真实 PostgreSQL 环境复跑既有队列并发用例 8 passed（合计 11 passed）；`ruff check`/`format` 干净 | 不适用 | Passed |

未验证范围：真实 worker 消费后的端到端 Run 结果链路不在本主张内（本改动只闭合会话来源写入）；HTTP 层（外部入口经 `create_conversation=False` 复用）经由 service 单测路径等价覆盖。
