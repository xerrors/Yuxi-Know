# MCP 故障隔离与状态警告

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/extensions/mcp/service.py

## 问题

MCP 凭据密钥缺失、凭据不可解密或远程服务故障会在工具发现阶段终止整个 Agent Run，页面仅显示 TaskGroup 包装错误。用户需要在 MCP 未连接时继续使用智能体普通聊天，并知道具体不可用的能力。

## 决策

### 实现方案

MCP service 在单服务发现边界隔离异常并只返回已知安全原因。Context 的不可用服务用于本 Run 工具缓存和授权门控；普通聊天继续，失败 MCP 及相关 Skill 工具关闭。工具调用故障返回安全 ToolMessage，取消、图控制异常与外围身份检查继续传播。

图状态使用 `warnings: list[RuntimeWarning]`；RuntimeWarning 是包含 `code`、`source`、`message` 的 TypedDict，持久值为普通字典列表。Authorization 的模型前后节点从当前能力生成 warnings，后置节点覆盖动态 Skill 在本次模型装配阶段发现的故障；警告随 checkpoint 持久化，`extract_agent_state` 将它加入现有状态增量与回读响应。状态面板逐条展示 message，每次整体替换列表，下一轮能力恢复时写入 `[]` 清除旧警告。删除专用通知事件、弹窗消费、Context 的通知去重标记和模型提示拼接。

失败服务在同一 Run 不重复发现，新 Run 重新检查。管理页连接测试保留严格失败。

部署密钥由本地 env_file 持久配置，API/worker 使用同一 Fernet 密钥；密钥逻辑和 shipping Compose 保持现有契约。新密钥无法解密的旧连接需要重新授权，已有凭据保留。CI 的主 worker job 仅为隔离测试拓扑生成临时密钥，并实际执行故障 E2E。

本决定部分取代 [MCP 个人授权与运行边界](./2026-10-18-mcp-personal-oauth.md) 中 Context 不保存连接提示和网络错误终止整轮的策略。当前运行语义由 [MCP 机制](../../../mechanisms/mcp.md) 说明。

## 替代方案

保留独立警告事件需要重复维护发布、去重与客户端消费，且页面刷新后无法回读。只在客户端转换弹窗无法持久保存事实。复用图状态与现有状态面板缩小实现范围，并保留故障隔离和实际出站授权。


## 后果

本 Run 内失败 MCP 及其依赖暂不可用，用户修复连接后在新 Run 重新发现。单服务发现/调用捕获边界外的共享数据库、身份及 Agent 授权查询失败会让运行失败；MCP 出站回读发生在单服务捕获边界内，其故障按该服务不可用处理。状态警告和错误工具结果只包含固定业务原因，不包含任意底层异常文本。

## 验证

旧能力不存在：生产代码不再发布或消费 `capability_limited` 事件，不再保存 `_capability_warning_sent`、`_last_capability_warning` 或 `_authorization_turn_id` 通知标记；MCP 警告不调用 message.warning。

重新引入条件：出现无法由 checkpoint 状态表达的独立通知消费者时，另行裁决通知协议。

相关 unit 验证单服务隔离、安全原因、工具门控、控制异常传播、多条 warnings 的状态投影与下一轮清空。真实 API/worker E2E 验证直接 MCP 与预加载 Skill 的未连接、错误密钥、网络拒绝，回读 PostgreSQL checkpoint 状态并核对普通状态增量。前端通过 lint、unit、build 和真实页面检查验证状态面板展示。

本地验证：后端全量 unit 2938 passed、99 skipped，列表状态相关 unit 22 passed；独立运行 `test/e2e/test_mcp_failure_isolation.py` 为 6 passed。前端 lint、741 项 unit、生产 build 与文档 build 通过；新增列表模板测试后，相关文件 11 项测试通过，覆盖两条消息、安全转义和空列表，工程契约检查及其 66 项测试通过。真实浏览器验证错误密钥时普通回复完成、警告显示、刷新回读及无弹窗；多警告及恢复后清空由真实图的同线程两轮 checkpoint 测试证明。独立 Reviewer 复核通过。

外部真实 OAuth 浏览器重新授权与真实供应商模型探针未执行；E2E 模型使用确定性 HTTP replay。远端 GitHub Actions 尚未执行，本地验证不代表远端 CI 通过。
