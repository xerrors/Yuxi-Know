# Agents API 维护索引

本页供修改 Agent API、Web、CLI 或 Demo 的维护者定位契约和验证入口。对外接入从 [Agent API 入门](../intro/agents-api-quickstart.md)开始，字段、事件及兼容边界以 [Public API 参考](../advanced/agents-public-api.md)为准。

## 当前契约与实现

| 维护内容 | 先读文档 | 实现位置 |
| --- | --- | --- |
| Session、Turn、Items、HTTP 与 SSE | [Public API](../advanced/agents-public-api.md) | `backend/yuxi/api/routers/public_v1/agents` |
| Input 接收、FIFO、steer、等待与取消 | [请求队列](../mechanisms/agent-request-queue.md) | `backend/yuxi/modules/agents/services`、`repositories` |
| 配置快照、执行归属与最终结果 | [运行时上下文](../mechanisms/agent-runtime.md) | Agent runtime 与 Session 资源投影 |
| 图片、附件和草稿文件 | [API 文件契约](../advanced/agents-public-api.md)、[文档处理](../advanced/document-processing.md) | Agent 附件 service、repository 与 workspace 文件边界 |
| API Key、用户与 APP 可见性 | [API Key 接入](../advanced/api-key-integration.md)、[资源权限](../mechanisms/resource-permissions.md) | identity 依赖和各域可见性查询 |
| Web、CLI 与 Demo 消费 | [CLI](../intro/cli.md)、[API 入门](../intro/agents-api-quickstart.md) | `frontend/src/modules/session`、`packages/yuxi-cli`、`packages/agent-demo` |

HTTP 与 SSE 共用 Session 投影。持久输入、Receipt、Turn、Run 和最终输出分别拥有明确归属；客户端直接消费公开字段，不维护旧 Thread 响应的另一套状态。具体时序与失败恢复由上表专题解释。

## 修改与验证

先定位真实 producer、协议适配与调用方，再选择[测试规范](./testing-guidelines.md)中的证据层级。协议或公开状态变化需要同时核对 Web、CLI、Demo 和 OpenAPI；接收、队列、附件或恢复变化需要真实 PostgreSQL、HTTP、worker/SSE 与最终持久结果，不能仅以单元测试代替。

结果必须读取目标 Turn 的 `result_run_id`，断流后依据回执和持久资源恢复。SDK 是否结束调用不构成执行成功证据。当前支持范围和未实现字段由 [Public API 参考](../advanced/agents-public-api.md)维护，不在本页复制后续优先级。

## 决策与历史证据

- [资源契约](decisions/implemented/2026-10-09-agents-resource-contract.md)、[配置与取消](decisions/implemented/2026-10-09-agents-session-lifecycle.md)、[附件提交](decisions/implemented/2026-10-09-agents-draft-attachments.md)、[查询恢复](decisions/implemented/2026-10-09-agents-query-recovery.md)：各边界的选择与验证。
- [状态与附件事实归一](decisions/implemented/2026-10-09-agents-owner-simplification.md)：后续简化及三端验证。
- [2026-10-09 对齐交付记录](decisions/archived/2026-10-09-agents-api-delivery.md)：当日验收结果和未验证范围，仅用于追溯历史。

历史测试数据保存在交付记录中，当前验证命令见测试规范。
