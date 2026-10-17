# Agents 会话配置与等待取消

状态：implemented
类型：architecture
Owner：backend/yuxi/modules/agents/services/inputs.py

## 问题

普通输入只保存模型和审批模式，提示词、资源选择与执行限制在 worker 启动时读取 Agent 定义。同一会话或已排队输入因此可能随外部配置变化。并行工具等待的取消清理假定末条消息为 AIMessage，并可能丢弃尚在 pending writes 中的已完成工具结果。

本记录拥有[机制对齐方案](2026-10-09-agents-api-mechanism-alignment.md)第 2 步的配置与取消决定，补充[公开资源决定](2026-10-09-agents-resource-contract.md)。附件/OCR 与分页恢复分别由[附件提交决定](2026-10-09-agents-draft-attachments.md)、[查询恢复决定](2026-10-09-agents-query-recovery.md)拥有；整体验收见[对齐交付记录](../archived/2026-10-09-agents-api-delivery.md)。

## 决策

Session 创建时保存完整的可配置 Agent Context 与 Schema 默认值，模型按显式值、Agent 配置和系统默认值解析。空会话也要求可用聊天模型，公开 agent.model 返回有效值。显式空白模型返回 422；模型省略保持原值，POST 更新中的 null 被拒绝。更新模型和审批模式只作用于之后接收的新输入，已保存的 Agent 或系统默认值修改不改变已有会话。

接收与更新持有同一个 Session 锁。新 Input 深拷贝会话配置，原子应用 follow-up 单次模型与审批覆盖；覆盖不改写会话。活动 steer 与等待恢复使用当前 Run 配置；空闲 steer 批次保存创建时的配置。排队 Input 的完整配置保持冻结，后续消息仍遵循默认 steer、显式 FIFO 和等待点限制。

快照保存资源选择意图，不保存运行身份或授权结果。worker 注入当前身份、Workdir 和 lease，重新解析资源可见性；工具副作用继续在执行边界校验权限。协作默认继承派发 Run 的实际配置，显式选择其他 Agent 时冻结目标 Context；父会话更新不改变正在派发的 Run。

等待取消先用原图 END 状态改写合入已完成节点的 pending writes、清除等待任务，再为当前 AI 未配对的调用补齐取消 ToolMessage，最后清除状态改写触发的任务。完成检测只读取当前 AI 之后的结果，取消消息身份包含 AI 与 call ID。已完成消息和其他业务增量保留。任一持久提交后失联均可重试；清理不执行模型或工具，失败保持 cancelling，由恢复扫描继续处理。清理完成后才写 cancelled，最终结果仍由目标 Turn 的 result_run_id 拥有。

### 实现方案

input_config 解析声明配置和默认值，Session 的既有 config_snapshot JSON 列保存会话值，Input/Run payload 保存完整 context_snapshot。inputs 拥有原子接收，threads 拥有会话锁内更新，preparation 消费冻结配置并装配当前执行资源。scheduler 继续在事务提交后派发；Receipt 幂等重放保留原 Input 与消费归属。

turns 的取消用例调用原拓扑的 checkpoint-only 图，仅使用状态 API。三次状态提交分别拥有 pending writes 合入、缺失结果补齐和任务清空，真实 reducer 与崩溃重试测试证明结果没有丢失或重复。公开适配层只投影有效模型和审批值，完整 Context 不进入公开资源；Web、CLI 与 Demo 继续直接消费 agent.model 和 yuxi 配置。

## 替代方案

- worker 每次读取最新 Agent：无需保存完整配置，但会话与排队请求受外部修改影响，提交意图难以解释。
- 只保存模型和审批，在领取队头时冻结其他字段：存储较少，但已接收请求的行为仍随排队时间改变。采用接收时完整冻结。
- Session 更新追溯修改队列或活动 Turn：操作范围更大，覆盖与模型历史之间出现竞态。采用只影响后续接收的输入。
- 取消时删除 AI 工具调用或直接补取消消息：写入少，但可能破坏调用/结果配对、删除真实结果或丢掉 sibling pending writes。采用原图状态提交和补齐结果。

## 后果

