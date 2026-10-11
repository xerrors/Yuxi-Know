# Web 反馈接口

本页供 Web 产品集成和平台管理员查阅反馈采集的身份、请求与保留规则；不属于 Public API 协议。

## 反馈采集

反馈是 Web 产品功能，所有接口只接受产品 JWT，拒绝 API Key；Public API 不提供反馈路由。用户评价只接受自身产品会话的终态 Turn，且 `run_id` 必须等于该 Turn 的 `yuxi.result_run_id`，拥有明确的最终助手输出。等待、中间 Run 和无最终回答的错误返回 `409`，未知或越权目标返回 `404`。反馈直接提交 PostgreSQL，不创建 Input、Turn 或队列任务。

| 接口 | 输入与结果 |
| --- | --- |
| `PUT /api/agent/threads/{thread_id}/turns/{turn_id}/feedback` | 完整当前值 `{run_id, rating, reason}`；rating 为 `like` 或 `dislike`，reason 可省略或为 null，去除首尾空白后最多 2000 字符；提交后返回记录 ID 和持久值 |
| `DELETE /api/agent/threads/{thread_id}/turns/{turn_id}/feedback?run_id=…` | 撤销当前用户评价，合法目标重复撤销返回 `204`；Agent 标记保持保留 |
| `GET /api/agent/threads/{thread_id}/feedback` | 自身会话的记录，source 可为 `user` 或 `agent`；重复参数 run_ids 最多 100 个；limit 为 1–100，after 使用上一页 last_id |

反馈列表返回 `{items, has_more, last_id}`。每条记录包含来源、评价或原因、UTC 时间、Agent、Session/Turn/Run 标识和 Run 当前状态。游标必须属于相同身份与过滤条件，否则返回 `400`。每个 Run 保留一份当前用户评价，重复完整状态写入不增行；多个客户端并发修改采用最后提交值，不保留点击历史。归档保留记录，删除会话后查询隐藏记录。

`GET /api/system/agent-feedback` 仅允许产品 JWT 的 `superadmin` 集中查看，可按 agent_id、source、rating 筛选并使用相同分页；普通 `admin`、Agent 管理者和所有 API Key 均被拒绝。列表不返回原始对话、manifest 或私有 Skill 元数据，也不扩展原会话、审计或文件权限。

Agent 可通过[改进标记工具](../agents/tools-system.md#内置工具-记录改进线索)记录流程纠正或经验候选。保存反馈只完成采集，后续复盘和 Skill 更新需要独立流程。
