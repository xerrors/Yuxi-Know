# Keycloak 本地统一认证实验：官方协议与 Yuxi 适配核对

本页是面向 identity 维护者和实验执行者的审计参考，核查日期为 2026-10-13。读者需要了解 Docker Compose 与 OIDC 授权码流程。目标是在独立本地实验中，用官方开源 Keycloak 模拟统一认证中心，验证 Yuxi 的登录、身份绑定及禁用用户边界；完成标准是版本、导入、网络和协议条件能追到官方来源，实际链路验证与未执行项分别记录。范围不包含生产 IdP 部署、LDAP、飞书桥接、商用套餐、多企业管理或全量成员同步。Yuxi 当前配置由[第三方认证参考](../../advanced/third-party-auth.md)拥有。

## 稳定镜像与启动导入

官方 GitHub 最新正式版本为 `26.8.0`，发布时间为 2026-10-01，`prerelease=false`；官方 Docker 入门也使用此版本。Quay 标签 API 在核查时给出的当前有效 manifest digest 如下。相同版本标签在 2026-10-10 发生重建，因此实验使用版本与 digest 双重固定；本核查没有拉取或启动镜像。[正式 Release](https://github.com/keycloak/keycloak/releases/tag/26.8.0)、[官方 Docker 入门](https://www.keycloak.org/getting-started/getting-started-docker)、[官方 Quay 标签元数据](https://quay.io/api/v1/repository/keycloak/keycloak/tag/?specificTag=26.8.0)

```text
quay.io/keycloak/keycloak:26.8.0@sha256:27b3230fbabb8c9ff3c66c864cf09dcd8a41aca82e5100679d109ef0eeb05741
```

本地服务使用 `start-dev --import-realm`，bootstrap 管理员由 `KC_BOOTSTRAP_ADMIN_USERNAME`、`KC_BOOTSTRAP_ADMIN_PASSWORD` 提供。realm 文件挂入 `/opt/keycloak/data/import`，命名为 `yuxi-lab-realm.json`。导入支持 JSON 属性中 `${ENV_NAME}` 占位符，client secret 和测试密码因此可以从容器环境注入，仓库只保存占位符。[容器启动与导入](https://www.keycloak.org/server/containers)、[导入命名与环境占位符](https://www.keycloak.org/server/importExport)

启动导入会跳过已经存在的 realm，修改文件后单纯重启不会更新它。重复实验可使用专属临时数据目录重建实验实例，或对专属 `yuxi-lab` realm 显式执行管理更新；不能用重新导入覆盖共享 realm。`start-dev` 具有开发默认值，只用于本地实验。[启动导入语义](https://www.keycloak.org/server/importExport)、[开发模式边界](https://www.keycloak.org/server/containers)

26.8.0 官方镜像运行用户为 UID 1000、GID 0。bind mount 的导入目录及父目录需允许该用户遍历，JSON 文件需允许读取；宿主机另一 UID 拥有的 `0700` 目录会阻止读取。实验应核对容器实际可读权限，再确认 realm 出现在管理 API；只给 JSON 文件加读取权限不能解决目录缺少遍历权限。[26.8.0 容器 Dockerfile](https://github.com/keycloak/keycloak/blob/26.8.0/quarkus/container/Dockerfile)

## 浏览器和 API 使用同一个 issuer

Keycloak hostname v2 用显式 URL 定义公开端点和 issuer。默认 `hostname-backchannel-dynamic=false`，后端与浏览器端点相同；hostname 配置不会替代监听端口设置。实验建议保持一个固定名称和端口，避免 browser 使用 localhost、API 使用 service name 时出现 discovery 地址不可达或 issuer 不一致。[Hostname v2](https://www.keycloak.org/server/hostname)、[OIDC issuer 精确匹配规则](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)

| 位置 | 实验配置或可观察结果 |
| --- | --- |
| 浏览器主机 | 显式将保留测试域名 `auth.yuxi.test` 映射到 `127.0.0.1` |
| Keycloak | `KC_HOSTNAME=http://auth.yuxi.test:8780`，`KC_HTTP_PORT=8780` |
| Docker 发布 | `127.0.0.1:8780:8780`，API 与 Keycloak 加入同一个实验网络 |
| Docker DNS | Keycloak 网络 alias 为 `auth.yuxi.test`，解析到容器地址 |
| Yuxi issuer | `http://auth.yuxi.test:8780/realms/yuxi-lab` |
| Discovery | 上述 issuer 加 `/.well-known/openid-configuration`，浏览器与 API 均可达 |
| 回调 | 浏览器实际访问的 `http://localhost:5173/api/auth/oidc/callback`，随槽位端口显式调整 |

该表是实验网络建议，尚未在当前机器实施。名称在浏览器侧和容器侧可以解析到不同地址，但 URL 字符串、端口和 realm 保持一致。Compose 同网络的服务通过 DNS 相互发现，容器通信使用容器监听端口；保留 `127.0.0.1` 发布使入口仅面向本机。若浏览器运行在另一台机器，需要可达的测试入口与对应名称映射，不能继续假设它的 localhost 是 Docker 主机。[Compose 网络与端口](https://docs.docker.com/compose/how-tos/networking/)、[网络 aliases](https://docs.docker.com/reference/compose-file/services/#aliases)、[Yuxi Vite 回调参考](../../advanced/third-party-auth.md)

hostname v2 也支持公开前台 URL 与动态内部 backchannel，但最小实验无需启用这个额外路径。验收应从 API 容器与浏览器分别读取 discovery，核对 `issuer`，并验证 authorization、token、userinfo、JWKS URL 可达；不能仅检查容器存活。[Hostname v2 的动态 backchannel](https://www.keycloak.org/server/hostname)

已有实验也可复用浏览器和 API 都能访问的一个固定测试 IP/域名及端口，保持同一 canonical issuer；表中的别名方案不要求另建环境或修改生产网络。使用公网测试入口时应限制实验访问范围，HTTP 只用于已约定的开发验证；该结果不构成生产 HTTPS、代理信任或证书配置验收。

## 最小 realm 与 confidential client

实验使用单独 `yuxi-lab` realm、一个 `yuxi-web` confidential client、两名虚构测试成员。client 开启 Standard Flow，关闭 Implicit Flow、Direct Access Grants、Service Accounts；Client authentication 为 ON，Client Authenticator 为 Client ID and Secret。后台 client secret 认证支持 HTTP POST 表单 `client_id`/`client_secret`，也支持 Basic；Yuxi 当前表单请求对应 `client_secret_post`，不要将 client 限制为仅 Basic。[OIDC 授权码](https://www.keycloak.org/securing-apps/oidc-layers)、[Confidential client credentials](https://www.keycloak.org/docs/latest/server_admin/index.html)、[26.8.0 client secret authenticator](https://github.com/keycloak/keycloak/blob/26.8.0/services/src/main/java/org/keycloak/authentication/authenticators/client/ClientIdAndSecretAuthenticator.java)

下例是待实验验证的 realm 最小候选。`${...}` 由 Keycloak 导入读取容器环境；应原样保存到 JSON，不能由 shell 或 Compose 提前替换成凭据。测试用户姓名、邮箱和标识均为虚构值。`sslRequired=none` 只允许本地 HTTP 实验。

```json
{
  "realm": "yuxi-lab",
  "enabled": true,
  "sslRequired": "none",
  "registrationAllowed": false,
  "resetPasswordAllowed": false,
  "verifyEmail": false,
  "clients": [{
    "clientId": "yuxi-web",
    "enabled": true,
    "protocol": "openid-connect",
    "publicClient": false,
    "clientAuthenticatorType": "client-secret",
    "secret": "${YUXI_LAB_CLIENT_SECRET}",
    "standardFlowEnabled": true,
    "implicitFlowEnabled": false,
    "directAccessGrantsEnabled": false,
    "serviceAccountsEnabled": false,
    "redirectUris": ["http://localhost:5173/api/auth/oidc/callback"],
    "defaultClientScopes": ["profile", "email"],
    "attributes": {
      "pkce.code.challenge.method": "S256",
      "post.logout.redirect.uris": "http://localhost:5173/login"
    }
  }],
  "users": [{
    "username": "lab-alice",
    "enabled": true,
    "emailVerified": true,
    "email": "alice@example.com",
    "firstName": "Lab",
    "lastName": "Alice",
    "credentials": [{"type": "password", "value": "${YUXI_LAB_ALICE_PASSWORD}", "temporary": false}]
  }, {
    "username": "lab-bob",
    "enabled": true,
    "emailVerified": true,
    "email": "bob@example.com",
    "firstName": "Lab",
    "lastName": "Bob",
    "credentials": [{"type": "password", "value": "${YUXI_LAB_BOB_PASSWORD}", "temporary": false}]
  }]
}
```

realm、client、user 和 credential 字段来自[Admin REST representations](https://www.keycloak.org/docs-api/latest/rest-api/index.html)，占位符来自[导入文档](https://www.keycloak.org/server/importExport)；两个 attributes 的键名由[26.8.0 OIDCConfigAttributes](https://github.com/keycloak/keycloak/blob/26.8.0/server-spi-private/src/main/java/org/keycloak/protocol/oidc/OIDCConfigAttributes.java)拥有。导入后需回读 client、用户和实际 profile/email scopes，不依赖导入日志判断成功。准确登记回调和 logout 返回地址；服务器兑换场景不需要为此开放任意 Web Origins 或使用全域通配符。

PKCE 选项为空时，Keycloak 仅在 client 发来相应参数时应用 PKCE；设为 S256 后必须提供 challenge/verifier。当前 Yuxi OIDC 源码没有这些参数，直接使用此候选会让当前授权失败。当前实验范围为模拟真实 IdP 与现有 OIDC 互通，因此基线显式省去 `pkce.code.challenge.method`；S256 候选用于列明后续生产协议的适配条件，不要求本地互通任务扩展安全改造。基线结果不能写成 S256 验证通过。[PKCE client 设置](https://www.keycloak.org/docs/latest/server_admin/index.html)、[Yuxi 授权构造](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/identity/oidc.py)、[Yuxi token 请求](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/infrastructure/oidc/client.py)

## 初始化与状态变更的自动化路径

最少工具路径是“启动导入建立 fixture，容器自带 `kcadm.sh` 修改测试状态并回读”。Admin CLI 使用相同的 Admin REST API，并负责管理 token；小实验无需增加另一个 IdP SDK 或管理常驻服务。管理员凭据只用于实验初始化与测试控制，普通 Web client 关闭 service accounts，Yuxi 接收 client secret 即可，不接收 master 管理员权限。[Admin CLI](https://www.keycloak.org/docs/latest/server_admin/index.html#admin-cli)、[Admin REST API](https://www.keycloak.org/docs-api/latest/rest-api/index.html)

通过 `/opt/keycloak/bin/kcadm.sh config credentials` 对实验 master realm 建立管理会话；敏感参数优先使用工具交互提示或其文档提供的环境方式，管理 token 配置文件保留在实验容器内且不提交。随后 `get users -r yuxi-lab -q username=lab-alice --fields id,username,enabled` 取得真实内部 ID，`update users/<user-id> -r yuxi-lab -s enabled=false` 禁用，再 `get users/<user-id> -r yuxi-lab --fields id,username,enabled` 证明最终状态。恢复测试用 `enabled=true`，显式终止会话可对 `users/<user-id>/logout` 执行 `create`。[CLI 认证、用户更新与会话操作](https://www.keycloak.org/docs/latest/server_admin/index.html#admin-cli)

若已有 Python HTTP integration fixture，可直接调用以下 Admin API，使用一次性实验管理员 token；返回后读取对象验证，fixture 只清理本次专属 realm 或专属用户。初始化用 realm JSON、状态操作用 API 是两种互补路径。

| 动作 | Admin REST 资源 |
| --- | --- |
| 创建 realm | `POST /admin/realms`，RealmRepresentation 可含 users/clients |
| 创建 client / user | `POST /admin/realms/yuxi-lab/clients` 或 `/users` |
| 查用户 | `GET /admin/realms/yuxi-lab/users?username=lab-alice&exact=true` |
| 更新与回读用户 | `PUT` / `GET /admin/realms/yuxi-lab/users/{id}` |
| 设置测试密码 | `PUT /admin/realms/yuxi-lab/users/{id}/reset-password` |
| 终止该用户 IdP 会话 | `POST /admin/realms/yuxi-lab/users/{id}/logout` |

表中资源由[Admin REST API](https://www.keycloak.org/docs-api/latest/rest-api/index.html)拥有。client 的管理资源 ID 与 `clientId=yuxi-web` 不同，管理 API 中应先查对象再用内部 ID；用户名称与用户 ID 同样需要区分。fixture 更新部分状态时应使用 CLI 的字段更新或读取后提交准确 representation，不能从人类名称猜对象 ID。

## 登录、ID Token 与注销的适配边界

Keycloak 授权码流程返回 access token、refresh token 和 ID Token。候选请求使用 `openid profile email`、一次性 state、与浏览器授权事务关联的 nonce、S256 challenge；token 兑换使用相同 callback、confidential client secret 和 verifier。PKCE verifier 与 nonce 需要由发起授权的事务保管，不能仅生成 nonce 后忽略返回值。[OIDC 流程](https://www.keycloak.org/securing-apps/oidc-layers)、[OIDC Token Response 与 nonce 校验](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)

本地 HTTP 实验适配按 JWKS 验证 ID Token 签名并限制算法，核对 `iss` 等于配置的完整 issuer、`aud` 包含本 client、`exp` 未到期和 nonce 一致；按使用方式处理 `azp` 等字段。UserInfo `sub` 应与 ID Token `sub` 相同后再关联账号。OIDC Core 对直接 TLS token 响应有特定签名校验选择，本实验为 HTTP，因此不能用该条件省去签名检查。[ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)、[UserInfo Response](https://openid.net/specs/openid-connect-core-1_0.html#UserInfoResponse)、[Keycloak JWKS endpoint](https://www.keycloak.org/securing-apps/oidc-layers)

现有 Yuxi callback 只读 access token 和 UserInfo，未消费 ID Token、JWKS、issuer/audience/nonce 校验，且 state 与短期兑换 code 使用进程内存。它签发另一个 Yuxi 本地 JWT。因此基本互通、完整 OIDC 校验、多实例暂态和本地会话撤销需要分别验证，不能由 provider 正确签发推定应用已经执行校验。[现有协议客户端](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/infrastructure/oidc/client.py)、[授权暂态](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/identity/oidc.py)、[HTTP callback](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/api/routers/identity/oidc.py)、[本地 JWT 发布](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/identity/services/oidc.py)

标准注销使用 discovery 的 `end_session_endpoint`。浏览器携带 `id_token_hint` 和准确登记的 `post_logout_redirect_uri`；Keycloak 要求返回地址与 client 的 Valid Post Logout Redirect URIs 匹配，使用返回地址时需有 client_id 或 id_token_hint。无 hint 时可以出现用户确认页。注销由应用先结束本地会话、再结束 IdP SSO 会话；一个 callback 地址不自动兼作合适的注销落地页。[RP-Initiated Logout](https://www.keycloak.org/docs/latest/server_admin/index.html#_oidc-logout)、[OIDC Logout 标准](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)

Yuxi 当前有 logout URL helper，但只读符号搜索没有发现被路由或前端调用，也没有保管 ID Token 用于 hint。需要真实浏览器验证注销后应用无本地会话、IdP 不再保持原 SSO，以及另一个 client 的注销传播。Keycloak backchannel logout 会向已登记的 client URL POST logout token，应用需自行验签并按会话标识结束本地会话；仅部署 Keycloak 不会新增该应用能力。[Yuxi helper](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/identity/oidc.py)、[Keycloak backchannel logout](https://www.keycloak.org/docs/latest/server_admin/index.html#_oidc-logout)

## 禁用用户与已签发 JWT 的区别

Keycloak `enabled=false` 可以用于模拟冻结/停用，不需要删除测试成员。26.8.0 源码在 refresh token 兑换中检查用户启用状态，在 UserInfo 请求中拒绝禁用用户，token introspection 也借助用户有效性检查拒绝禁用状态。因此新认证与持续远端验证可观察到停用；这些结论为源码检查，尚未对运行实例执行。[TokenManager](https://github.com/keycloak/keycloak/blob/26.8.0/services/src/main/java/org/keycloak/protocol/oidc/TokenManager.java)、[UserInfoEndpoint](https://github.com/keycloak/keycloak/blob/26.8.0/services/src/main/java/org/keycloak/protocol/oidc/endpoints/UserInfoEndpoint.java)、[AccessTokenIntrospectionProvider](https://github.com/keycloak/keycloak/blob/26.8.0/services/src/main/java/org/keycloak/protocol/oidc/AccessTokenIntrospectionProvider.java)

已发 JWT 的签名和 `exp` 不会因远端账号字段更新而被修改。仅做离线签名/寿命验证的应用无法据此获得新的用户状态；官方也明确 Sign out all active sessions 不会使尚未到期的 access token 自然提前过期。introspection 是独立远端判定，只有 confidential client 可以调用。[用户会话与 access token 边界](https://www.keycloak.org/docs/latest/server_admin/index.html#managing-user-sessions)、[Introspection endpoint](https://www.keycloak.org/securing-apps/oidc-layers)

Yuxi 登录后自行签发本地 JWT，后续请求不会自动再调用 Keycloak。因此“禁用成员后新的 Keycloak 登录拒绝”与“原 Yuxi 会话立即终止”是两个验收结果。当前互通实验应先记录实际结果；如要求后者，另需应用端持续状态校验、经过验证的 backchannel logout 或明确的本地撤销机制，这些不属于当前基线联调的默认实现范围。恢复 `enabled=true` 只恢复 IdP 成员可用性，不授权恢复被本地管理员停用的账号。[Yuxi 本地会话发布](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/identity/services/oidc.py)、[Keycloak logout 传播](https://www.keycloak.org/docs/latest/server_admin/index.html#_oidc-logout)

## 实验验收与本次检查

当前任务的基线验收为：真实 Keycloak discovery、表单 secret 授权码兑换、UserInfo、本地账号/代表性资源回读、重复登录，以及 IdP 禁用后新登录拒绝。PKCE、ID Token/nonce、双向注销及已有本地会话即时撤销的缺口需要如实记录，不将基线结果写成生产 IdP 就绪。

| 观察项 | 有效证据 | 本核查状态 |
| --- | --- | --- |
| 固定版本与镜像 | GitHub 正式 Release、Quay 当前有效 digest | Inspected |
| realm/client/users 导入 | Admin API 回读目标 realm、client 设置和两位虚构成员 | Not run；仅检查官方契约与候选 JSON |
| 同 issuer 可达性 | API 与浏览器分别读取 discovery，并核对 issuer 和端点 | Not run；未访问运行实例 |
| 现有 OIDC 互通 | 真实浏览器授权、code 换 token、UserInfo 和 Yuxi 用户/资源回读 | Not run；仅只读源码 |
| 停用与恢复 | Admin API 回读 enabled 后验证新登录、已发 IdP token 和本地 JWT 的分别结果 | Not run；未操作用户 |
| S256/ID Token/logout | 对应协议正向与错误 verifier、错误 nonce/issuer/aud、重复 state 的拒绝结果 | Not run；属于后续候选协议验收 |

本核查仅创建此研究页，未拉取镜像、创建账号、访问实验或生产凭据。最终运行结果由主任务实际执行的浏览器/HTTP/数据库证据补充；本页不复制未执行的结果。
