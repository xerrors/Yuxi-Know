# Agents 公开资源与客户端直接消费

状态：implemented
类型：architecture
Owner：backend/yuxi/api/routers/public_v1/agents/schemas.py

## 问题

同一 Session 的创建、列表、更新和展示操作使用不同响应形状，接收回执覆盖业务状态，HTTP 与 SSE 的 Turn 字段不同。客户端在 HTTP 边界把 Session 扩展还原为旧 Thread，增加了需要记忆和维护的解析规则。

本记录拥有[机制对齐方案](2026-10-09-agents-api-mechanism-alignment.md)第一步已生效的资源决定，部分取代[核心子集决定](2026-10-09-agents-session-protocol.md)。配置完整快照与取消清理由[配置及取消决定](2026-10-09-agents-session-lifecycle.md)拥有；附件由[附件提交决定](2026-10-09-agents-draft-attachments.md)、分页与恢复由[查询恢复决定](2026-10-09-agents-query-recovery.md)拥有；整体验收见[对齐交付记录](../archived/2026-10-09-agents-api-delivery.md)。

## 决策

创建、详情、列表元素、POST 更新、已读、归档及 Session 相关资源读取使用同一 Session 模型；持久内容通过 Items 分页；搜索将该资源放在命中的 session 字段，匹配片段独立返回。Session 核心表达身份、Agent、工作状态和时间；Yuxi 展示、队列、等待点与归档标记显式列入扩展。创建回执放在 yuxi.receipt，事件提交返回相同回执模型。

Session 的工作状态直接表达最近 Turn 的状态；是否可以继续接收输入由等待点与队列门禁决定。该状态投影由[事实归一决定](2026-10-09-agents-owner-simplification.md)拥有，取代本记录的失败转 idle 决定。取消清理中的 Turn 核心状态保持 in_progress，Yuxi cancelling 表达清理进度。HTTP Turn 与 SSE turn 使用同一核心投影，结果归属、输出、等待点、Run 和 Yuxi 用量位于扩展。首次执行时间从该 Turn 的 Run 持久事实读取，恢复不重置起点。

模型覆盖在创建/更新使用 agent.model，在消息事件使用 yuxi.model。内部执行直接读取完整配置快照的 model；唯一配置来源由[事实归一决定](2026-10-09-agents-owner-simplification.md)拥有。更新未提供模型时保持原值，显式 null 被拒绝。

### 实现方案

Public schema 与 routers 拥有 HTTP 契约和字段装配；agents services/repositories 继续拥有授权、Input/Receipt、Turn/Run 和持久结果。共享 turn_core 只投影明确的 Turn、Run 与首次开始时间，不推测相邻执行结果。创建 SSE 从独立回执读取 event_id，再输出同一 Session 资源。

Session repository 按授权用户、APP、创建时间与 ID 做有界 cursor 查询；service 批量读取当前工作、队列数量和活动事实，列表不逐项加载完整历史。活动时间包含每次持久 Receipt，因此聚合 steer 也推进活动；展示更新不推进活动。is_pinned 是有当前 Web 消费者的筛选，Web 独立分页取齐置顶资源并合并展示，普通列表 cursor 不受置顶、归档或创建影响。

Web、CLI 与 Demo 的 API 层返回公开资源，调用方直接读取 core 和 yuxi，持久内容通过 Items 分页。产品私有“历史目录候选”继续使用自身目录 DTO。HTTP/E2E 和客户端 fixture 按新 wire 编写，保留业务断言，不通过逆向包装旧对象维持解析。

## 替代方案

- 在 API 边界把 yuxi 解包回旧 Thread：减少局部字段改动，但保留两套公开结构、状态别名和长期维护负担。
- 列表继续 offset 且总是附加所有置顶：请求数量少，但分页计数和资源数量具有额外规则。采用稳定 cursor 和明确的置顶筛选。
- 失败转 idle 可表达会话仍可接收输入，但会隐藏最近工作的结果；[事实归一决定](2026-10-09-agents-owner-simplification.md)选择直接投影最近 Turn，输入门禁独立判断。

## 后果

这是直接替换公开协议的改动：PATCH、旧字段、旧扁平响应和客户端还原包装移除，没有历史数据或平台兼容路径。三端字段、状态和测试消费在同一范围修改。置顶保证增加独立查询，但每页有界且与普通分页边界分开。Session 配置冻结和等待取消由配置及取消决定拥有；本记录保留原资源阶段的决定，当前完整专项与验收由[事实归一决定](2026-10-09-agents-owner-simplification.md)拥有。

## 验证

环境为开发 Compose 的真实 HTTP、PostgreSQL、Redis、worker 和 provisioner；模型使用本任务启动的确定性重放服务。验证以资源、数据库结果和 DOM 回读为依据，SSE 由调用方观察目标 Turn 终态并主动关闭。

| 实际命令 / 检查 | 结果 |
| --- | --- |
| `docker compose exec -T api uv run --no-sync --group test pytest test/unit -m 'not slow' -q` | 2568 passed，55 skipped |
| resources、items、key boundary、Turn 结果、chat router、Project 与 Viewer 九文件 HTTP integration | 47 passed；覆盖新资源、旧字段/PATCH 拒绝、跨用户 cursor 拒绝、聚合 steer 时间和首次执行时间 |
| initial input、concurrent create、tool cycle、answer resume、preloaded audit 五用例 worker E2E | 7 passed；包含字符串、多块文本、创建 SSE 与 HTTP 终态核心一致、结果绑定和回答后恢复 |
| Web `pnpm run lint:check`、`pnpm run test:unit`、`pnpm run build` | Passed；512 unit passed；最终 `node --test test/unit/chatThreadsStore.test.js` 为 9 passed，覆盖首屏外置顶、独立 cursor 和迟到状态页不覆盖改名 |
| Web 真实浏览器与 HTTP 回读 | 列表、改名、置顶、归档和活动时间验证通过，无页面异常 |
| CLI `npm run typecheck`、`npm test`、`npm run pack:check` | Passed；10 tests；pack 为 dry run |
| CLI Client/ChatSession 对真实 HTTP、worker、SSE 与 Turn 回读 | Passed；接收明确 Turn 终态、主动结束订阅并回读其结果 |
| Demo `npm run lint`、`npm test`、`npm run build`、`npm run test:browser` | Passed；13 unit，15 browser；browser 使用 mock HTTP |
| Demo 真实浏览器、两轮 worker 与持久 history 回读 | Passed；Session、最终正文、队列计数和当前 Turn 一致，无页面异常 |
| 运行中服务的 `/openapi.json` | Session 列表元素、独立回执、POST 更新和 Turn 核心字段验证通过 |
| `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts` | Passed；64 脚本测试通过，包含相对链接检查 |
| `cd docs && pnpm run build`、`git diff --check` | Passed |

`--no-sync` 复用 Compose 中已安装的测试依赖；默认同步触发 editable 安装的环境目录权限问题。测试缓存写入权限警告和前端构建的大 chunk 提示不影响上述结果。

配置完整快照与取消专项的独立通过证据见配置及取消决定，它们不属于本记录的第一步验证范围。本记录不覆盖附件、查询恢复与跨步骤验收，它们由上述专项决定及实施计划提供独立证据。Not run：官方 SDK 自动完成/收集结果。
