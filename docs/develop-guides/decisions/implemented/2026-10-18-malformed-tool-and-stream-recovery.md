# 无效工具调用与静默断线恢复

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/agents/services/checkpoint_messages.py

## 问题

演示中的模型返回参数无法解析的 `write_file`。图没有可执行的合法工具调用，最终 checkpoint 被当成正常完成。下一次输入由 PatchToolCallsMiddleware 为无效调用补入 ToolMessage，ChatCompletionsAdapter 移除畸形调用却保留其结果，供应商拒绝不配对消息。另一次服务重建后，页面读流长期不结束，未回读已经完成的持久 Turn。

## 决策

### 实现方案

checkpoint 消息结算服务拒绝用包含无效工具调用的最终 AI 结算正常完成，沿既有执行失败通道保存错误；不执行猜测修复后的工具参数。模型发送边界在保留失败文本的同时，仅移除同批已移除无效调用所对应的工具结果；合法调用及结果、真实孤儿结果、原始 checkpoint 保留。推理字段回填在这一 wire 过滤前完成，避免消息数量改变后错位。

前端 SSE reader 在持续 60 秒没有任何字节时结束失效订阅，进入既有 Turn 对账与 cursor 重连流程。服务器默认空闲心跳为 15 秒，正常长任务不会因没有模型正文而超时。终态仍只由 HTTP/SSE 的 Turn 事实确认，超时不取消后端任务。

## 替代方案

修改历史 checkpoint 或无差别丢弃所有孤儿结果会隐藏上游错误、损失审计。猜测畸形参数并执行会改变副作用。引入另一套自动恢复状态机或供应商重试配置没有必要；本方案复用已有失败与重连路径。

## 验证

注册 Adapter 的四个 HTTP 入口覆盖无效调用与补齐结果过滤，合法批次、下一 AI 复用 ID、跨 Human/System 的真实孤儿和推理字段分别验证。负向案例在旧实现下保留不配对结果；跨边界负控在过宽过滤时丢失原文。checkpoint 负向回归确认旧结算允许正常完成，修复后回滚并抛出明确错误。

`test_malformed_tool_recovery_e2e.py` 经真实 HTTP、worker 与 PostgreSQL 验证第一轮失败、同会话第二轮成功，回读原 checkpoint 保留 invalid 调用和补齐结果。该用例进入 `backend/test/run_tests.sh` 的确定性 E2E 集合。前端回归覆盖静默断线后终态历史、正常心跳、原 cursor 重连和停止后不再重连。

真实演示中，原先报 400 的会话使用原 checkpoint 成功继续，模型读取到已有数据。对产品页面仅替换一次 GET SSE 响应为无字节半开流，任务约八秒完成，页面约 60 秒后回读持久结果并显示完整回答，`performance.timeOrigin` 保持相同；没有刷新页面或变更任务状态。详细环境与未验证范围见[复跑审计](../../audits/demo-recheck-audit-2026-10-18.md)。

## 后果

无效最终调用会明确失败，由用户继续输入；不增加自动执行重试。60 秒字节空闲限制在服务器心跳被配置得更慢或后台页面被浏览器暂停时会多一次幂等重连；不变更 Run 状态和文件内容。保留原失败会话与文件作为证据。
