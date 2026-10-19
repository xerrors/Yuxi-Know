# 接入独立 YuxiAuth 认证中心

本指南供 Yuxi 部署管理员接入已有认证中心。认证服务的 Compose、Keycloak 模板、私有配置生成器与考勤示例由独立私有项目 [xerrors/YuxiAuth](https://github.com/xerrors/YuxiAuth) 维护；需要该仓库访问权限。Yuxi 仅维护通用 OIDC/MCP 客户端。

## 配置登录

先按照 YuxiAuth 的 README 部署认证中心，为当前 Yuxi 注册独立 confidential 客户端、准确回调地址、PKCE S256 及 back-channel 登出地址。主企业 realm 与可选考勤测试 realm 分别管理身份，同名账号不会自动合并。

将 YuxiAuth 运行目录输出的 `.private/yuxi-oidc.env` 写入当前 Yuxi 的私有部署配置，按 [OIDC 配置参考](./third-party-auth.md)设置。可选考勤测试平台使用 `.private/attendance-yuxi-oidc.env`。API 与浏览器必须能访问完全相同的 issuer；OIDC 配置改变后重新创建 API，环境中显式变量会覆盖 env file。

共享测试入口可以使用固定服务器 IP 与端口，例如 `http://192.0.2.10:39090`，不需要域名或 hosts；示例 IP 需替换，服务器防火墙和云安全组须放行认证端口。`localhost` 指浏览器所在机器，不能作为其他机器访问共享认证的入口。HTTP 和虚构员工仅用于测试；真实员工生产接入使用可信 HTTPS。

## 验证与维护

使用两个不同员工从 Yuxi 登录页进入认证中心，验证回调后得到不同普通用户，重复登录保持各自内部 user_id。错误密码必须留在认证中心；本地密码登录继续保留。Yuxi 退出撤销本地会话，认证中心 SSO 会话按 [OIDC 账号边界](./third-party-auth.md)处理。

认证部署修改、客户端管理、数据库备份及恢复在 YuxiAuth 项目执行。不要在 Yuxi 工作树复制认证 Compose、挂载认证数据库或通过 Yuxi 前端代理认证路径。入口变化会改变 issuer，需先备份并精确迁移既有身份映射和撤销旧会话；不能按用户名重新关联身份。

考勤 MCP 接入和 worker 验收见 [MCP 集成](../agents/mcp-integration.md#企业考勤实验)。
