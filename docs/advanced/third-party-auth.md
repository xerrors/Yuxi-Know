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

# 是否使用原始用户名（不带 oidc: 前缀），允许映射到 Yuxi 已有的本地账号 (true/false，默认: false)
# 开启后，OIDC 返回的 username 会直接作为 user_id 登录，需要管理员提前创建好用户账号
# OIDC_USE_RAW_USERNAME=false

# 是否从OIDC userinfo 中获取部门信息并自动创建关联部门 (true/false，默认: false)
# OIDC_FETCH_DEPARTMENT_INFO=false

# 部门名称字段映射 (默认: department)
# OIDC_DEPARTMENT_CLAIM=department

# OIDC 登录时是否强制提示用户重新登录 (添加 prompt=login 参数，true/false，默认: false)
# OIDC_FORCE_PROMPT_LOGIN=false

```
### 3. 重启Yuxi服务使配置生效
```bash
docker restart api-dev web-dev
```

## 功能说明

### 使用原始用户名（OIDC_USE_RAW_USERNAME=true）
当你需要将 Yuxi 系统中已有的本地账号与 OIDC SSO 绑定，可以开启此选项。

**绑定原理**（无需修改数据库）：  
系统会创建一个标记为删除的占位用户 `oidc:{sub}:{target_user_id}` 来记录 OIDC sub 与 Yuxi 用户的绑定关系，确保只有绑定过的 OIDC 身份才能登录对应的账号，**防止账号冒用**。

### 自动获取部门信息（OIDC_FETCH_DEPARTMENT_INFO=true）
开启后，系统会从 OIDC userinfo 中读取部门名称和描述，自动在 Yuxi 中创建部门并将用户关联到该部门。

- 对从 OIDC 获取的部门名称会自动做 `strip()` 去空格，并截断到 50 字符
- 部门描述会自动截断到 255 字符
- 如果部门名称处理后为空，会回退到使用 `OIDC_DEFAULT_DEPARTMENT` 默认部门