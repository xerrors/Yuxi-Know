# 已提交 Run 的队列发布由调度器统一裁决

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/services/scheduler.py

## 问题

Input/Receipt 或恢复命令提交后，队列发布失败不能改变已接受的命令。只在协作工具捕获专用发布异常，导致普通消息、人工恢复和队列继续对同一故障给出不同结果；调用方还需要了解调度器的传输异常。

## 决策

### 实现方案

`scheduler.deliver` 在已提交 Run 的 ARQ 发布边界记录发布异常并返回 `False`，成功返回 `True`；工作目录、配置和领取错误继续显式失败。所有提交后的入口复用该行为，命令结果仍来自 PostgreSQL 的 Input/Receipt。删除 `DispatchDeliveryError` 和协作入口专用捕获。

`dispatch_next_input` 返回本轮发布是否未失败：新 Run 发布成功或没有可领取工作时为 `True`，发布失败时为 `False`。现有业务调用方不读取其返回值；恢复扫描读取两处发布结果，将失败计入当轮聚合异常，保留 worker readiness 的恢复健康后果。

## 替代方案

- 每个入口分别捕获异常：增加重复策略，并且遗漏入口时会再次暴露不同的接收语义。
- 发布错误继续向命令入口抛出：数据库已经接收，错误会诱导模型或用户重复提交；队列已经具有按原 Run 补投的恢复机制。
- 把所有调度错误都改为发布延迟：隐藏目录、配置和领取错误，超出已有补投承诺。

## 后果

发布失败会延迟执行，pending Run 继续由恢复扫描补投；入口成功只表示命令持久接受。目录、领取和后续附件清理错误继续显式失败，不被伪装为发布延迟。进程取消不被异常捕获。所有命令入口使用相同的提交后发布语义，恢复扫描仍会因任何一条发布失败而拒绝续报完整恢复健康。

## 验证

- 相关 unit 与真实 PostgreSQL 输入测试共 32 项通过：`test_agent_scheduler_recovery.py`、`test_agent_dispatch_receipts.py`、`test_thread_priority_inputs.py`。
- 发布故障测试在实际 enqueue 边界抛连接错误；FastAPI HTTP 事件通过 ASGI 发起，回读 Input/Receipt/Turn/Run 证明接收、幂等和补投不产生第二份工作。队列继续命令的控制回执同样被独立回读。
- 恢复扫描在首次领取 ready Input、补投已存 pending Run 两类发布故障下，都在当轮抛出聚合异常；故障解除后仍复用原 Run。目录校验错误继续向调用方抛出。
- 真实 PostgreSQL、MinIO 与文件的附件测试 `test_input_attachments.py` 共 13 项通过，覆盖无可执行工作时的返回值与附件准备、归档、清理事实。
- 新发布测试由既有 `scripts/ci_run_service_integration.sh` 执行；入口到真实 worker 的完整覆盖由现有 E2E 提供，故障注入测试不替代该层证据。

旧能力不存在：删除协作专用发布异常与捕获；不保留按调用入口选择的发布错误策略。

重新引入条件：只有队列发布之外出现不同、明确且有当前调用方的恢复承诺，才讨论独立结果或策略；不得按 UI、HTTP 或工具来源分叉。
