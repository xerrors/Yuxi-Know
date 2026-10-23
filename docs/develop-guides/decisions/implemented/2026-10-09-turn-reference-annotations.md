# Turn 按需标注来源

状态：implemented
类型：feature
Owner：backend/yuxi/modules/agents/services/references.py

模型选择与可标注内容范围由[来源标注模型与内容范围](2026-10-23-reference-model-and-content-scope.md)部分取代；新标注使用管理员配置，空值沿用快速响应模型。

## 问题

用户能查看检索结果，但回答中的具体结论与知识库、网页证据尚无可恢复的对应关系。来源提取依赖旧知识库工具名，且 Run 分组会漏掉同一 Turn 在恢复前取得的证据。

## 决策

### 实现方案

Agent service 从当前产品用户可见的 completed Turn 读取 result_run_id 指向的最终回答，并汇总同一 Turn 成功完成的 query_kb、open_kb_document、find_kb_document 与 web_search 工具消息。知识库来源按当前读取权限过滤。Web 内部 HTTP GET 提供来源与已保存标注，POST 按需从最终 Run 的完整 context_snapshot 读取冻结模型发起独立调用，缺失模型明确拒绝；仅接受产品用户登录 JWT，拒绝 API Key，不进入 Public 协议。入口与作用域由 [Web 内部边界决策](2026-10-09-web-reference-boundary.md) 说明。调用不进入 Agent 执行图，不创建新 Turn 或修改回答。

模型只返回回答原始 Markdown 行范围、服务端来源编号及证据摘录。后端验证编号、行范围与摘录，知识库位置使用检索记录拥有的原文范围；无法精确定位时显示检索片段。来源归一化、独立调用和输出校验集中在 `services/references.py`。引用保存在最终回答 Message.extra_metadata.references，由 Web 内部 GET 读取；Public Turn metadata 不包含引用。该字段已有持久化与明确 Turn/Run 归属，无需为派生标注新增 Schema 或升级步骤。当前 business Schema 与 v5→v6 升级由[事实归一决定](2026-10-09-agents-owner-simplification.md)拥有。同一 Turn 的并发标注请求由 PostgreSQL 事务锁串行拒绝，成功结果可直接重放；调用有时限，失败不保存成功结果。

前端复用 Markdown 原始行映射在对应块尾显示域名或文件名胶囊，同段多个来源合并为 `+N`，悬浮或聚焦展开可切换的来源卡片；正文仅在查看来源时轻量高亮。交互决策与证据见[回答来源胶囊与悬浮预览](2026-10-09-reference-source-capsules.md)。回答不裁剪前导空行，SVG/HTML 预览在 token 层保留原始行范围。知识库 manager 的真实文档能力决定入口：支持文档的来源打开现有 FileDetailModal，Dify、Notion 等只读连接器显示检索片段；网页使用 HTTP(S) 链接。文档代次或原文变化时禁用旧行号定位。刷新后从持久结果恢复。

## 替代方案

- 主 Agent 生成回答时同步输出引用：关系更直接，但改变生成流程和模型输入；留待后续独立需求。
- 新增 Turn JSON 列：数据位置直观，但增加 Schema 升级与维护成本；最终 Message 已有明确结果归属和可复用的 metadata。
- 每轮自动执行：无需点击，但所有检索回答都增加模型费用与等待时间。

## 后果

标注表达检索内容对回答的支持关系；模型判断不能证明生成时的因果来源或结论真伪。网页仅提供搜索返回片段时，标注只依据该片段。知识库行号属于解析文本，变换过的分块只能使用权威块范围。回答高亮对应 Markdown 块，原文源码视图逐行高亮。输入超出 60000 字符或调用超过 90 秒时显式失败，失败后可重试。

用户点击会产生一次额外模型调用，用量与模型信息保存在引用 metadata 中。请求成功后直接重放结果，关闭标注只改变前端显示。读取始终重新过滤当前可见知识库。该功能不新增生产配置或 Schema 版本。

## 验证

以下为来源任务在其基线上的原始验收；合入当前 main 后的快照、契约及浏览器验证单独记录，不把原日志视为合并结果。

