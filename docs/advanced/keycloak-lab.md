# 使用 Keycloak 联调企业登录

本操作指南供集成开发者在已有 Yuxi 开发槽位上验证统一认证登录。需要 Docker Compose、Python 3 和一个已完成管理员初始化的 Yuxi 测试环境；完成后可使用虚构员工执行真实授权码登录并观察 Yuxi 开户结果。环境使用 HTTP 和 Keycloak `start-dev`，仅供隔离联调。企业生产接入仍使用[OIDC 配置参考](./third-party-auth.md)，不能直接复制实验部署上线。

## 生成独立认证环境

在仓库根目录执行，目标目录必须位于仓库外且尚不存在。以下 Yuxi 地址必须与浏览器实际访问的测试入口一致：

```bash
python3 docker/keycloak-lab/prepare.py ../yuxi-sso-lab --yuxi-url http://localhost:25175
docker compose -f ../yuxi-sso-lab/compose.yml up -d
```

生成器创建私有 `.env` 和 `.private/yuxi-oidc.env`，为数据库、管理账号、客户端和两名虚构员工分别生成随机凭据。管理员用户名在 `KC_BOOTSTRAP_ADMIN_USERNAME`，员工 `demo.dev`、`demo.product` 的密码分别在 `EMPLOYEE_DEV_PASSWORD`、`EMPLOYEE_PRODUCT_PASSWORD`。只在本地受保护的编辑器中读取，不复制到 Git、日志或聊天记录。

Compose 启动固定版本 Keycloak 和独立 PostgreSQL。数据库只加入内部网络，Keycloak 额外加入供 Yuxi API 使用的 `yuxi-enterprise-sso_sso` 网络；这避免两个部署中同名 `postgres` 的 DNS 冲突。宿主机只在 `127.0.0.1:39090` 发布认证服务。

在浏览器所在机器的 hosts 文件加入：

```text
127.0.0.1 auth.yuxi.test
```

若 Docker 运行在远程开发机，在浏览器所在机器建立 SSH 转发：

```bash
ssh -N -L 39090:127.0.0.1:39090 -L 25175:127.0.0.1:25175 <ssh-user>@<dev-host>
```

打开 `http://auth.yuxi.test:39090/realms/yuxi-enterprise/.well-known/openid-configuration`，确认 `issuer` 为 `http://auth.yuxi.test:39090/realms/yuxi-enterprise`。管理入口为 `http://auth.yuxi.test:39090/admin/`，企业 realm 为 `yuxi-enterprise`；员工账号页为 `http://auth.yuxi.test:39090/realms/yuxi-enterprise/account/`。

## 将测试 Yuxi 接入认证中心

在 Yuxi 工作树中创建被忽略的 `.yuxi/oidc-lab.compose.yml`。将 env file 路径替换为生成器输出的实际绝对路径：

```yaml
services:
  api:
    env_file:
      - /absolute/path/to/yuxi-sso-lab/.private/yuxi-oidc.env
    networks:
      - app-network
      - sso-lab
networks:
  sso-lab:
    external: true
    name: yuxi-enterprise-sso_sso
```

保留工作树已有的 Compose 覆盖文件，并把此文件加到最后；例如：

```bash
docker compose -f docker-compose.yml -f .yuxi/oidc-lab.compose.yml up -d --no-deps api
```

API 通过共享网络解析 `auth.yuxi.test`，浏览器通过 hosts 和转发访问同一个 issuer。两端的 URL、端口和 realm 必须完全一致。已有环境若在 Compose `environment` 中显式指定 `OIDC_*`，它会覆盖 env file，需要同时调整；生成文件已清空手动协议端点以使用 discovery。

打开 Yuxi 登录页，确认出现“示例企业统一登录”。实验开启自动创建普通用户和部门读取，关闭按同名 uid 自动关联已有账号，并设置 `OIDC_FORCE_PROMPT_LOGIN=false` 以复用认证中心会话。配置变化需要重新创建 API 容器。

## 验证登录和账号行为

1. 使用 `demo.dev` 首次登录。在管理页面或数据库确认只有一名对应普通用户，部门为研发部；身份表按 issuer 和 Keycloak sub 映射，uid 为 `oidc:` 前缀的内部标识。
2. 使用另一份浏览器本地会话再次统一登录，确认本地用户 ID 相同。点击 Yuxi 退出后直接返回登录页，旧 Yuxi JWT 必须返回 401，认证中心 SSO 保留；再次登录可复用 SSO。
3. 使用 `demo.product` 登录，确认得到另一名普通用户和产品部。同名本地用户不自动合并，Keycloak 管理员身份不自动授予 Yuxi 管理权限。
4. 从 Keycloak 管理页面结束员工会话，确认 Yuxi back-channel 接口收到有效通知、旧 JWT 返回 401。禁用员工后新登录应被拒绝；只改 Enabled 不等同于结束会话，须分别验证。
5. 在独立无痕浏览器测试错误密码，必须停留在 Keycloak。测试结束后恢复虚构员工为 Enabled。

模板强制 PKCE S256，back-channel URL 为共享网络内的 `http://api:5050/api/auth/oidc/backchannel-logout`。共享网络中只能让一个目标 API 使用该别名；多个 Yuxi 槽位联调时为每个客户端配置独立容器 DNS 名。已有 realm 不会重新导入模板，需在客户端 Advanced 设置中同步这两项；后端通知地址无需与浏览器 origin 相同，但必须指向同一个 Yuxi 部署。

## 维护和排障

- **导入文件不可读**：运行目录保持 `0700`，被挂载的 `seed/` 为 `0755`、占位 JSON 为 `0644`。JSON 不含真实密钥；容器 UID 1000 必须能够遍历挂载目录并读取文件。
- **配置修改未生效**：启动导入跳过已存在的 realm。通过 Keycloak 管理界面更新 client 的准确 Redirect URI；同步修改私有 Yuxi 环境文件并重建 API。不要为刷新配置删除已有 volume。
- **API 数据库连接失败**：确认认证数据库没有加入 Yuxi API 所用的共享网络。两个 `postgres` 别名会造成错误的 DNS 目标。
- **Docker 地址池耗尽**：在运行目录的 Compose 为两个实验网络分别指定不冲突的子网；先核对机器已有路由和 Docker 网络。
- **登录回调失败**：检查两端 discovery 的 issuer、客户端 secret 和完全一致的回调 URL。不要用手工替换部分协议端点掩盖网络配置不一致。
- **停止和恢复**：在运行目录执行 `docker compose down` 保留命名 volume，再执行 `docker compose up -d` 恢复。移除 Yuxi 的实验覆盖文件并重建 API，可恢复槽位原有认证配置。不要使用 `down -v` 清理需要保留的测试数据。

## 实验与生产的边界

联调环境使用 confidential 授权码、PKCE S256、准确回调和随机 secret，关闭密码直授、隐式授权和服务账号。Yuxi 校验签名、issuer/audience/nonce 和 UserInfo 身份，使用 Redis 浏览器事务与 PostgreSQL 可撤销会话；账号软删除不会因统一登录而恢复。生产要求和账号边界统一由 [OIDC 配置参考](./third-party-auth.md)说明。

实验使用 HTTP、`start-dev` 和虚构员工，不接入企业目录或飞书，不验证生产证书、负载均衡和 IdP 运维策略。正式接入需部署可信 HTTPS 认证中心与 Yuxi 入口，并验证该 IdP 的 back-channel 行为。[官方资料核查](../develop-guides/audits/keycloak-oidc-lab-research-2026-10-13.md)记录版本和协议依据。
