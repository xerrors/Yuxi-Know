# Agents Session 公开协议

状态：implemented
类型：feature
Owner：backend/yuxi/api/routers/public_v1/agents/threads.py

## 问题

公开接口的 Thread 路径与 Session 事件命名不一致，响应结构、持久内容分页和异步完成条件缺少明确契约。外部调用方需要一套可查阅、可恢复并能确认最终结果的会话协议。

## 决策

资源结构、更新方法、列表 cursor 和客户端消费由[公开资源决定](2026-10-09-agents-resource-contract.md)部分取代；本记录继续拥有 Session 路径、初始输入、持久 Items 与长期 SSE 的核心子集边界。当前公开行为以[API 参考](../../../advanced/agents-public-api.md)和后续决定为准。

公开资源使用 Session，ID 沿用 Thread UUID。HTTP 实现 OpenAI Agents 核心会话契约的显式子集：创建与详情返回 `agent.session`，支持字符串初始输入、普通消息和取消事件、持久 Session Items 及 SSE。FIFO、Input/Run、等待点和协作树属于 Yuxi 扩展。当前维护入口见[维护索引](../../agents-api-alignment-plan.md)，客户端限制由[公开 API 参考](../../../advanced/agents-public-api.md)维护。

### 实现方案

[Public Session 适配层](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/api/routers/public_v1/agents/threads.py)拥有请求、响应、HTTP 状态码和 OpenAPI。创建返回 201，事件持久接收返回 202；会话核心字段与 `yuxi` 业务快照分开装配。Web、CLI 与 Demo 在各自 HTTP 边界读取新契约，内部 Thread、Turn 和 Run 名称继续表达业务归属。现有 CLI 决定的公开入口由本记录部分取代，见[CLI 决定](2026-10-01-npm-cli-public-v1.md)。

[公开 Items 投影](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/services/public_items.py)复用实时事件与历史查询的同一登记结果；repository 使用用户、APP 与 Session 作用域查询。Session Items 的 `after` 只定位该授权会话的公开 item。请求边界校验输入长度与图片，响应内容块允许多块文本合并后的持久正文及执行中的空工具结果。

agents services/repositories 继续拥有权限、持久输入、回执、FIFO、执行状态和结果归属。适配层不改变事务提交与 worker 投递顺序，也不根据模型文本结束或相邻 Run 推断结果。SSE 是长期订阅；客户端以目标 Turn 的整轮终态回读明确结果并主动关闭连接。创建流先发送 `agent.session.created`。无旧路径 alias、数据库迁移或新增依赖。

## 替代方案

仅改变路径并保留原响应无法统一会话资源的读取方式。全面复制官方平台涉及环境、工具执行和 SDK 运行行为，而这些能力缺少当前实现与消费者。核心协议子集允许复用容易兼容的字段和事件，并明确剩余差异。

## 后果

公开路径和响应要求外部调用方同步。Session 资源、POST 更新、列表 cursor、独立回执和归档标记采用[公开资源决定](2026-10-09-agents-resource-contract.md)。`agent.model` 返回会话快照中的有效模型，创建时解析 Agent 或系统默认值；配置生效时机由[配置及取消决定](2026-10-09-agents-session-lifecycle.md)拥有。官方 SDK 自动结束调用和最终结果收集不属于兼容承诺。

附件和完整查询/恢复的后续取舍见[机制对齐决定](2026-10-09-agents-api-mechanism-alignment.md)，当前协议范围由[公开 API 参考](../../../advanced/agents-public-api.md)维护。资源统一与直接消费、会话配置与取消生命周期已分别由对应决定生效；附件与完整查询恢复分别由[附件提交决定](2026-10-09-agents-draft-attachments.md)和[查询恢复决定](2026-10-09-agents-query-recovery.md)提供独立证据；本记录的验证范围限于保留的核心子集。

原核心子集阶段只验证响应 limit；[查询与恢复决定](2026-10-09-agents-query-recovery.md)与[事实归一决定](2026-10-09-agents-owner-simplification.md)拥有当前 repository 的有界数据库分页及真实 PostgreSQL 证据。历史数据迁移与部署平台兼容不在范围内。

## 验证

验证环境为开发 Compose 的真实 HTTP、PostgreSQL、Redis、worker 和 provisioner，模型响应使用确定性重放服务。Items 的双向分页、跨 Session cursor、APP 隔离、未登记审计排除和执行中空工具结果经过 HTTP/数据库验证。字符串、创建流、合法多块长文本、输入与结果归属经过真实 worker 验证。

