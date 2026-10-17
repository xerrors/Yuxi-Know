# 调试分组与反馈观测统一使用 Turn

状态：implemented
类型：feature
Owner：backend/yuxi/modules/agents/services/trace_links.py

## 问题

Langfuse 使用 Turn 级 Trace，调试面板却按 Run 分组和发起跳转，恢复与引导产生的执行段被展示为多个独立轮次。平台反馈来自不同用户，原会话入口受个人会话权限约束，管理员无法据此完成反馈复盘。

## 决策

### 实现方案

审计服务投影 Run 的真实 Turn 归属，并批量读取所属 Turn 的持久状态和起止时间。前端按 Turn 展示记录，保留 Run 明细及各段执行时间，不从邻近消息或 Run 推测归属。时间概览继续按 Run 执行窗口累计，选择与筛选归入所属 Turn。

Web 专用跳转接口由 agents 的 trace_links service 授权并读取 Turn 的持久 Trace。调试入口检查自身会话与 Turn，反馈入口按反馈记录关联原 Turn，允许平台超级管理员跨用户复盘。两个入口只接受超级管理员产品 JWT，拒绝 API Key；反馈查询排除已删除会话。返回 Turn 标识、Trace 标识与惰性解析的 URL，缺少 Trace 或配置时显式返回不可用。Langfuse 自身执行目标项目的访问控制。

## 替代方案

- 保留按 Run 分组：与实际 Trace 粒度不一致，恢复执行分散。
- 反馈跳回个人会话：无法满足跨用户复盘。
- 扩展个人会话权限：引入超出观测跳转所需的正文、文件与操作授权。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 同 Turn 多 Run 合组，零消息轮次可见 | 丢失恢复段或无消息 Run | messageDebug model、审计 service | 前端相关 unit 28 项、真实 HTTP 审计、浅深色及 1024px 浏览器 DOM | 同 Turn 有消息段与零消息失败段混合，选中后者窗口仍保留轮次 | Passed |
| 两入口定位同一 Turn Trace | 从相邻轮次借用 Trace | trace_links service、Turn repository | 自管 HTTP integration 2 项、前端交互 unit | 当前 Turn 无 Trace 且邻轮有 Trace | Passed |
| 反馈跨用户复盘只对产品超级管理员开放 | 普通用户、admin、API Key 越权或已删除会话可见 | Web dependency、feedback repository | 真实 HTTP 身份矩阵、内部替代调用 unit | 普通身份、两类 Key、已删除反馈和跨用户个人会话拒绝 | Passed |

直接命令为 `cd frontend && node --test test/unit/messageDebug.test.js test/unit/turnTraceNavigation.test.js`、`docker compose exec api uv run --group test pytest test/integration/api/test_turn_trace_links_api.py` 以及 `docker compose exec api uv run --group test pytest test/unit/services/test_trace_links.py test/unit/services/test_session_message_audits.py`。前端 lint、build、文档 build 与 Ruff 通过；后端全量 unit 通过 2703 项并跳过 62 项，新增身份边界 unit 单独通过。独立 Reviewer 复核后无阻断项。

工程契约检查及其 66 项单测通过，`git diff --check` 通过。前端全量 unit 为 644 项通过、1 项失败，失败项是未改动的 Markdown 宏原型污染用例；本决定涉及的调试和观测测试全部通过。

浏览器使用真实 HTTP 与 PostgreSQL 临时资源验证一个 Turn 包含两段 Run、Turn 跳转请求和无 Trace 提示。真实 Langfuse 项目中的页面展示未执行。既有 API 回归套件的全局清理 fixture 因历史 Workdir 被其他 Project 共享而拒绝运行；自管观测测试只回收各自创建的新用户、会话与项目。

## 后果

Langfuse 是可选服务，未配置或远端 URL 解析失败时无法跳转。审计保留既有 500 条上限，部分轮次可能只包含窗口内的执行记录；截断提示继续展示。
