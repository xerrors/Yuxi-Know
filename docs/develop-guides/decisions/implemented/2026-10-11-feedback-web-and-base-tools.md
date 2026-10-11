# Web 反馈边界与基础内置工具

状态：implemented
类型：architecture
Owner：backend/yuxi/modules/extensions/tools/builtin/__init__.py

## 问题

反馈采集是 Web 产品功能，需求没有授权扩展 Public API。改进标记的注册、授权和 Skill 门控分别按工具名和 Run 特判，导致一个通用工具需要修改多个策略位置。

## 决策

### 实现方案

反馈 HTTP 位于 `api/routers/agents/feedback.py`，沿用 Web 来源标注的 `/api/agent/threads` 边界，只接受产品 JWT，固定 `app_id=None`，拒绝所有 API Key。业务 service 的最终输出、用户隔离、事务与集中查询权限保持原有边界。删除 Public 反馈路由及其 schema，前端、测试和文档使用 Web 地址，不提供旧路由兼容入口。后端开发约定明确：用户未明确要求时，不允许新增 Public 路由或扩展其协议。

`tools/builtin/__init__.py` 拥有统一基础工具集合，包含 `ask_user_question` 和 `mark_for_improvement`。运行时在现有内置工具解析循环中注册基础工具和配置工具；授权和 Skill 门控读取同一集合，不再识别特定工具或判断是否存在 Run。搜索、OCR、安装技能与展示交付物保持原有配置入口。改进标记归入 builtin 分类，真正持久化时仍要求可信 Run、调用 ID 与有效执行租约。

## 替代方案

- 只移动路由，保留 API Key 访问：仍扩大外部功能范围，不符合 Web 产品边界。
- 在三个位置分别判断工具名：基础能力增加时继续复制策略。
- 自动启用全部 builtin 工具：搜索、OCR 和安装技能也失去现有配置语义，扩大此次需求。

## 后果

`ask_user_question` 成为所有正常 Agent 图的基础能力，不再受 tools 选择影响；显式等待行为由现有人工交互流程处理。没有 Run 的上下文可见改进标记工具，但工具执行会明确拒绝无归属写入。Public 反馈尚未发布，不承诺保留撤下的地址。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| 反馈属于 Web，Public 没有新增反馈协议 | HTTP、身份 | Web feedback router、后端约定 | 真实 HTTP integration，Public 路由与 schema 回读 | 产品 JWT 访问旧 Public 地址返回 404；full/agents Key 不能使用 Web 反馈 | Passed |
| 基础工具自动注册、无需配置与 Skill | 模型、ToolNode、授权 | builtin 基础集合、runtime、middlewares | unit 与 worker E2E | tools/skills 为空、无 Run 的注册；未激活 Skill 引用基础工具也不能隐藏它；配置重复不重复注册 | Passed |
| 通用白名单不绕过资源或执行身份校验 | 授权、持久化 | authorization、feedback service | unit、PG integration | 同名 MCP 仍拒绝冲突、未激活普通 Skill 依赖仍不可调用、无真实 Run 不能保存标记 | Passed |
| Web 点赞、预设与管理员回看继续可用 | DOM、HTTP、PG | 前端 API、feedback store、admin list | unit、5173 浏览器交互、PG 回读 | 回读不覆盖新保存、空说明仍可提交 | Passed |

已执行证据：

- 相关授权与 Skill 单测：30 passed；覆盖空工具/Skill、无 Run 的注册、重复选择、基础工具不被 Skill 隐藏，以及无 Run 拒绝实际写入。
- `docker compose exec -T api uv run --group test pytest test/integration/api/test_agent_feedback_api.py test/integration/services/test_agent_feedback.py test/integration/services/test_schema_migration_version.py -q`：38 passed。HTTP 文件独立命名，避免与 service 同名测试一起收集时的模块冲突。
- `docker compose exec -T api uv run --group test pytest test/e2e/test_agent_feedback_e2e.py -m e2e -q`：2 passed，真实 worker 在空 tools/skills 配置下记录标记并完成任务；无效原因不持久化。
- `docker compose exec -T api uv run --group test pytest test/unit -m 'not slow' -q`：2676 passed，55 skipped；跳过项不作为本次验收证据。
- 前端 `pnpm run lint:check`、完整 `pnpm run test:unit` 与 `pnpm run build`：通过。
- `feedbackPresets.js` 在真实 5173 页面完成预设、文字、总长度限制与管理员详情验证；`feedbackNavigation.js` 完成迟到保存不重开、刷新恢复、详情关闭、离页及销毁标签后的迟到查询不导航验证。两份脚本使用 Web 反馈地址，原会话仍使用现有 Public Session 地址。
- Python changed-file Ruff check 与相关新文件 format check：通过；容器缺少 Ruff 可执行文件，使用仓库锁定的 Ruff 0.16.4 在宿主机检查。
- 工程信任检查与其 64 项单测通过；`cd docs && pnpm run build` 通过，保留完整链接校验。

HTTP 用例通过独立 fixture 创建共享 Agent，按该固定 ID 创建产品与 APP 测试会话，并在 teardown 删除 Agent，不读取现有目录的首项；修正后同一 HTTP 集合 6 passed。