| 命令 / 检查 | 实际结果 |
| --- | --- |
| `python3 scripts/verify_engineering_contracts.py` | Passed |
| `python3 -m unittest scripts.test_verify_engineering_contracts` | 64 passed |
| `docker compose exec -T api uv run --no-sync pytest test/unit -m "not slow" -q` | 2563 passed，55 skipped |
| `docker compose exec -T api uv run --no-sync pytest test/unit/routers/test_public_session_contract.py test/unit/services/test_openai_event_adapter.py test/unit/routers/test_public_agent_resume_schema.py test/unit/services/test_public_agents_api.py -q` | 响应修正后 38 passed |
| `docker compose exec -T api uv run --no-sync pytest test/integration/api/test_public_session_items.py test/integration/api/test_public_agents_key_boundary.py test/integration/api/test_public_agent_auth.py -q` | 13 passed |
| Viewer、Dashboard、私有 Agent 权限、Items、Key boundary 与 Auth 的最终 HTTP integration | 30 passed |
| 生命周期、扩展、协作、Key scope 与 OpenAI events 五文件 E2E | 29 个唯一场景通过；最终补跑后三文件为 9 passed |
| 权限撤销相关筛选 E2E | 8 passed，3 deselected |
| `docker compose exec -T frontend pnpm run lint:check`、`pnpm run test:unit`、`pnpm run build` | Passed；509 unit passed |
| 真实前端浏览器与 HTTP / PostgreSQL 回读 | Session 创建、详情适配、真实聊天路由 DOM 与归档通过；仅清理该测试 Session |
| CLI `npm run typecheck`、`npm test`、`npm run pack:check` | Passed；10 tests passed；pack 为 dry run |
| Demo `npm test`、`npm run lint`、`npm run build`、`npm run test:browser` | Passed；13 unit 与 15 browser passed（浏览器测试使用 mock HTTP） |
| `uvx ruff check backend/yuxi` 与修改的公开适配层格式检查 | Passed |
| Swagger 实际页面 | 创建 201、JSON/SSE 类型、响应模型、幂等字段和长期连接说明可见 |
| 文档相对链接、`cd docs && pnpm run build`、`git diff --check` | Passed |

E2E 实际命令为 `docker compose exec -T api uv run --no-sync pytest test/e2e/test_agent_lifecycle_e2e.py test/e2e/test_agent_lifecycle_extended_e2e.py test/e2e/test_session_cooperation_e2e.py test/e2e/test_agent_lifecycle_key_scope_e2e.py test/e2e/test_openai_events_e2e.py -m e2e -x -q`，以及后三文件同参数补跑。旧轮在 collection 后源文件已修正但内存仍使用旧 helper，结果为 21 passed、1 failed、1 teardown error；补跑使用最新代码，9 passed 覆盖全部剩余场景。

最终 HTTP 命令为 `docker compose exec -T api uv run --no-sync pytest test/integration/api/test_viewer_filesystem_router.py test/integration/api/test_dashboard_router.py test/integration/api/test_permission_convergence.py::test_private_agent_crud_isolation_governance_and_app_default test/integration/api/test_public_session_items.py test/integration/api/test_public_agents_key_boundary.py test/integration/api/test_public_agent_auth.py -x -q`。

权限撤销命令为 `docker compose exec -T api uv run --no-sync pytest test/e2e/test_permission_revocation_e2e.py -m e2e -k 'tool_boundary_rechecks_current_caller_and_retains_history or waitpoint_resume_after_revocation_cannot_create_new_run or failed_model_response_cannot_start_retry_or_summary_after_revocation' -x -q`；筛选覆盖本次迁移的调用方，另外 3 个场景未在此轮运行。独立 Reviewer 复查完整 diff、新增文件和上述证据，无未解决实质问题。

并行提问与协作等待的取消专项由[配置及取消决定](2026-10-09-agents-session-lifecycle.md)拥有；原图清理保留完成结果与业务增量，并支持提交后崩溃恢复。该专项的真实 checkpoint、worker 与负向证据独立于本记录的协议核心子集验收。

标准 `uv run --group test` 在当前容器的 editable package 构建阶段因 `yuxi.egg-info` 写权限失败；测试使用容器既有依赖的 `--no-sync` 执行。真实外部模型、官方 SDK、长历史容量及生产 nginx 部署为 Not run。
