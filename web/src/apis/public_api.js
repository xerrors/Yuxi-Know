import { apiGet, apiPost } from './base'

/**
 * 公共API模块
 * 包含所有不需要认证的公共接口
 */

// 登录相关API
export const authApi = {
  /**
   * 用户登录
   * @param {Object} credentials - 登录凭证
   * @returns {Promise} - 登录结果
   */
  login: (credentials) => {
    const formData = new FormData()
    formData.append('username', credentials.username)
    formData.append('password', credentials.password)

    return apiRequest('/api/auth/token', {
      method: 'POST',
      body: formData
    }, false)
  },

  /**
   * 检查是否是首次运行
   * @returns {Promise<boolean>} - 是否首次运行
   */
  checkFirstRun: () => apiGet('/api/auth/check-first-run'),

  /**
   * 初始化管理员账户
   * @param {Object} adminData - 管理员账户数据
   * @returns {Promise} - 初始化结果
   */
  initializeAdmin: (adminData) => apiPost('/api/auth/initialize', adminData),
}

// 配置相关API
export const configApi = {
  /**
   * 获取系统配置
   * @returns {Promise} - 系统配置
   */
  getConfig: () => apiGet('/api/config'),
}

// 健康检查API
export const healthApi = {
  /**
   * 系统健康检查
   * @returns {Promise} - 健康检查结果
   */
  check: () => apiGet('/api/health'),
}

// 从base.js导入apiRequest以支持FormData
import { apiRequest } from './base'