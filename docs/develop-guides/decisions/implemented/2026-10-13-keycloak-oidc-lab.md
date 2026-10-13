# 使用 Keycloak 联调企业统一认证

状态：implemented
类型：feature
Owner：docker/keycloak-lab/compose.yml

## 问题

企业部署需要对接已有统一认证中心。Yuxi 已有 OIDC 授权码登录，但缺少可复现的真实身份提供商环境和端到端互通证据。

## 决策

### 实现方案

以固定版本 Keycloak 和独立 PostgreSQL 提供专属测试 realm、confidential client 和虚构员工。仓库保存 Compose、无密钥的 realm 模板、私有配置生成器和操作文档；运行凭据保存在仓库外受保护目录。使用一个浏览器和 API 都可达的 issuer URL，明确登记 Yuxi 回调。认证数据库使用内部网络，API 只加入 Keycloak 的共享网络，避免同名数据库 DNS 混淆。HTTP 端口只发布在宿主 loopback，远程浏览器通过 SSH 转发和 hosts 访问。

Yuxi 通过 `OIDC_*` 配置和 identity 用例登录，首次创建普通用户并按 issuer+sub 复用账号。实验使用独立工作树、数据库和虚构员工；不按同名 uid 自动关联已有账号。

实验客户端强制 PKCE S256，并登记退出跳转与 back-channel 通知地址。协议和会话安全边界由[OIDC 安全决定](./2026-10-13-oidc-production-boundaries.md)拥有；实验不增加 SCIM、飞书成员同步、企业目录或 IdP 联邦。禁用和结束会话分别验证。

## 替代方案

- 自制 OAuth mock：无法证明与真实企业 IdP 的协议互通。
- 建立完整 IAM 平台：超出模拟认证中心并适配的需求；Keycloak 已提供管理界面和标准协议。
- 直接改主站认证：影响真实用户，独立测试入口可提供同样的验证。

## 验证

- 生成器四项单测验证私有文件权限、容器可读的占位模板、准确回调与登出配置、拒绝覆盖已有凭据及仓库内运行目录。
- 真实 Keycloak 管理 API 回读 confidential 授权码、强制 S256、准确登录/退出回调与 back-channel 设置。客户端关闭密码直授、隐式授权和服务账号。
- 真实浏览器完成员工登录，回读 Yuxi 的普通用户和部门，重复登录保持用户 ID；页面退出并在 Keycloak 确认后，浏览器回到登录页且旧 JWT 返回 401。
- 从 Keycloak 管理端结束虚构员工会话，管理 API 回读远端会话归零，Yuxi 旧 JWT 返回 401。错误密码和禁用员工的新登录留在认证中心并显示错误。

完整自动化命令、协议负向案例、代理日志和未验证范围由 [OIDC 安全决定](./2026-10-13-oidc-production-boundaries.md)记录。固定协议 fixture 验证数据库与并发边界，真实 Keycloak 浏览器验证互通，两类证据分别执行。

## 后果

HTTP 与 start-dev 仅用于隔离联调，不能用于真实员工和生产凭据。启动导入不会更新已有 realm，既有客户端需要同步准确的 PKCE 和登出配置。IdP 目录停用和标准会话登出是不同事件，目录同步、生产 HTTPS 与证书部署不在实验范围内。
