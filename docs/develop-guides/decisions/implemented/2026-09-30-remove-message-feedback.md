# 移除消息反馈能力

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/services/checkpoint_messages.py

## 问题

消息点赞和点踩原先会保存到数据库、同步 Langfuse，并在 Dashboard 展示统计和详情。该功能不再提供，保留可写、可读入口会继续承诺无效的产品行为。

## 决策

消息级旧反馈 API、点踩原因弹窗和满意度统计保持移除。基于最终 Run 的赞/踩、Agent 改进标记及平台管理员只读列表由[反馈采集决定](2026-10-11-agent-feedback-collection.md)拥有；该决定部分取代此处的聊天按钮占位与产品列表范围。

后端删除消息反馈路由与 service、MessageFeedback ORM、ConversationStats 中无调用方的 user_feedback 字段、消息 History 反馈字段、Langfuse 用户评分 helper，以及 Dashboard 反馈查询、统计和响应字段。ORM fresh schema 因此不再创建 `message_feedbacks` 表。没有旧库数据迁移；已有部署中的相关表或列可继续留存，但应用不再访问。

### 实现方案

Public Agent capabilities 不注册旧消息反馈路由，agent service、Message/ConversationStats 映射及 Langfuse 评分入口不包含旧写入、读取和序列化。旧反馈统计和对应响应字段保持移除。聊天和管理列表的当前采集行为由新的 feedback service/repository 及[反馈采集决定](2026-10-11-agent-feedback-collection.md)维护。

## 替代方案

- 只隐藏或禁用按钮：仍会留下可直接调用的后端写入、读取与统计 API。
- 只删除 Dashboard：仍会保留消息反馈存储、History 数据和 Langfuse 副作用。
- 为已有部署加入删除迁移：会扩大本次变更的数据操作范围；应用不再读取旧表后没有必要。

## 后果

- 最终回答的按钮采用新采集流程，行为见[反馈采集决定](2026-10-11-agent-feedback-collection.md)。
- History、原 Dashboard 统计和 Agent analytics 不返回旧消息反馈字段。
- 新创建的 Schema 不包含 `message_feedbacks` 和 ConversationStats 反馈列；新采集使用独立的 Run 反馈表。旧数据库中的遗留表/列不再由应用映射或访问。
- 依赖旧 HTTP endpoint 或私有响应字段的外部客户端需要停止使用。

## 验证

以下记录 2026-09-30 移除旧消息反馈的历史验证，不作为当前采集行为的证据。当前按钮、存储与管理列表的验证由[反馈采集决定](2026-10-11-agent-feedback-collection.md#验证)维护。

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 两个按钮保留并只显示开发中提示 | handler 发请求或写入状态 | `frontend/src/modules/session/ui/RefsComponent.vue` | 阅读两个 handler 与模板；`rg -n 'submitMessageFeedback|getMessageFeedback|messages/.*/feedback' frontend/src backend/yuxi` | 恢复任一调用或状态后命中旧 API 引用搜索 | Inspected：handler 只调用提示；旧 API 搜索无结果。Not run：页面点击验证，当前无登录态且 API 容器未启动，访问 `/agent` 被重定向到 `/login` |
| 后端不再有消息反馈读写、ORM 或 Langfuse 评分能力 | 路由、模型、History、score helper 残留 | `backend/yuxi/modules/agents/services/checkpoint_messages.py` | `rg -n 'MessageFeedback|message_feedbacks|submit_user_feedback_score|user_feedback' backend/yuxi` | 恢复映射或入口后命中旧能力搜索 | Inspected：搜索无结果 |
| Dashboard 不再提供反馈端点、统计或界面 | endpoint、card、modal 或 analytics 字段残留 | `backend/yuxi/modules/system/dashboard.py`、`frontend/src/pages/DashboardView.vue` | `rg -n 'feedback_stats|total_feedbacks|satisfaction_rate|agent_satisfaction_rates|/feedbacks|FeedbackModalComponent' backend/yuxi frontend/src` | 恢复任一字段或组件后命中旧能力搜索 | Inspected：实现源码无结果；测试保留缺失字段断言 |
| 代码格式与前端构建可用 | 删除产生语法、格式或组件构建错误 | 受影响 Python 与 Web 源码 | `git diff --check`；`python3 -m compileall -q backend/yuxi backend/test scripts`；`docker compose exec frontend pnpm run lint:check`；`docker compose exec frontend pnpm run build` | 恢复非法语法或 lint/build 破坏后命令失败 | Passed：上述格式检查、Python 编译检查、前端 lint 和构建 |

旧能力不存在：应用不再提供旧消息反馈路由、旧表映射、Langfuse 评分同步或满意度统计；旧部署数据库可能保留未使用的数据表和列。

重新引入条件：独立 Langfuse 评分或满意度统计需要新的消费方、数据保留策略及明确 Owner；当前产品采集已由[反馈采集决定](2026-10-11-agent-feedback-collection.md)单独建立。
