# 执行授权刷新按边界分级：模型边界刷新资源，工具边界复查身份与 MCP 策略

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/runtime/middlewares/authorization.py

## 问题

授权中间件在每次模型调用前后与每次工具调用都执行完整刷新：打开数据库会话、复查 user/run/agent 可见性、normalize 资源配置、重算 Skill 运行快照、查询 MCP 可用性，并经 `sync_agent_context_skills` 重建用户 Skill 文件投影（pg advisory 锁加线程池文件遍历）。一个含 N 次工具调用的轮次会重复 N+2 次几乎相同的工作；两次模型边界刷新之间没有任何授权事实变化。文件投影重建是其中最重的操作，却按工具调用次数放大，并在并发下按用户串行化。

## 决策

刷新按边界分级，安全判定本身保持每次请求与每次工具调用都重新执行：

- `abefore_model` 是唯一的完整刷新点：复查身份、重建资源与 Skill 快照、解析 MCP 策略，每模型轮次一次。
- `awrap_model_call` 与摘要授权入口 `refresh_execution_authorization` 复查执行身份、解析当前 MCP 策略并同步 Skill 投影；投影同步频率与原先一致（每模型轮次一次），且发生在 Skill 文件被读取的模型轮次开始处。
- `awrap_tool_call` 只复查执行身份并解析当前 MCP 策略（`_execution_mcp_policy`），不再重建资源、快照与投影。

`tool_allowed` 的判定输入不变：执行身份实时复查，MCP 可用性与禁用工具集合每次工具调用实时解析，Skill 快照与激活状态在模型边界刷新。

### 实现方案

`authorization.py` 把原 `_refresh_execution_resources` 的候选 MCP 解析与不可用过滤拆为 `_resolve_mcp_policy`，由两条路径共用：`_refresh_execution_resources`（模型边界，含 `refresh_agent_context_resources` 全量重建）与 `_execution_mcp_policy`（工具边界，只含 `_require_execution_actor` 身份复查）。`refresh_execution_authorization` 组合 `_execution_mcp_policy` 与 `sync_agent_context_skills`，服务 `awrap_model_call` 与摘要模型授权。工具执行异常仍按原语义把故障 MCP 标记为本 Run 不可用。

## 替代方案

- 维持每工具调用全量刷新：安全语义相同，但开销随工具调用数线性放大，advisory 锁在并发下成为同用户请求的串行点。
- 工具边界完全不查数据库：身份撤销的生效窗口扩大到整轮，违反"模型和工具执行边界重新读取身份与授权"的约定。
- 投影同步增加版本戳或 TTL 缓存：能进一步降低模型边界成本，但需要新的失效通道；当前没有测量证明其必要，留作后续选项。

## 后果

模型边界之间（中断恢复与同一工具批次内）滞后的输入包括：Skill 文件投影、agent 资源选择的 normalize 结果（`tools`/`mcps`/`knowledges` 的用户可见性过滤与注册面，旧实现在每次工具调用重建）以及 Skill 快照本身——工具批次中途被撤销的 Skill，其激活判定与依赖工具要到下一模型边界才被拒绝。审批或协作等待恢复后的首个工具批次内，等待期间被撤销的 Skill 文件仍可能被 `read_file` 读取一次。MCP 可用性、禁用工具集合与执行身份不受影响：`tool_allowed` 使用的 MCP 策略每次工具调用实时解析，账号与 Agent 撤权在每次模型请求和工具调用即时失败。

## 验证

`test/unit/middlewares/test_runtime_authorization.py` 新增 `test_tool_boundary_rechecks_identity_without_rebuilding_resources`，断言工具边界复查执行身份一次且不触发资源重建与投影同步；既有网络重试后复检、上下文溢出后摘要授权、MCP 故障隔离与警告替换测试在调整 patch 目标后保持通过。真实 PostgreSQL 集成 `test/integration/services/test_runtime_authorization_boundaries.py` 中，两个原以 `refresh_execution_authorization` 为"全量刷新入口"的用例改写为按模型边界顺序驱动（`abefore_model` 后接 `refresh_execution_authorization`），继续证明绑定根冻结、共享正文按当前文件读取与撤销/重授后的选择收敛；该文件其余授权边界用例不改语义通过。完整命令与结果随交付记录。

旧能力不存在：生产装配中 `awrap_tool_call` 不再引用 `refresh_execution_authorization` 与 `sync_agent_context_skills`；资源重建函数不再包含内联的候选 MCP 解析，生产代码只有模型边界调用 `_refresh_execution_resources`（`test/unit/toolkits/test_kbs_tools.py` 作为直接调用方仍引用该函数）。

重新引入条件：若授权模型要求 Skill 文件投影或资源选择在工具批内即时收敛（如审批恢复后的长等待被视为安全边界），须以新的明确裁决恢复工具边界全量刷新，并补对应负向测试。
