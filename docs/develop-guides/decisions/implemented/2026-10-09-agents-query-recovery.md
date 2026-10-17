# Agents 有界查询与结果恢复

状态：implemented
类型：feature
Owner：backend/yuxi/modules/agents/repositories/public_items.py

## 问题

Items 查询先加载整段 Message 再截页，Turn 缺少列表；组合 history 入口重复维护会话、执行段和内容。CLI 将没有增量正文的完成轮次视为失败，Web 的提交响应丢失可能导致重新生成幂等键。短期 Redis 事件无法承担最终结果恢复。

## 决策

### 实现方案

Session、Turn、Items 共用 `after/limit/order` 和 `object/data/first_id/last_id/has_more`。Items 在 PostgreSQL 展开已登记的公开 JSON 身份，按 Message ID 与公开索引执行游标过滤及 limit+1；同一 Message 内多个 item 可跨页。页面的 `yuxi.runs` 仅包含该页引用的轻量执行段，满足 Web 展示状态和耗时。Turn 列表批量查询当前 Run 与开始时间，不调用完整快照。移除组合 history 入口，三端直接读取资源与内容页。

回执查询复用现有 PostgreSQL Receipt，通过完整用户、APP、Session 与幂等键定位。创建响应丢失重放相同创建请求；消息响应丢失先查回执，并保留相同意图与键供再次重试。消费归属从 Input 读取，最终结果来自目标 Turn 的 result_run_id。SSE 使用 Last-Event-ID 续订；事件过期、断开或目标终态时回读持久资源，断流本身不表示完成。

Web 与 Demo 初始读取最新内容页并显式加载更早内容，刷新合并已加载内容而不删除老页。CLI 提供列表分页和回执查询，交互聊天在断线或 resync 时读取同一 Turn 的明确结果。公开参考及快速开始说明回执、游标与目标结果；整体验收采用真实 HTTP、worker 和三端故障注入。

## 替代方案

继续全量 history 降低短期改动但查询和重连成本随会话增长。新增公开 item 表需要增加写入事务与存储迁移；当前登记元数据已拥有稳定身份，直接 PostgreSQL 展开即可。以最近 Turn 或 SSE 正文推断结果不能满足排队、重连和相邻 Turn 的因果归属。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 有界双向分页不遗漏同 Message 内 item | SQL、游标、隔离 | public_items/turn repositories | 真实 PostgreSQL 与 HTTP 查询测试 | 他 Session/Turn/APP 游标拒绝，内部审计不返回 | Passed |
| 提交响应丢失不重复执行 | Receipt、客户端重试 | inputs service、三端提交 | HTTP/worker 与客户端故障注入 | 相同键不同意图拒绝，排队 Input 保持原归属 | Passed |
| SSE 断开或 Redis 过期仍能取得目标结果 | 事件、最终结果 | events/turns service、三端观察 | worker/SSE 与客户端恢复测试 | 相邻 Turn 终态不能结算目标 Turn | Passed |
| 完整三端流程与公开文档一致 | 调用方、OpenAPI | Web、CLI、Demo、公开参考 | 三端 gate、真实页面、HTTP/worker、docs build | 旧入口返回 404 | Passed |

实际证据：真实 PostgreSQL/HTTP 与 OpenAPI 专项 17 passed；worker 生命周期、SSE、配置及附件场景 21 项，修正旧状态断言后相应 3 项重跑通过。后端全量 unit 2571 passed、55 skipped。客户端、浏览器与文档的最终 gate 结果由[对齐交付记录](../archived/2026-10-09-agents-api-delivery.md)保存。命令使用 `uv run --no-sync --group test`，复用容器已安装测试环境；直接 sync 会触碰只读的 `yuxi.egg-info`。

## 后果

JSON 展开减少返回范围，长期超大会话仍可能需要独立索引表；只在真实查询性能证据要求时重新讨论。客户端保留已加载内容与未确认提交，占用内存，但无需新增服务端恢复状态或改变事务 Owner。外部模型与 OCR 可选能力的未执行范围需单独报告。
