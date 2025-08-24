import { apiGet, apiPost, apiAdminGet, apiAdminPost, apiSuperAdminPost } from './base'

/**
 * 系统管理API模块
 * 包含系统配置、健康检查、信息管理等功能
 */



// =============================================================================
// === 健康检查分组 ===
// =============================================================================

export const healthApi = {
  /**
   * 系统健康检查（公开接口）
   * @returns {Promise} - 健康检查结果
   */
  checkHealth: () => apiGet('/api/system/health', {}, false),

  /**
   * OCR服务健康检查
   * @returns {Promise} - OCR服务健康状态
   */
  checkOcrHealth: async () => apiAdminGet('/api/system/health/ocr')
}

// =============================================================================
// === 配置管理分组 ===
// =============================================================================

export const configApi = {
  /**
   * 获取系统配置
   * @returns {Promise} - 系统配置
   */
  getConfig: async () =>  apiAdminGet('/api/system/config'),

  /**
   * 更新单个配置项
   * @param {string} key - 配置键
   * @param {any} value - 配置值
   * @returns {Promise} - 更新结果
   */
  updateConfig: async (key, value) => apiAdminPost('/api/system/config', { key, value }),

  /**
   * 批量更新配置项
   * @param {Object} items - 配置项对象
   * @returns {Promise} - 更新结果
   */
  updateConfigBatch: async (items) => apiAdminPost('/api/system/config/update', items),

  /**
   * 重启系统（仅超级管理员）
   * @returns {Promise} - 重启结果
   */
  restartSystem: async () => apiSuperAdminPost('/api/system/restart', {}),

  /**
   * 获取系统日志
   * @returns {Promise} - 系统日志
   */
  getLogs: async () =>  apiAdminGet('/api/system/logs')
}

// =============================================================================
// === 信息管理分组 ===
// =============================================================================

export const brandAPi = {
  /**
   * 获取系统信息配置（公开接口）
   * @returns {Promise} - 系统信息配置
   */
  getInfoConfig: () => apiGet('/api/system/info', {}, false),

  /**
   * 重新加载信息配置
   * @returns {Promise} - 重新加载结果
   */
  reloadInfoConfig: async () =>  apiPost('/api/system/info/reload', {}, {}, false)
}

// =============================================================================
// === OCR服务分组 ===
// =============================================================================

export const ocrApi = {
  /**
   * 获取OCR服务统计信息
   * @returns {Promise} - OCR统计信息
   */
  getStats: async () => apiAdminGet('/api/system/ocr/stats'),

  /**
   * 获取OCR服务健康状态
   * @returns {Promise} - OCR健康状态
   */
  getHealth: async () => apiAdminGet('/api/system/ocr/health')
}