复用已有 JSON 列与 payload，无新增表、状态或迁移。Session 和每个 Input 保存一份可配置 Context，增加提示词与配置的存储；资源内容、凭据和授权不被固化。已有会话要更换模型或审批模式需显式更新，其他不受支持的官方配置字段继续拒绝。

取消维护有三个持久提交点，其崩溃恢复由同一个 cancelling Owner 负责。动态工作区提示、资源权限和文件内容继续在执行边界生效，配置快照不承诺外部模型或工具字节永久不变。

## 验证

本记录原始验收使用开发 Compose 的真实 PostgreSQL、HTTP、Redis、worker 与 provisioner，模型使用确定性重放服务。模型请求独立检查会话提示词与预加载内容；最终配置、manifest、Input/Turn/Run 归属和取消前后 checkpoint 均重新读取。当前附件事实表、唯一配置快照与临时来源清理的决定及证据由[事实归一记录](2026-10-09-agents-owner-simplification.md)拥有。

| 实际命令 / 检查 | 结果 |
| --- | --- |
| `docker compose exec -T api uv run --no-sync --group test pytest test/unit -m 'not slow' -q` | 2576 passed，55 skipped；包含完整字段/身份过滤、空白模型拒绝、重复 call ID、真实 StateGraph 的 pending writes 与两处提交后崩溃恢复 |
| `docker compose exec -T api uv run --no-sync --group test pytest test/integration/services/test_thread_priority_inputs.py -q` | 12 passed；系统默认冻结、Input 合批、FIFO、等待限制、幂等与提交后派发 |
| `docker compose exec -T api uv run --no-sync --group test pytest test/integration/services/test_session_cooperation.py -q` | 55 passed；配置继承、目标 Agent 快照、权限、树范围与恢复 |
| `docker compose exec -T api uv run --no-sync --group test pytest test/integration/services/test_thread_priority_inputs.py::test_empty_session_freezes_system_default_before_first_input -q` | 1 passed；空会话创建后修改系统默认和 Agent，首条 Input/Run 保持原快照 |
| `docker compose exec -T api uv run --no-sync --group test pytest test/integration/api/test_public_session_resources.py test/integration/api/test_public_agents_key_boundary.py test/integration/api/test_turn_result_causality.py -q` | 9 passed；有效模型、资源操作一致、作用域与结果因果 |
| 下方配置与取消 worker E2E 命令 | 6 passed；双模型更新、单次覆盖、已接收配置冻结、真实 checkpoint 结果保留和最终终态 |
| 下方权限 worker E2E 命令 | 3 passed；快照输入与恢复执行仍受当前授权约束 |
| 变更文件 Ruff、`python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`、`git diff --check` | Passed；64 脚本测试通过 |
| `cd docs && pnpm run build` | Passed |

配置与取消的实际 E2E 命令：

```bash
docker compose exec -T api uv run --no-sync --group test pytest \
  test/e2e/test_session_config_e2e.py \
  'test/e2e/test_session_cooperation_e2e.py::test_sessions_use_public_state_and_shared_sandbox[True-False-True]' \
  'test/e2e/test_session_cooperation_e2e.py::test_sessions_use_public_state_and_shared_sandbox[False-False-True]' \
  test/e2e/test_agent_lifecycle_e2e.py::test_cancel_waiting_turn_pauses_queue_until_continue \
  test/e2e/test_agent_lifecycle_e2e.py::test_waiting_turn_requires_complete_answers_and_resumes_same_turn \
  test/e2e/test_agent_lifecycle_e2e.py::test_steer_aggregates_and_yields_into_same_turn -q
```

权限的实际 E2E 命令：

```bash
docker compose exec -T api uv run --no-sync --group test pytest \
  test/e2e/test_permission_revocation_e2e.py::test_queued_input_after_revocation_fails_without_another_model_call \
  test/e2e/test_permission_revocation_e2e.py::test_waitpoint_resume_after_revocation_cannot_create_new_run -q
```

`--no-sync` 使用容器已有测试依赖，避免 editable 安装目录权限问题。

本记录的验证范围为配置与取消；附件、查询与整体验收由专项决定和实施计划提供证据。Not run：外部真实模型探针、官方 SDK 自动完成/收集结果。本记录不以 SDK 返回或流断开判断 Turn 成功。
