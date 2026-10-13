# Generic OIDC 生产安全：协议证据与最小方案

本页是 identity 维护者的研究参考，核查日期为 2026-10-13；前置知识为授权码流程、Yuxi 本地 JWT 和数据库事务。目标是为 FastAPI/Vue 的 generic OIDC 安全补齐提供官方依据及真实 Keycloak 验收方向。本文区分规范要求与应用选择，不声明候选方案已经实现。生产配置由[第三方认证参考](../../advanced/third-party-auth.md)拥有，实验拓扑由[Keycloak 联调研究](./keycloak-oidc-lab-research-2026-10-13.md)说明。

范围包括授权事务、身份验证、身份持久绑定和会话注销；不包含目录同步、SCIM 服务、组织权限映射、IAM 管理台、多个企业的动态 IdP 选择及新建 IdP 部署平台。验收以真实协议拒绝、数据库身份与会话回读、浏览器登录结果为准。

## 授权事务如何绑定发起浏览器

[OAuth Security BCP §2.1–2.1.1](https://www.rfc-editor.org/rfc/rfc9700.html#section-2.1) 要求防止 CSRF 与授权码注入：public client 必须 PKCE，confidential client 推荐 PKCE；挑战或 nonce 必须按事务生成并绑定发起浏览器。使用 state 防 CSRF 时，它必须绑定浏览器且单次使用。§2.1.1 推荐不暴露 verifier 的挑战方法，当前为 S256。客户端必须避免开放重定向。

建议的最小流程是后端生成 state、nonce、verifier；浏览器只收到随机事务绑定 cookie 与 IdP 跳转 URL。服务端短期记录关联浏览器绑定摘要、预期 issuer/client/callback、nonce、verifier 和已校验的站内返回路径。生产 cookie 使用 Secure、HttpOnly、SameSite=Lax；此选择对应顶层 GET callback，若改成 form_post 必须重新验证跨站 cookie 行为。Cookie 属性、摘要与存储结构属于本地工程选择。

共享短期存储在单个原子操作中核对绑定并消费 state；普通 GET 后 DEL 留有并发窗口。未知、过期、绑定不符、重复或 IdP error callback 均不得建立用户会话。Cookie 不符不消费另一浏览器的事务，防止旁观者抢先作废。数据库也能承担此操作，但一次性暂态可复用 Redis；Redis 不可用时登录失败，不退回进程字典。回调交给 Vue 的短期登录兑换码同样绑定浏览器且原子单用，避免攻击者把自己的兑换链接发给受害者完成登录替换。这些是从事务绑定与单用要求导出的实施建议。

建议保留一个固定 issuer、一个 confidential client 与授权码流程。生产启用 S256 并在 Keycloak client 强制 S256，负向验证缺失或错误 verifier 均失败；无需为尚无 consumer 的 plain、implicit、动态注册或多 issuer 增加兼容层。[Keycloak PKCE 设置](https://www.keycloak.org/docs/latest/server_admin/index.html#_oidc_clients)

## 哪些远端数据可以成为登录身份

[OIDC Core errata 2 §2、§3.1.3.7](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation) 定义 ID Token 的必需字段与验证：精确匹配 issuer；aud 包含 client 且其他 audience 可信；exp 未到期；发起时有 nonce 则返回值必须一致。iat 的可接受时间范围由 RP 决定。当前 errata 2 对 azp 按扩展处理，出现时校验其为本 client 是可采用的规则；不能将旧版的多 audience/azp 描述写成当前通用 MUST。

建议采用小而明确的应用 profile：要求非空字符串 sub、iss 和 nonce，合法 aud 形状及数值时间；固定 RS256，按可信 JWKS 验签，拒绝 none、HMAC 和未协商算法；要求 aud 只指向本 client，azp 如出现也必须匹配；拒绝未来 iat，采用小幅时钟容差。单一 audience 是本地严格选择，接入有其他 audience 的 provider 必须先解释那些 audience 的信任来源。Core 对直接 TLS token 响应提供特定签名校验豁免；统一验签能让 HTTP 实验和生产使用同一身份验证路径，此方案主动不用该豁免。

授权码流程的 at_hash 为可选，存在时验证也是 Core 的 MAY；建议存在就验证、缺失可接受，不能要求所有 provider 都返回。UserInfo 的 sub 必须与已验证 ID Token 的 sub 精确相等。验证完成前不写账号、不创建部门、不发 Yuxi JWT。[Core §3.1.3.8](https://openid.net/specs/openid-connect-core-1_0.html#CodeFlowTokenValidation)、[Core §5.3.2](https://openid.net/specs/openid-connect-core-1_0.html#UserInfoResponse)

建议把验证后的身份对象交给 identity service；从 UserInfo 提取展示名、邮箱或部门时禁止覆盖已验证的 issuer/sub/nonce 等安全字段。JWT 库承担密码学，协议适配层承担声明与远端响应类型验证；不要以“库 decode 成功”代替业务 profile 检查。

## Discovery 与 JWKS 的信任从哪里开始

[Discovery §3、§4.3、§7.1](https://openid.net/specs/openid-connect-discovery-1_0.html#ProviderConfigurationValidation) 要求 discovery 的 issuer 与预配置 issuer、ID Token iss 一致；issuer 不含 query/fragment。授权、token、UserInfo、JWKS 端点使用 HTTPS，TLS 校验证书；失败的数据不能继续使用。标准没有要求所有端点与 issuer 同源，因此“同 hostname”不能冒充规范要求。

建议生产从管理员配置的完整 issuer 建立信任，保留大小写、路径和尾斜线的明确语义；只有构造 discovery 请求路径时按规范处理尾斜线。加载时一次校验所需字段、URL 结构和 HTTPS，再发布完整 metadata。拒绝 URL userinfo、fragment 与 HTTPS 降级；对网络访问设置超时与响应大小上限，不跟随未验证重定向。显式端点覆盖也必须经过同一验证边界，不能绕过 issuer 与 JWKS 校验。内网 IdP 本身是合法部署需求，网络出口约束由部署承担；不因实现 generic OIDC 建造新的 SSRF 代理平台。

本地 HTTP 联调例外必须由已有开发环境边界或显式实验配置开启，默认生产仍要求 HTTPS 与证书验证。不要根据“私网地址”推断整个部署可信，也不要通过关闭证书校验实现 HTTPS 联调。例外范围覆盖所有实际访问的 OIDC 端点，并在真实测试结果里声明未验证生产 TLS。

[Core §10.1.1](https://openid.net/specs/openid-connect-core-1_0.html#RotateSigKeys) 描述未知 kid 时重新获取 JWKS，OP 在过渡期间保留旧公钥。建议按 issuer 缓存 JWKS，未知 kid 最多受限刷新一次，仍无可信匹配密钥则拒绝；使用 key 的签名用途、算法与类型做匹配，不从 token 的 jku/x5u 建立新信任。为未知 kid 的刷新加短暂冷却并合并并发请求，防止攻击者利用随机 kid 放大 IdP 请求；缓存到期后不可无限使用已移除密钥。刷新次数、TTL 与冷却是实现预算，规范不提供通用秒数。

## 持久账号和删除状态由谁决定

[Core §5.7](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability) 将 issuer 与 sub 的组合定义为稳定标识，邮箱和 preferred_username 没有同等保证。建议在 identity repository 的唯一约束中保存这对值与本地 user_id；重复登录复用同一用户，issuer 不同而 sub 相同的账号保持隔离。用户名重命名不改变所有权，用户名碰撞不自动绑定已有账号。管理员授权的存量绑定迁移需要明确证据，不能靠名称猜测。

本地删除或禁用属于 Yuxi 业务决定。建议保留绑定指向的删除记录或持久拒绝标记，登录查到后直接拒绝；自动创建只处理未登记的外部身份。只删除绑定却保留自动创建能力，会允许同一外部身份重新开户。规范未规定应用必须自动恢复已删除账号，“禁止自动恢复”来自本地管理语义。若彻底清除身份绑定，则产品必须明确同一外部身份是否允许重新注册，不能把该后果藏在清理实现里。

只读检查时，[OIDC 登录 service](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/identity/services/oidc.py) 存在按 sub 查找、按原始用户名绑定、恢复删除用户与签发本地 JWT 的分支；[OIDC 协议客户端](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/infrastructure/oidc/client.py) 拥有 discovery、token 和 UserInfo 请求；[OIDC 领域模块](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/identity/oidc.py) 拥有登录暂态与配置。以上是研究时的源码定位，具体实现与迁移以最终提交的这些 Owner 为准。

OIDC 登录只提供认证时的身份声明。SCIM 是独立的用户与群组资源管理协议；若未来要求全量成员、组织变动和离职同步，需要独立目录生命周期需求。当前登录补齐只处理已经到达 Yuxi 的认证和注销事件，不增加 SCIM 服务或读取 Keycloak 管理员凭据。[SCIM Protocol RFC 7644 §3](https://www.rfc-editor.org/rfc/rfc7644.html#section-3)

## 双向注销如何真正撤销本地权限

[RP-Initiated Logout §2](https://openid.net/specs/openid-connect-rpinitiated-1_0.html#RPLogout) 定义浏览器跳转到 end_session_endpoint，可携带 id_token_hint、已登记的 post_logout_redirect_uri 和 state；id_token_hint 为推荐项。无 hint 时 OP 需要用户确认。建议用户在 Yuxi 注销时先持久撤销本地会话，再启动 OP 注销；远端失败不能恢复本地会话。若需要返回关联，以独立短期 state 验证注销返回，返回页不产生新登录。ID Token hint 保存在服务端会话，日志不记录其内容；不为此保留无 consumer 的 refresh token。

[Back-Channel Logout errata 1 §2.4–2.8](https://openid.net/specs/openid-connect-backchannel-1_0.html#Validation) 要求签名 Logout Token，包含 iss、aud、iat、exp、jti、events，并至少有 sub 或 sid；禁止 nonce，禁止 alg=none。events 包含规定的注销事件，值为对象。jti 的接收去重检查为 OPTIONAL，不能写成规范 MUST。sid 缺失时注销 issuer/sub 对应全部会话；已经注销的会话按成功处理。无效 token 返回 400，成功返回 200。

建议本地会话持久保存 issuer、sub、OP sid 与独立本地 session_id，本地 JWT 引用 session_id，每次鉴权查询未撤销会话及账号状态。sid 存在时只处理同 issuer 的该 sid；sub 也存在则同时匹配，不能因为 sid 查无结果而扩大成该用户所有会话。仅 sub 时处理该 issuer/sub 的全部本地会话。普通密码登录或其他 issuer 的会话不得被同名 sub 影响。

建议采用 jti 去重：验签及字段校验通过后，在同一数据库事务中记录 issuer/jti 和撤销匹配会话，保留去重记录至 token 不再可接受。若先在 Redis 标记“已处理”再撤销 PostgreSQL 会话，数据库失败可能导致重试被去重但用户仍在线；要避免这种跨存储提交窗口。已成功处理的重传可返回成功且无新副作用，失败事务允许重试。短小的持久会话与注销回执足够承担本任务，无需通用事件总线。

应用的 iat 接受窗口与小幅时钟容差要固定且可测；exp 必须存在并有效。当前 errata 1 明确要求 exp，旧版示例与某些实现可能缺失，真实 Keycloak 实验应核对实际 payload。若运行版本不满足该要求，记录互操作问题，不能静默忽略校验再声明当前规范通过。typ=logout+jwt 是推荐值，不适合未经联调就作为所有 provider 的强制值。

Keycloak 26.8.0 的 `initLogoutToken` 设置随机 jti、当前 iat 和两分钟后的 exp，并在 session-required 开关开启时添加 sid；它使用与 ID Token 相同的签名算法配置。这是官方版本源码检查，实际运行仍须验证输出。[26.8.0 DefaultTokenManager](https://github.com/keycloak/keycloak/blob/26.8.0/services/src/main/java/org/keycloak/jose/jws/DefaultTokenManager.java)

[Keycloak 管理指南](https://www.keycloak.org/docs/latest/server_admin/index.html#_oidc-logout) 说明管理员注销也可向已登记 URL 发送 backchannel；client 的 Front channel logout 关闭时应用 Backchannel logout URL，Backchannel logout session required 控制 sid 声明。建议真实联调配置显式 URL 与 sid；分别验证按 sid 与仅 sub 的范围。Keycloak 用户 enabled=false、Keycloak 会话注销、Yuxi 本地账号禁用是独立动作，不能假设改一个字段必然发出注销事件。仅离线校验 JWT 签名/exp 的本地应用也无法据此观察远端变更；未到达的 backchannel 通知不会自动触发撤销。

## 最小方案用什么证据验收

建议由现有 protocol client、identity service/repository、鉴权依赖和 Vue 登录/退出入口共同闭合行为，Schema 变更交给现有 migration Owner。先实现并验证授权与身份绑定，再把可撤销会话接入注销。研究结论不授权推测已有数据的 issuer；存量 sub-only 绑定必须有可问责的迁移来源，无法确定的绑定显式拒绝。

| 边界 | 正向直接证据 | 恢复目标缺陷的负向案例 |
| --- | --- | --- |
| 授权事务 | 两个 API 实例间完成同一次真实登录，浏览器得到当前账号 | callback 与兑换链接换浏览器；并发消费同一 state/兑换码；过期；缺失或错误 verifier |
| Token 与 UserInfo | 真实 Keycloak 签名、公钥、声明及本地用户回读 | 错误签名、nonce、issuer、aud、azp、iat/exp、at_hash，UserInfo sub 替换；每项在对应 guard 拒绝 |
| Metadata 与旋转 | 可信 discovery 和真实新增 kid 后登录成功 | issuer 不符、HTTP 生产端点、恶意重定向、未知 kid、刷新不可达、移除旧公钥后的过期缓存 |
| 账号绑定 | 同一 issuer/sub 重登 user_id 不变，重命名后资源归属不变 | 不同 issuer 同 sub、同名不同 sub、本地删除/禁用后重登；数据库确认没有恢复或重开户 |
| 本地及 RP 注销 | 注销后旧 Yuxi JWT 访问真实业务 API 被拒绝，浏览器重新登录需经历预期 OP 流程 | OP 注销失败仍保持本地撤销；伪造返回 state 不建立会话 |
| Backchannel | Keycloak 管理员注销后回读本地撤销状态，旧 JWT 立即拒绝 | 篡改 token、缺 exp/jti/events、包含 nonce、错误 issuer/aud、sid/sub 不符、重放、撤销事务失败再重试 |
| 注销隔离 | 同用户两个 OP sid、另一用户及密码登录会话可分别读取状态 | 注销一个 sid 不影响其他 sid；sub-only 仅影响同 issuer/sub；伪造 token 不改任何会话 |

真实 IdP 负责证明协议互通；定向签名 fixture 负责构造错误声明，真实 HTTP 与数据库结果证明拒绝及副作用边界。未知 kid 的成功旋转至少需要一次真实 Keycloak 密钥更新；mock JWKS 仅覆盖分支。浏览器使用协议回调完成登录，不能用测试直接写数据库会话替代主链路。

本研究状态为 `Inspected`：已读取官方 OIDC Core/Discovery、OAuth Security BCP、双向注销规范、Keycloak 文档以及对应 Yuxi 源码。真实 Keycloak、浏览器、数据库迁移与安全负向测试为 `Not run`，由主任务执行；没有读取凭据或操作远端账号。此页提供推荐与证据要求，不构成生产就绪认证。

文档检查：`python3 scripts/verify_engineering_contracts.py` 通过；`python3 -m unittest scripts.test_verify_engineering_contracts` 通过 64 项测试；在 `docs` 执行 `pnpm run build` 成功，存在 bundle 大小提示；本页相对链接、12 个外部规范锚点及末尾换行均核对通过；`git diff --check -- docs/develop-guides/audits/oidc-production-security-research-2026-10-13.md` 通过。检查结果只证明研究文档结构与链接有效，不证明产品协议验收通过。