- `docker compose exec api uv run --group test pytest test/unit/services/test_turn_references.py -q`：20 passed。覆盖标准知识检索、编号文档窗口、去重、空证据、无权来源，以及虚构来源、摘录、类型和行范围拒绝。
- `docker compose exec -e REFERENCE_PROBE_MODEL=siliconflow-cn:deepseek-ai/DeepSeek-V4-Flash api uv run --group test pytest test/integration/api/test_turn_references.py -q`：7 passed。通过真实 HTTP、PostgreSQL 和 OpenAI wire 重放验证当前 Turn 归属、早期 Run 证据、幂等、并发锁、撤权过滤、失败重试、Dify 远端文件能力与预算拒绝；另用真实模型验证回答第 3/5 行的匹配、用量与数据库回读一致。探针只发送测试文本，模型未配置时此 slow 案例明确跳过。
- `docker compose exec api uv run --group test pytest test/integration/api/test_turn_references.py -m "not slow" -q`：8 passed、1 deselected。Web 内部路径、full/agents Key 拒绝、跨用户与 APP 隔离、OpenAPI 与 Public metadata 边界通过；真实模型探针不在该集合中。实际浏览器标注和刷新均使用内部接口。
- `docker compose exec api uv run --group test pytest test/unit -m "not slow"`：2576 passed、55 skipped、7 subtests passed。既有可选服务案例跳过。
- `docker compose exec frontend pnpm run test:unit`：516 passed；`pnpm run lint:check` 与 `pnpm run build` 通过。来源 store 覆盖晚到请求归属、错误重试、空匹配和刷新恢复；renderer 回归保留前导空行、SVG 与后续正文的原始行号。
- `playwright-cli -s=turn-refs run-code --filename=frontend/test/browser/turnReferences.js`：真实检索快照会话验证标注等待、两条角标、键盘打开原文、网页跳转、隐藏/恢复、刷新、浅深色和窄屏。文档变代次的负向检查确认提示位置失效且无旧行号高亮。
- `playwright-cli -s=turn-refs run-code --filename=frontend/test/browser/turnReferenceBoundaries.js`：以持久测试快照验证前导空行的第 5/19 行、SVG、真实 HTML iframe 和带远端 file_id 的 Dify 片段入口。预览容器带额外 wrapper 或复用池混入相同内容的嵌套预览时，隐藏标注会抛 DOM 异常并残留角标；只复用直接子节点并同步原始行映射后通过。
- `python3 -m unittest scripts.test_verify_engineering_contracts`：64 passed；受影响 Python 的 Ruff 检查和 `git diff --check` 通过。`python3 scripts/verify_engineering_contracts.py` 未通过：HEAD 已有 `2026-10-09-agents-session-protocol.md` 使用不合法的 `类型：refactor`，已通过 `git show HEAD` 复现，此次不修改该独立记录。
- `cd docs && pnpm run build`：通过。独立 Reviewer 完整审查需求、diff、Owner 与证据；发现的原文裁剪、预览回归和只读连接器入口问题已修复并复审。

合入 main 的当前验证：后端完整 unit **2593 passed / 55 skipped / 7 subtests passed**，引用 unit **20 passed**；真实 HTTP **11 passed / 1 deselected**。HTTP fixture 按当前 Session `201`、`id`、`agent.model` 和完整快照创建，回读两轮公开结果；修改 Session 默认模型后仍使用结果 Run 的模型，缺失执行快照明确拒绝且没有模型请求或成功标注。Web **521 passed**，lint/build 通过；工程契约及检查器 **64 tests**、docs build 和 Ruff 通过。真实模型 slow 探针未在合并环境重跑。

合并后的真实页面通过 `frontend/test/browser/turnReferences.js` 与 `sourceCapsules.js`：独立模型 wire、持久标注、文件第 8–12 行、网页跳转、隐藏/恢复、刷新、同段四来源切换、长文件名、键盘、浅深色及小窗口滚动。测试使用独立 PostgreSQL、Redis、API 和临时 Vite 缓存；Vite 缓存失效的首次空页面失败不计为通过，切换独立缓存及真实 API 代理后重跑成功。`turnReferenceBoundaries.js` 也通过：原始第 5/19 行、前导空行、SVG、嵌套与顶层相同内容的 HTML iframe，以及 Dify 远端文件的片段入口均由真实 DOM 读取。固定来源关系用于交互 oracle，不能代替模型语义验证。

HTTP 测试在独立 Compose 数据与端口中运行，沙盒管理使用 memory 后端以免现有全局 inventory 清理扫描其他开发槽；引用链路本身不执行沙盒、队列或 Agent 图。未验证 Agent 新一轮检索生成到标注的完整 worker E2E，也未验证其他模型提供商的 JSON 输出稳定性。
