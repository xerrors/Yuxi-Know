# OIDC 登录的协议、身份与会话边界

状态：implemented
类型：architecture
Owner：backend/yuxi/modules/identity/services/oidc.py

## 问题

OIDC 基线仅交换 access token 并读取 UserInfo，缺少 ID token、PKCE 与浏览器关联验证，短期 state/code 只在单进程可用。以 sub 或同名账号识别身份、自动恢复注销用户和无撤销的本地 JWT 不满足企业登录安全要求。用户要求保持实现简单，完成真实联调、审查、提交并部署；公网 OIDC 在 HTTPS 就绪前保持关闭。

## 决策

### 实现方案

协议客户端统一通过 discovery 校验 issuer 和端点，通过 JWKS 验证允许的非对称签名及 ID token 的 iss、aud、azp、exp、iat、nonce、sub 和可选 at_hash，UserInfo 的 sub 必须一致。所有授权使用 PKCE S256，生产配置要求 HTTPS，开发联调允许明确的开发环境 HTTP。远端网络和解码均有界，错误不暴露 token 或原始响应。

Redis 保存带 TTL 的 state/登录结果，HttpOnly SameSite=Lax cookie 绑定浏览器，Lua 原子核对及消费 state。结果兑换可在短 TTL 内重试，但每次核对 PostgreSQL 的账号和会话，注销、退出和过期不可恢复旧凭据。前端先清回调 URL，再应用响应；离页或切换会话后忽略迟到响应。

PostgreSQL 保存 OIDCIdentity 的 issuer+subject 唯一映射以及 OIDCSession 的本地会话，API 认证依赖逐次核对 OIDC 会话有效性。自动开户只创建普通用户，不按同名或邮箱绑定、不恢复已删除账号。Schema 升级为 11；当前数据库直接调整到目标结构；代码不提供旧 OIDC 自动迁移或历史绑定推断。保留本地密码登录作为独立入口。

退出首先撤销本地 OIDC 会话，再提供认证中心 end_session 跳转。Back-channel logout 校验签名和专用 logout claims，持久记录事件并撤销匹配会话；事件也阻止进行中的旧认证在登出后发布。该机制依赖 IdP 发送标准通知，不提供 SCIM 或对目录停用事件的轮询。

## 替代方案

- 仅增加签名验证：不能闭合登录 CSRF、跨实例、身份冲突及退出后的访问边界。
- 引入完整认证平台 SDK 与通用插件层：现有 PyJWT/httpx、Redis 和 PostgreSQL 可完成一条线性 OIDC 流程。
- 根据邮箱或原始用户名自动合并：缺少当前本地账号持有证明；存量映射由部署者核对后直接处理。
- 每个 API 请求访问 IdP：增加远端依赖且不能通用于所有 Provider；采用本地有期限的会话和标准登出通知。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| 只接受受信任的 OIDC 身份 | 签名、claims、discovery | 协议客户端 | 签名 fixture 与真实 Keycloak | 错 issuer/aud/nonce/sub/过期/伪造 token | Passed |
| 登录属于原浏览器且跨实例可用 | CSRF、重放和进程内状态 | OIDC service 与 Redis | 实际 HTTP/Redis | 错浏览器、state 重放、过期拒绝 | Passed |
| 身份隔离且注销不可复活 | 错提供商、同名合并、软删除 | identity repository 与 Schema | 真实 PostgreSQL | 同 sub 不同 issuer、已删除账号、并发开户 | Passed |
| 登录结果和会话可以撤销 | 丢响应、晚回调、重放 | session/登出事件持久化与认证依赖 | HTTP/PG/Keycloak | 退出后旧 JWT、错签名通知、登出中晚回调 | Passed |
| 回调与日志不暴露凭据 | 浏览器生命周期、代理和访问日志 | 前端与 Nginx/middleware | unit/browser/代理探针 | 离页后晚响应、编码路径与错误响应 | Passed |
| 可部署且兼容本地登录 | Schema 与主工作区集成 | models/Compose | 新基线、旧版本拒绝、密码登录、ready | 未准备目标表结构时拒绝启动 | Passed（隔离环境）；主工作区在提交后部署 |

## 后果

原始用户名自动合并能力移除，现有数据库结构和绑定由部署者明确处理；主工作区保留本地登录。IdP 停用不等于标准登出通知，未发通知时本地会话在自身到期前有效，文档明确管理员应撤销 IdP 会话或停用 Yuxi 用户。公网 OIDC 不在 HTTP 入口启用；HTTPS 代理、生产 IdP 发布由后续明确环境配置负责，不以本次开发 HTTP 联调冒充。


实际证据：

- 独立 PostgreSQL 16 临时实例、真实 Redis 与 TCP HTTP 执行 `pytest test/unit/services/test_oidc_service.py test/integration/services/test_oidc_login_transaction.py test/unit/server/test_oidc_access_log.py test/integration/services/test_schema_migration_version.py -q --tb=short`：67 passed。覆盖两份 HTTP API 实例共享事务、签名/声明错误、同名及跨 issuer 隔离、旧 JWT、注销/锁定、状态重放、密钥轮换、事务回滚、sid 签发时序及 sub-only 通知。测试数据库使用 tmpfs，不证明磁盘故障恢复。
- 前端 `pnpm run lint:check`、`pnpm run test:unit`、`pnpm run build`：Passed，581 项 unit，包括回调 URL 清理、迟到兑换与站外跳转拒绝。`frontend/test/browser/enterprise-login.playwright.js` 在真实浏览器验证可选登录入口。
- `python3 scripts/verify_oidc_proxy.py`：真实 Nginx 成功/故障回调、编码路径及 Referer 脱敏通过，响应带 no-store/no-referrer。
- Keycloak 26.8.0 真实浏览器登录保持用户 ID、角色和部门；UI 发起 RP logout 后浏览器清除凭据且旧 JWT 401；管理端结束会话后远端会话归零，back-channel 通知使本地旧 JWT 401。实验账号凭据仅存在私有运行目录。

公网 HTTPS、生产 IdP、跨进程故障恢复及 SCIM 目录同步未在此环境验证。HTTP API 副本测试运行于同一测试进程，证明实例不依赖私有 state，但不替代真实多机故障测试。主工作区按用户要求保持 OIDC 关闭，不以开发 HTTP 的互通结果冒充公网生产启用。

用户要求先完成功能并停止后续测试，最终历史整理后没有重跑全量测试。上述 Passed 只表示已实际执行的相关结果；最终全量后端回归中断，文档构建在文件整理期间中断，均不计为通过。
