/**
 * 认证相关 API
 */

/**
 * 获取 OIDC 配置
 * @returns {Promise<{enabled: boolean, provider_name?: string}>}
 */
async function getOIDCConfig() {
  const response = await fetch('/api/auth/oidc/config')
  if (!response.ok) {
    throw new Error('获取 OIDC 配置失败')
  }
  return response.json()
}

/**
 * 获取 OIDC 登录 URL
 * @param {string} redirectPath - 登录后的重定向路径
 * @returns {Promise<{login_url: string}>}
 */
async function getOIDCLoginUrl(redirectPath = '/') {
  const params = new URLSearchParams({ redirect_path: redirectPath })
  const response = await fetch(`/api/auth/oidc/login-url?${params}`)
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '获取 OIDC 登录地址失败')
  }
  return response.json()
}

/**
 * 处理 OIDC 回调
 * @param {string} code - 授权码
 * @param {string} state - state 参数
 * @returns {Promise<{
 *   access_token: string,
 *   token_type: string,
 *   user_id: number,
 *   username: string,
 *   user_id_login: string,
 *   phone_number: string | null,
 *   avatar: string | null,
 *   role: string,
 *   department_id: number | null,
 *   department_name: string | null
 * }>}
 */
async function handleOIDCCallback(code, state) {
  const params = new URLSearchParams({ code, state })
  const response = await fetch(`/api/auth/oidc/callback?${params}`)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'OIDC 登录失败')
  }

  return response.json()
}

/**
 * 执行 OIDC 登出
 * @param {string} token - JWT token
 * @returns {Promise<{logout_url?: string}>}
 */
async function oidcLogout(token) {
  const response = await fetch('/api/auth/oidc/logout', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'OIDC 登出失败')
  }

  return response.json()
}

export const authApi = {
  getOIDCConfig,
  getOIDCLoginUrl,
  handleOIDCCallback,
  oidcLogout,
}
