# API 内置知识库 MCP

状态：implemented
类型：feature
Owner：backend/yuxi/api/routers/public_v1/knowledge_mcp.py

## 问题

外部客户端需要使用 API Key 检索知识库。MCP 与现有 API 共进程、共域名和端口，能够减少独立容器、HTTP 转发和重复部署维护。

## 决策

### 实现方案

FastAPI main 在 `/api/mcp` 注册无状态 Streamable HTTP 适配器，API lifespan 管理 MCP manager 的启动和关闭。MCP 进入失败阻止 API 接流量，并执行既有资源清理。使用后端已有 MCP SDK，无新增依赖或独立包。

协议适配器位于 `api/routers/public_v1/knowledge_mcp.py`，与 Knowledge Public HTTP 入口并列，统一对外知识库协议的源码归属。ASGI 路由与 lifespan 在 API 入口装配，MCP 地址为 `/api/mcp`。

每次 HTTP 请求复用 `get_current_user` 和 `get_required_user`，knowledge Key 的精确路径允许集合增加 `/api/mcp`；MCP 仍仅接受 Yuxi API Key。绑定用户、部门要求、Key 权限与撤销检查由原认证入口拥有。每次工具调用重新查询该身份的可见知识库，复用现有 Knowledge Schema 和五个只读服务。SDK 默认将异常内容返回客户端，适配层把业务错误和底层异常转换为稳定的 MCP isError 与状态码，避免公开内部诊断。

Host 白名单由 API 环境变量 `YUXI_MCP_ALLOWED_HOSTS` 拥有，默认允许本机与 Compose api 主机，拒绝浏览器 Origin。部署和客户端配置见[知识库 MCP 接入](../../../advanced/knowledge-mcp.md)。测试位于 backend 既有 unit/integration 目录，并由既有后端 CI 选择；没有专属依赖锁文件、Compose 或 workflow。

模型调用说明、结构化结果与安全恢复指引由[客户端体验决策](./2026-10-15-knowledge-mcp-client-experience.md)补充。

## 替代方案

- 独立 HTTP 转发服务保留现有 HTTP 边界，但需要额外容器、端口、连接池和重复鉴权请求。
- 在 API 内转发自身 HTTP 接口可以减少容器，但继续增加自调用和错误处理层。
- 直接复用业务服务使 MCP 成为与 HTTP 路由并列的薄协议适配器，权限与数据 Owner 保持不变。

## 后果

MCP 与 API 同步发布和启停，共用资源；服务故障不再表现为独立上游连接错误。模型可用的工具和资源范围保持原五个只读用例。`knowledge` Key 可以进入 MCP，但不扩大到其他 API 路径；`full` Key 仍受用户可见性约束，`agents` Key 与 JWT 被拒绝。

MCP 随 API 发布，OpenCode 使用专用 Key 连接 `/api/mcp`。独立服务需要明确的独立扩容或发布隔离需求。

## 验证

- `docker compose exec -T api uv run --group test pytest test/unit -m 'not slow'` 通过。MCP 协议测试覆盖 Schema、并发身份、可见性、无效/agents/撤销 Key、未绑定部门、未知工具、参数约束、Host/Origin、错误脱敏和启动失败清理；后端 workflow 运行完整 unit 集合。
- `docker compose exec -T api uv run --group test pytest test/integration/api/test_knowledge_mcp.py -q` 通过。Fixture 创建并回收 Key、用户、私有知识库与 PostgreSQL/MinIO 文档；MCP 回读结果与 HTTP API 相同，跨用户查询和原文读取被拒绝，JWT、agents、无效及撤销 Key 被拒绝。system-tests workflow 显式运行该测试，无专属 Key 或预存数据要求。
- SDK 和 OpenCode 实测完成工具发现、检索、原文读取与关键词定位，核对非空片段与对应来源；专用 knowledge Key 访问凭据管理 API 被拒绝。

运行验证使用开发 Compose。公网 HTTPS、跨机器代理和其他 MCP 客户端未验证。
