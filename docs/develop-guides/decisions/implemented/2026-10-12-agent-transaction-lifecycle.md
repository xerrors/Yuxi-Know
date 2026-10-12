# Agent 事务与生命周期的共同契约

状态：implemented
类型：architecture
Owner：backend/yuxi/modules/agents/services/scheduler.py

## 问题

Input 和控制命令重复定义幂等键、意图指纹及回执冲突，跨域创建还各自拥有删除后重放策略。Agent 治理与配置校验混在仓储和路由；Session 仓储同时拥有消息写入、Memory 与响应预算。Run 创建、等待恢复和终态收敛的平行路径使事务提交、消息绑定、结果归属及通知顺序难以局部判断。

## 决策

### 实现方案

共同的幂等键、规范化指纹和同命令同意图比较放在可供 owning service 使用的叶子契约。保持已有指纹字节、键作用域和数据库唯一约束，保留锁前快速重放及锁后复查；Input 回执固定接收目标，控制回执保留各自响应，schedules 软删与 workspace 删除重放仍由所属用例决定。不合并各域的输入校验、权限锁及事务。

Agent 权限与配置编排由 service 拥有，repository 只接收已准备结果并查询/写入；移除内部 commit 和 commit 开关，由真实调用 service 或自管入口在唯一提交点提交。默认 Agent、环境配置、mark viewed、消息写入与 Memory 消费先核对现有 HTTP、worker、扩展和测试调用者，再按职责归属迁移。认证作用域和 Input 消息解析是叶子契约，repository 不反向调用 services。

首次消费、交互恢复、协作恢复与 steer 接管共用 Run 创建与当前归属的相同部分；提交前固定 Turn/Run、Input 和附件及恢复 Message 绑定，提交后投递。终态收敛共用 Run/Turn/Session 与后续队列的持久更新序列，成功、失败、取消、已持久终态与等待保留必要策略。消息与审计写入各自拥有明确语义，最终回答由 result_run_id 指向的顶层 Run 给出，通知在 owning transaction 提交后发布。只拆 execution 及 cooperation 中实际妨碍这些边界的混合职责，不建立新的执行框架。

## 替代方案

仅将重复代码提取为能自行提交或映射 HTTP 状态的 helper 会隐藏事务与领域错误，因此共享纯比较和明确的持久流程，事务保留真实用例 Owner。统一所有回执、Run 类型及终态为一个通用状态机需要改变删除重放、等待与取消承诺；当前消费者不同的规则继续各自表达。对没有责任差异的透传合并或删除，对安全 capability 和已发布扩展入口保留消费者依据。

## 后果

AgentInput 消费、模型/工具审计和公开 item 继续各自拥有来源投影与原子执行事实；MessageRepository 拥有共同消息和兼容 ToolCall 操作。MemoryHistoryRepository 只查询，MemoryHistoryService 装配预算。subscriptions、checkpoint_state、checkpoint_messages 与 message_audits 分别表达订阅、读取 checkpoint、对账结算与审计读取；当前契约见[输入队列机制](../../../mechanisms/agent-request-queue.md#事务与消息归属)。

幂等锁前/锁后检查留在真实用例，不引入事务回调框架；promote_input 保留先锁定授权 Thread 后重放，避免扩大已删除资源的重放规则。get_pending_steer 的两个丢弃返回值调用用于取得 Input 行锁，终态与 lease 恢复沿同一 Input→Run 顺序操作。协作通知是单向服务叶子，核心生命周期不再反向导入协作命令。cooperation 与 sandbox-release 键字节由共同运行锁契约保留；身份最后超管的 DDL/应用镜像仍属于身份阶段，其他域的锁键仍由各自 Owner 拥有。

Agent 与环境仓储 flush，由治理 service 提交。新增 default/环境无变化结果和 viewed 变化标志，重复操作保持身份与修订时间并避免空提交。execution 主流程拥有图执行前的事务结束点，追踪 helper 只准备写入，禁用追踪也结束 runtime/附件读取事务；同事务已锁对象与 steer 裁决由终态服务消费，局部边界见[运行结构简化决定](2026-10-12-agent-structure-simplification.md)。终态发布共用释放与发布顺序；模型执行结果对 PG 的一致性核对留在 checkpoint 交付边界，取消的 writer flush 和 owner 裁决保持独立。工具入口只规整一次审计文本、公开合法内容与错误，checkpoint 兼容投影复用相同文本规则；空失败原因统一为“工具执行失败”。

## 验证

相关全量 unit、真实 HTTP/PG 和 worker/SSE E2E 验证冻结输入、同键同/异意图、作用域隔离、唯一领取、锁等待、FIFO、steer、交互/协作等待恢复、成功/失败/取消、重复投递、lease 和崩溃补偿，回读 Input/Receipt、Message/Run/Turn、result_run_id 与公开事件。Agent 治理、配置、绑定包、环境、默认定义、Memory 预算、schedule/project 创建重放保留各自 oracle；新增 PG 测试读取独立事务与固定结构化工具结果。

在隔离候选副本分别恢复异意图放行、repository 提前提交、更新后半失败不回滚、失效用户可见性、失效用户入口筛选/错误归属和公开工具错误分叉，五组在业务不变量断言失败，入口筛选组在“用户不存在”的错误归属断言失败；恢复候选后 9 项 PG oracle 通过。协作 E2E 首轮缺少独立 replay 服务导致两项超时，补齐环境后复验通过。工程契约、64 项工程检查 unit、Python Ruff/format、相对链接、docs build、diff 和独立 Review 随最终候选执行；数量与 skip 由[审计报告](../../audits/modules-structure-audit-2026-10-11.md)记录。

## 未验证范围

现有 Receipt 和冻结 Input 是持久消费者，不能因整理 helper 改写旧 hash 或键命名空间。并发提交、取消、审批和协作恢复需要原锁序及租约校验；ARQ 和 Redis 不拥有最终业务状态。生产部署、真实外部模型供应商和 Kubernetes backend 未运行；本组使用隔离 PG、Redis、MinIO、Docker 沙盒与固定 HTTP replay。unit skip 不计通过。
