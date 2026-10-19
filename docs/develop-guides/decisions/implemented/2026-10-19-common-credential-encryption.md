# 通用凭据密钥与固定 MCP 回调路径

状态：implemented
类型：simplification
Owner：backend/yuxi/infrastructure/crypto.py

## 问题

MCP 为持久凭据单独引入加密密钥和完整回调 URL 配置。加密密钥属于部署基础设施；完整回调 URL 又要求部署重复填写代码已固定的路径。

## 决策

### 实现方案

`YUXI_ENCRYPTION_KEY` 替换 MCP 专用密钥，由 infrastructure 中的单个函数读取 Fernet 密钥，MCP 拥有凭据载荷及领域错误语义。公开站点来源由 `runtime_settings` 读取 `YUXI_PUBLIC_URL`，只允许无路径、query、fragment 和用户信息的 HTTP(S) 来源；MCP 拼接代码固定的回调路径后执行已有 HTTPS/实验来源检查。不引入密钥注册、派生、轮换或兼容回退机制，不改动 JWT、API Key、OIDC 登录与实验 HTTP 白名单。

## 替代方案

复用 JWT/API Key 密钥会耦合不同用途及生命周期；继续按模块配置增加部署表面；从请求 Host 推导回调则改变当前信任边界。选择通用配置及固定代码路径。OIDC 的现有配置不属于本次范围，未来消费者可以使用相同基础设施配置，不增加模块专用密钥。

## 后果

按全新配置部署通用 Fernet 密钥与公开站点来源，不提供旧变量、旧配置或旧数据迁移支持。缺失或错误密钥继续明确拒绝个人授权；HTTPS 与实验 HTTP 限制保持。不自动修改私有环境或重建在线容器。

## 验证

- `docker compose exec -T api uv run --group test pytest test/unit/config/test_runtime_settings.py test/unit/services/test_mcp_oauth_config.py -q`：43 passed。当前凭据加密结果经独立 Fernet 解密及 JSON 解析核对；缺失、非法与错误密钥拒绝，JWT 不作为 fallback。公开来源拒绝路径、query、fragment、userinfo、非法端口与空白。
- `docker compose exec -T api uv run --group test pytest test/integration/services/test_mcp_oauth.py -q`：43 passed。真实 HTTP/PostgreSQL 的动态注册与授权码兑换分别核对相同固定回调，覆盖个人工具、断开、并发刷新和撤权。
- 旧能力不存在：生产读取与默认模板不再使用 `MCP_OAUTH_ENCRYPTION_KEY`、`MCP_OAUTH_REDIRECT_URI`，不增加旧变量 fallback，当前配置文档不提供旧名称迁移说明。
- 重新引入条件：只有明确独立部署或回调路径契约证明通用配置不足时，才重新评估模块专用配置。
- 未验证范围：未修改私有部署环境，未重启在线服务，也未执行外部供应商浏览器或 worker E2E。

- 完整后端 unit：2902 passed、97 skipped；最终相关 unit 复验 43 passed。Ruff、工程信任检查及其 66 项单测、文档构建与 diff 检查通过，独立审查无阻塞项。
