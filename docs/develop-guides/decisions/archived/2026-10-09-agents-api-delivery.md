# 2026-10-09 Agents API 对齐交付记录

状态：archived
类型：feature
Owner：backend/yuxi/api/routers/public_v1/agents/threads.py

## 问题

公开会话协议、附件提交和三端客户端需要对齐，并验证配置冻结、等待恢复、查询分页和最终结果归属。

## 决策

当日按资源契约、生命周期、附件、查询恢复、整体验收五部分完成协议对齐。内部 Thread/Input/Turn/Run 保留持久事实，Web、CLI、Demo 直接消费公开字段。此记录保存原实施计划中的交付证据；当前契约由 [Public API 参考](../../../advanced/agents-public-api.md)维护，后续事实归一见[对应决定](../implemented/2026-10-09-agents-owner-simplification.md)。

## 替代方案

保留旧接口兼容层或由客户端将 Session 转回旧 Thread 形状，会持续维护重复协议与状态，因此当日采用三端同步调整。

## 后果

历史测试数量、临时环境和未验证范围只对应当日实现，不是当前版本的质量或兼容性承诺。

## 验证

以下结果保存自原实施计划，记录日期为 2026-10-09，本次文档整理未重新执行这些历史用例。

| 验证层级 | 实际结果与可观察事实 |
| --- | --- |
| 后端全量 unit | 2571 passed、55 skipped；结果包含独立审查后的有界清理修复。 |
| 真实 PostgreSQL、HTTP 与 OpenAPI | 查询/分页/回执 17 passed；清理及受影响逻辑 51 passed，首批已提交来源保留、后批过期 draft 被删除，缓存游标丢失可重复扫描。 |
| 真实 worker / SSE | 生命周期、SSE、配置及附件共 21 项；两处旧 running 断言改为公开 in_progress 后，相应 3 项重跑通过。FIFO 回执、Redis 事件到期后的指定 Turn 恢复及相邻 Turn 游标拒绝均回读持久事实。 |
| Web | 最终全量 517 passed；审查修复专项 27 passed；lint/build 通过。真实浏览器上传 draft、消息响应丢失后 1 POST/1 receipt 恢复、SSE 连接失败、刷新后仍展示目标结果。 |
| CLI | 15 passed，typecheck、打包检查通过；真实客户端验证附件、响应丢失与 SSE EOF 恢复、两个 Turn 的结果归属和双页查询。 |
| Demo | unit 13 passed，浏览器 18 passed，lint/build 通过；真实浏览器验证两轮持久结果、回执恢复、SSE 故障、用户与 APP 隔离，附件回读 Input 关联和原件字节。 |
| 工程契约与文档 | engineering contracts、64 项 gate 单测、docs build 和补丁空白检查通过。 |


未验证范围：官方 SDK 完整调用属于 P1；外部视觉/非视觉模型探针 2 skipped，未把确定性模型验收写成外部模型能力通过。三端未确认请求与 SSE 游标只在当前客户端生命周期内保存；重载后依据持久 Session/Input/Turn 恢复，不宣称保存未确认草稿的跨重载恢复。当前 MinIO 清理由上传逐批触发，不承诺无人上传时自动物理删除。
