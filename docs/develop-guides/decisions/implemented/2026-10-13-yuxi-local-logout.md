# Yuxi 退出只撤销本地凭据

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/identity/services/logout.py

## 问题

Yuxi 的退出按钮撤销本地 OIDC 会话后跳转认证中心 end_session，结束共享 SSO，影响同浏览器的其他产品。密码登录退出只清浏览器状态，旧 JWT 仍可访问。用户要求仅退出 Yuxi、下次可复用认证中心 SSO，并保留认证中心主动 back-channel 通知。

## 决策

### 实现方案

前端等待本地退出成功后清登录状态并 replace 到 Yuxi 登录页，不访问认证中心退出 URL。后端根据已验证 JWT 撤销当前 OIDC 会话，或持久撤销当前密码 JWT 的摘要；每次鉴权核对对应事实。新 JWT 带随机 jti，避免同秒登录得到相同凭据。撤销摘要和期限存 PostgreSQL，过期记录在退出时清理，不存原始 token。Schema 12 由部署者直接准备，不提供迁移程序。

back-channel 的签名验证、sid/sub 匹配及晚回调阻断继续由既有 OIDC 用例拥有。当前退出不调用 discovery/end_session，也不撤销 API Key 或其他用户/浏览器凭据。

## 替代方案

- 继续结束认证中心 SSO：不符合各产品独立退出的要求。
- 仅删本地 token：旧凭据仍有效。
- 只撤销 OIDC 会话：密码登录也使用同一退出按钮，凭据仍无法撤销。
- Redis 黑名单：重启丢失会复活有效期内的旧凭据，持久撤销事实属于 PostgreSQL。

## 验证

用户要求不运行测试套件。独立开发槽位使用专属虚构账号完成实际浏览器、HTTP 与 Keycloak 管理 API 核对；账号设置使用真实 Vue 页面与假资料预览。完整回归及更新后的 pytest 用例未执行。

| 验收主张 | 失败面 | 语义 Owner | 直接证据 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| OIDC 退出只影响当前 Yuxi 会话 | 共享 SSO 被结束 | logout service、UserInfoComponent | 页面回到 Yuxi 登录页、本地 token 清除、旧 JWT HTTP 401、IdP logout 请求数 0 | 旧 token 再访问拒绝 | Passed |
| 认证中心 SSO 可复用 | 退出误杀其他产品会话 | 前端退出与 Keycloak | 同浏览器再次统一登录自动返回同一账号，无输入认证中心密码；IdP 管理 API 仍读取活跃 SSO | 不得访问 end_session | Passed |
| 密码令牌撤销且隔离其他凭据 | 旧令牌复活、等价签名编码绕过 | LoginSessionRepository、鉴权依赖 | 当前及补齐 padding 的旧 JWT 401，其他密码 JWT 和 OIDC 会话 200 | padding 令牌退出前 200、退出后 401 | Passed |
| IdP 主动撤销继续生效 | back-channel 被移除 | 既有 OIDC service/repository | 管理端结束专属账号 SSO，PG 回读该主体 OIDC 会话已撤销；合法 JWT 携同一已撤销 sid 请求 401 | 有效签名凭据仍因会话撤销被拒绝 | Passed |
| 账号资料显示可读，ID 按需使用 | 后缀泄漏、ID撑宽、错误写入名称 | identity store、AccountSettingsComponent | 桌面及窄屏截图，初始无 ID code、编辑草稿为可读名称，展开/剪贴板等于原始完整 UID | 未改名称不提交资料请求（静态审查） | Passed（DOM）；Inspected（无变化保存分支） |

静态验证：相关 Python Ruff 和前端 ESLint 通过。JWT 摘要规范化实际签名输入和签名字节，覆盖旧无 jti 凭据，不依赖 token 的等价 base64url 表示。实际证据不包含真实 Duxi 产品；SSO 保留与不访问认证中心退出端点直接证明此产品不会主动结束共享登录。

## 后果

增加一张小型 JWT 撤销表和密码令牌的查询。退出需要后端提交成功；已失效凭据的浏览器可以直接清本地状态。认证中心全局退出只由认证中心自身入口发起。
