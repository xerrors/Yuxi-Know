# 独立认证部署与真实 IdP 验证

状态：implemented
类型：architecture
Owner：docs/advanced/third-party-auth.md

## 问题

通用 OIDC/MCP 客户端需要真实 IdP 互通证据；在平台仓库维护多套 Keycloak 模板和考勤实验部署又会混淆认证入口、数据与运维责任。

## 决策

### 实现方案

固定版本 Keycloak、独立 PostgreSQL、私有配置生成器和虚构员工考勤示例归私有项目 [YuxiAuth](https://github.com/xerrors/YuxiAuth)；Yuxi 保留标准 OIDC/MCP 客户端、平台业务验收和接入文档。浏览器与 API 使用同一可达 issuer，认证数据库与平台数据库分开。实际认证入口、代理、网络和持久化拓扑由认证项目的部署配置拥有，Yuxi 不携带实验 Compose 或按环境增加授权分支。

主企业与测试 realm 保持身份目录隔离，平台以 issuer+subject 关联账号，不按用户名自动合并。实验客户端使用 confidential 授权码、PKCE S256、准确的登录/退出回调与 back-channel 配置，关闭密码直授、隐式授权和服务账号。首次登录创建普通用户，重登复用身份；协议与会话安全由 [OIDC 安全决定](./2026-10-13-oidc-production-boundaries.md)拥有。

认证服务切换由其部署 Owner 备份数据库、签名密钥、身份映射、私有配置与考勤记录；受控更新准确旧 issuer 的映射时保留 subject 和内部 user_id，并撤销旧会话。平台升级与认证部署分别验证。考勤 MCP 使用标准个人授权，资源端验证签名、issuer、audience、scope 和 subject；浏览器只访问认证入口，资源工具由后端请求。

## 替代方案

自制 OAuth mock 不能证明真实 IdP 互通；建立完整 IAM、SCIM 或企业目录超出客户端接入范围。IDaaS 免费版不支持所需自研 OIDC；保留两套 Keycloak 增加入口与运维责任，按用户名跨 realm 合并不能证明身份。选择独立认证项目和同一套标准客户端。

## 后果

认证服务变更在 YuxiAuth 执行；Yuxi 工作树不拥有部署生成器及其测试。生产认证需要 HTTPS 与证书验证；HTTP/start-dev 仅适用于隔离实验，虚构员工结果不代表真实员工生产验收。realm 导入不会自动更新已有客户端，目录停用与标准会话登出分别验证；入口切换后旧会话或资源授权需要重新建立。

## 验证

以下为独立认证与平台接入阶段已记录的历史证据，文档合并未重新部署或访问认证服务。

- Keycloak 管理 API 回读 confidential 授权码、强制 S256、准确登录/退出与 back-channel 地址；真实浏览器登录后回读普通角色、部门与稳定用户 ID。错误密码、禁用员工拒绝登录；平台退出及管理端结束会话后，旧 JWT 均返回 401。
- 私有生成器验证文件权限、准确回调、拒绝覆盖已有凭据与仓库内运行目录；迁出阶段生成器 6 项、签名/持久考勤 7 项测试通过。Yuxi 的旧部署目录与生成器测试移除，私有仓库 visibility 回读为 private。
- 认证数据库恢复与备份逐条核对身份的 id/subject/user_id 保留，旧服务停止且原 volume 保留；真实 Chromium 完成平台登录、资源授权和失败登录反馈，保留默认 TLS 校验。
- 平台早期真实 API/worker 考勤与三角色浏览器证据见 [MCP 历史验收](../../audits/mcp-main-e2e-2026-10-18.md)。早期 Notion 只读结果不计入最终供应商验收，停止的配置不恢复；当前 MCP 行为和最新测试范围见 [个人授权与运行边界](./2026-10-18-mcp-personal-oauth.md)。
