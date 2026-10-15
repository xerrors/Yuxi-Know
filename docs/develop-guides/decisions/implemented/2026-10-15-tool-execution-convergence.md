# 工具执行事实与迁移冗余收敛

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/repositories/tool_audit.py

## 问题

同一工具执行结果同时写入 tool_audit Message 和独立 ToolCall 表；checkpoint 又从模型声明创建 pending ToolCall。Run 终态、审批拒绝、Memory 与 Dashboard 分别同步或读取旧表，声明与执行的概念和状态词表混杂。公开 item 已以 Message 为身份来源，旧表仍维护没有独立业务意义的结果副本。

## 目标与范围

以输入到最终历史的完整链路核对迁移入口、事实所有权、调用空壳、兼容消费者、配置、状态清理、测试和交付。删除经调用与持久化证据确认的旧机制。工具声明属于模型 Message，工具执行属于 tool_audit Message，公开 item 是协议快照；checkpoint 拥有执行恢复上下文。普通历史、调试审计、Memory 和统计共用这些事实。目标不改变 FIFO、权限、Run lease、外部工具协议或用户工作区文件。

关联链路分别由 [Thread Input 生命周期](./2026-10-15-session-input-monitor-convergence.md)、[后台作业投影](./2026-10-15-background-job-projection-convergence.md) 和 [运行适配器与依赖](./2026-10-15-runtime-adapter-contract-cleanup.md) 的实现 Owner 与验证负责。

假设：沿用当前空库基线和拒绝不匹配 Schema 的部署契约，不在线迁移已有用户数据。独立表删除通过提升 business 版本明确拒绝旧库，不通过运行时 fallback 读取旧表。

## 决策

### 实现方案

工具执行由 Message 的 operation_id、状态、输入输出和来源模型声明统一拥有；Memory、Dashboard 与审计读取此记录，checkpoint 只对已记录生命周期做补全。business Schema 版本提升为 3，启动拒绝旧库，空库检测识别已退役 tool_calls 表。

## 替代方案

- keep：保留双写，仍需维护两套状态和对账，拒绝。
- narrow：只把 ToolCall 改成只读但保留表和 Schema，仍需生产者或数据回填，拒绝。
- replace：新增另一套工具实体/投影框架，扩大维护面，拒绝。
- remove：删除独立 ToolCall ORM/表、checkpoint 生成和终态同步，当前消费者直接查询工具 Message。采用此方案。

模型审计仅提供调用声明；执行结果、错误与生命周期由工具 Message 提供。工具尚未执行时不伪造 pending 执行。审批拒绝保存明确来源但无 started_at 的工具结果。中断后的合法恢复通过同 Turn 的 resume ancestry 关联原模型声明。公开协议保留必要 item 身份及标准状态映射，不新增持久副本。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 工具执行只拥有一份持久事实 | 删除表但保留隐式双写或读取 | Message ORM / tool_audit / checkpoint_messages | metadata 与真实 PG 表/执行回读 | 恢复 ToolCall 表或兼容键 | Passed：backend unit 2654 passed；真实 PG 与生命周期 E2E 回读执行事实和新库表结构 |
| 审批、恢复、错误、取消保持明确 Run/Turn 归属 | 误用相邻 Run 或混同声明与执行 | tool_audit / runs / public_items | lease integration、HTTP/worker lifecycle E2E | 错误 owner、同 call_id 跨 Run、拒绝无执行开始 | Passed：核心/扩展 lifecycle 与协作 E2E 29 passed；lease PG 10 passed |
| Memory 与 Dashboard 读取唯一工具事实 | 统计声明次数、漏结果或泄露审计 | memory_history / Dashboard repositories | 相关 unit、真实 PG/HTTP 回读 | 无执行的声明不得算成功工具；跨用户来源拒绝 | Passed：Memory PG 4 passed；Dashboard HTTP 12 passed；统计状态与来源隔离负控精确失败 |
| 历史机制迁移闭环 | 旧入口或测试继续保护退役协议 | 当前入口、配置、装配与测试 Owner | 调用搜索、相关 unit、工程检查、文档 build | 旧能力不存在的负向搜索 | Inspected：源码、fixture、性能入口与依赖装配无旧消费者；工程 gate Passed |

旧能力不存在：源码与新库不包含独立 ToolCall 表、compatibility_tool_call_id、add_tool_call、checkpoint 的旧表投影及 Run 双终态同步；当前文档和正向 fixture 不要求旧表。历史归档仅作为来源记录。

重新引入条件：存在独立于 Message 生命周期的明确业务实体、消费者、所有权和真实链路证据，经单独决策引入，不能作为历史兼容恢复。

## 后果

business Schema 变化不自动操作现有数据库。工具统计按执行事实计算，未开始的声明不计入执行。现有公开 item 是断线恢复与分页的必要协议快照，独立提交失败可由已提交执行事实重放补全；其删除需要不同的因果与分页方案，不把它与旧 ToolCall 表等同。

验证环境：真实 PostgreSQL 使用独立测试库，Redis 使用独立实例，API、ARQ worker 与模型重放服务使用独立进程；沙盒场景使用真实 Cube。`test_agent_lifecycle_e2e.py`、`test_agent_lifecycle_extended_e2e.py` 与 `test_session_cooperation_e2e.py` 的 29 项用例验证 PG、公开 item、模型/工具审计及产物，不使用 HTTP 200 代替终态。隔离进程以正式容器的普通用户运行。

隔离负控：在独立进程中分别移除工具读取的同 Session、同 Turn 条件，真实 PG fixture 会读出各自的错误来源；移除退役表识别后，新库初始化 guard 不再拒绝残留旧表。统计分别移除 started_at 条件、恢复 total-successful 推算失败次数，新增用例分别以 5≠4 与 3≠1 失败。变异不写回工作区。

浏览器范围：真实 ThreadDetailDrawer SFC 以显式响应 fixture 验证六种执行状态、详情展开、loading、empty、error、浅/深色与 390px 宽度。Thread Input 监听与视图释放由前端 unit 和真实 AbortController 配合受控 fetch 的 signal 透传与取消测试证明，本记录未把 Drawer 浏览器 fixture 作为该链路 E2E。

Dashboard 真实 HTTP：`test/integration/api/test_dashboard_router.py` 12 passed。工具统计与时间序列共享 JSON 字段表达式的绑定参数；分别重建 SELECT 和 GROUP BY 的表达式会在 PostgreSQL 触发 GroupingError，新增 HTTP 用例在修复前以 500 失败、修复后回读工具输入输出及 3 次执行/1 次成功/1 次失败的增量。
