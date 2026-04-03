# 第三方登录认证
Yuxi 支持以OIDC接入第三方登录认证，方便企业用户集成现有的身份认证系统。
> 此功能默认关闭，需要在配置文件中启用并提供相关参数。

## 配置步骤
### 1. 前提条件
在你的SSO系统中注册一个新的客户端应用，获取以下信息：
- 客户端ID（Client ID）
- 客户端密钥（Client Secret）
- ISSUER URL

填入回调地址（Redirect URI）：https://<your_yuxi_host>/api/auth/oidc/callback

### 2. 配置Yuxi
在Yuxi的.env文件中添加以下配置项：

```sh
# 是否启用 OIDC 认证 (true/false)
# OIDC_ENABLED=false

# 认证源名称（显示在登录按钮上的文字，建议简短且具有辨识度, 默认: OIDC登录）
# OIDC_PROVIDER_NAME="OIDC登录"

# OIDC Provider 的 Issuer URL (例如: https://auth.example.com)
# OIDC_ISSUER_URL=

# OIDC Client ID
# OIDC_CLIENT_ID=

# OIDC Client Secret
# OIDC_CLIENT_SECRET=

# OIDC 回调 URL (可选，默认自动构建为 /api/auth/oidc/callback, 不建议自定义)
# 填写完整的地址：https://<your_yuxi_host>/api/auth/oidc/callback
# 需要确保此 URL 在 OIDC Provider 中已注册
# OIDC_REDIRECT_URI=

# 授权端点 (可选，自动从 discovery 获取)
# OIDC_AUTHORIZATION_ENDPOINT=

# Token 端点 (可选，自动从 discovery 获取)
# OIDC_TOKEN_ENDPOINT=

# UserInfo 端点 (可选，自动从 discovery 获取)
# OIDC_USERINFO_ENDPOINT=

# 登出端点 (可选，自动从 discovery 获取)
# OIDC_END_SESSION_ENDPOINT=

# 请求的 scope (默认: openid profile email)
# OIDC_SCOPES=openid profile email

# 是否自动创建用户 (true/false，默认: true)
# OIDC_AUTO_CREATE_USER=true

# OIDC 用户的默认角色 (user/admin，默认: user)
# OIDC_DEFAULT_ROLE=user

# OIDC 用户的默认部门名称 (默认: OIDC用户)
# OIDC_DEFAULT_DEPARTMENT=OIDC用户

# 用户名映射字段 (默认: preferred_username)
# OIDC_USERNAME_CLAIM=preferred_username

# 邮箱映射字段 (默认: email)
# OIDC_EMAIL_CLAIM=email

# 姓名映射字段 (默认: name)
# OIDC_NAME_CLAIM=name

```
### 3. 重启Yuxi服务使配置生效
```bash
docker restart api-dev web-dev
```