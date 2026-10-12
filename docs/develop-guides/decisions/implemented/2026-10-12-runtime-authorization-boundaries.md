# 授权准备、刷新与执行边界收敛

状态：implemented
类型：architecture
Owner：backend/yuxi/modules/agents/runtime/middlewares/authorization.py

## 问题

运行准备与刷新各自规范资源选择、解析 Skill 并写入 Context，规则存在漂移风险。普通模型轮次在 before_model、wrap_model_call、after_model 重复全量解析与投影同步。MCP 发现、模型等待、重试、摘要和工具调用之间可以发生外部撤权，实际请求与副作用边界必须读取当前权限。

## 决策

### 实现方案

runtime/context 的 `refresh_agent_context_resources` 共用资源规范化、原始选择、Skill 快照、专属根正文保留和能力受限判断。首次准备从 service 已验证的调用者和配置开始；执行刷新从持久 Run 或当前调用者的 active Thread 重新读取 Agent。两条身份入口保持各自职责，共享资源解析与快照应用。刷新把同一事务已授权的 Agent 交给 Skill 解析，避免重复可见性查询。

输入准备阶段读取当前资源，保证 Skill 正文和动态依赖参与摘要压力阈值与 Token 统计。每次实际模型请求、网络重试、摘要及工具调用前重新读取授权并同步投影。模型返回后、审批等待点之前仅复查持久账号、Run/Thread 和 Agent 使用权，不做资源解析与投影扫描。普通无重试模型轮次有两次资源读取、三次身份检查和一次投影同步，构图同步另计。

shipping middleware 顺序保持既有装配。投影事务锁、文件锁、来源比较和撤权清理由 skills/projection 拥有。授权不引入 TTL、跨请求缓存、权限版本或新的失效发布机制；详细执行行为由[Agent 运行机制](../../../mechanisms/agent-runtime.md#资源权限)解释。

## 替代方案

删除模型返回检查会让模型等待期间失权的响应进入审批。用 TTL 复用完整授权会允许撤权窗口；新增全局权限版本会扩大身份、配置与投影写入面。保留三次完整刷新继续产生多次扫描。

把 Skill wrapper 放在实际授权之后，会让外层摘要和 Token 统计遗漏最终输入。删除输入准备的资源读取则会让该 wrapper 沿用旧 Skill 正文。因此输入准备与实际请求分别读取当前资源，投影同步集中于实际请求，返回阶段仅复查身份。

## 后果

普通模型轮次的投影同步从三次降为一次。隔离真实 PostgreSQL/文件用例测得来源与投影哈希扫描 **6 → 2 次**、Agent 可见性 SQL **6 → 3 次**；这些数值不包含首次 Context 准备与构图，也不是全部数据库往返或全部文件读取次数。资源解析保留两个读取边界，专属预加载根正文维持本次执行快照，共享正文与授权在后续边界读取当前值。工具副作用仍由实际 executor 的权限与目标边界执行。

## 验证

测试命令在本任务隔离 Compose 环境执行，API 与 worker 使用完整 shipping 启动，PostgreSQL、Redis、OpenAI 协议 replay 和 Docker 沙盒均为真实服务。API 与沙盒使用相同 UID，合成账号、权限、来源文件和投影与其他工作树隔离。模型请求使用本地确定性协议服务；外部付费模型与 MCP 供应商兼容性不在该证据范围。

| 主张 | 证据与结果 |
|---|---|
| 准备/刷新统一，原选择与专属根文本准确 | `pytest test/integration/services/test_runtime_authorization_boundaries.py test/integration/services/test_user_skill_projection.py -p no:cacheprovider -q`：10 passed；真实撤权与重授权恢复、共享正文更新、专属根冻结、投影字节回读 |
| 普通轮次一次投影，返回阶段仅复查身份 | 正式 factory 与真实 LangGraph 模型请求、SQL listener 和实际目录哈希读取；恢复旧授权实现后断言测得 6 次哈希与 6 次 Agent 查询，修复后为 2 和 3 |
| Skill 输入参与摘要与 Token 统计 | 正式 factory、实际模型消息及绑定工具 schema；摘要阈值触发且回读历史文件，Token 与最终模型协议输入独立计数一致 |
| 撤权先于审批等待点 | 正式图在模型 await 内提交真实 Agent 撤权，返回 Project 外写入调用后拒绝；仍获授权的对照形成真实 interrupt |
| 撤权阻止重试、摘要与副作用 | `pytest test/e2e/test_permission_revocation_e2e.py -p no:cacheprovider -q`：11 passed；HTTP 提交撤权，数据库终态、请求记录与文件/MCP 副作用为 oracle |
| 投影锁等待后重新读取授权 | 上述真实 PG 投影并发测试通过；已有事务锁和撤销清理实现保持原边界 |
| 后端回归 | `pytest test/unit -m "not slow" -p no:cacheprovider -q`：2680 passed、60 skipped；仓库根目录未挂载，Compose/根目录检查跳过，不记为通过 |
| 工程与文档 | `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`（64 项）、`cd docs && pnpm run build` 通过；build 完成相对链接检查 |

负向验证临时恢复旧授权、移除输入准备读取、将 Skill wrapper 移到摘要内层、移除返回身份检查，分别因重复扫描、撤销正文泄漏、摘要请求缺失、撤权未拒绝而失败；恢复候选后相关集成全部通过。

六个新增或实质修改的 Python 文件 Ruff lint 与格式检查通过。已有投影并发测试只增加自管理资源标记，其两处长 SQL 的 E501 在提交前 HEAD 同工具复验同样存在；该文件格式检查通过，既有 SQL 不在本阶段改动范围。
