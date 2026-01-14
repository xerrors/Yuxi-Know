import { apiGet, apiPost, apiAdminGet, apiAdminPost, apiAdminPut, apiAdminDelete } from './base'

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
  getConfig: async () => apiAdminGet('/api/system/config'),

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
   * 获取系统日志
   * @param {string} levels - 可选的日志级别过滤，多个级别用逗号分隔
   * @returns {Promise} - 系统日志
   */
  getLogs: async (levels) => {
    const url = levels
      ? `/api/system/logs?levels=${encodeURIComponent(levels)}`
      : '/api/system/logs'
    return apiAdminGet(url)
  }
}

// =============================================================================
// === 信息管理分组 ===
// =============================================================================

export const brandApi = {
  /**
   * 获取系统信息配置（公开接口）
   * @returns {Promise} - 系统信息配置
   */
  getInfoConfig: () => apiGet('/api/system/info', {}, false),

  /**
   * 重新加载信息配置
   * @returns {Promise} - 重新加载结果
   */
  reloadInfoConfig: async () => apiPost('/api/system/info/reload', {}, {}, false)
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

// =============================================================================
// === 聊天模型状态检查分组 ===
// =============================================================================

export const chatModelApi = {
  /**
   * 获取指定聊天模型的状态
   * @param {string} provider - 模型提供商
   * @param {string} modelName - 模型名称
   * @returns {Promise} - 模型状态
   */
  getModelStatus: async (provider, modelName) => {
    return apiAdminGet(
      `/api/system/chat-models/status?provider=${encodeURIComponent(provider)}&model_name=${encodeURIComponent(modelName)}`
    )
  },

  /**
   * 获取所有聊天模型的状态
   * @returns {Promise} - 所有模型状态
   */
  getAllModelsStatus: async () => {
    return apiAdminGet('/api/system/chat-models/all/status')
  }
}

// =============================================================================
// === 自定义供应商管理分组 ===
// =============================================================================

export const customProviderApi = {
  /**
   * 获取所有自定义供应商
   * @returns {Promise} - 自定义供应商列表
   */
  getCustomProviders: async () => {
    return apiAdminGet('/api/system/custom-providers')
  },

  /**
   * 添加自定义供应商
   * @param {string} providerId - 供应商ID
   * @param {Object} providerData - 供应商配置数据
   * @returns {Promise} - 添加结果
   */
  addCustomProvider: async (providerId, providerData) => {
    return apiAdminPost('/api/system/custom-providers', {
      provider_id: providerId,
      provider_data: providerData
    })
  },

  /**
   * 更新自定义供应商
   * @param {string} providerId - 供应商ID
   * @param {Object} providerData - 供应商配置数据
   * @returns {Promise} - 更新结果
   */
  updateCustomProvider: async (providerId, providerData) => {
    return apiAdminPut(
      `/api/system/custom-providers/${encodeURIComponent(providerId)}`,
      providerData
    )
  },

  /**
   * 删除自定义供应商
   * @param {string} providerId - 供应商ID
   * @returns {Promise} - 删除结果
   */
  deleteCustomProvider: async (providerId) => {
    return apiAdminDelete(`/api/system/custom-providers/${encodeURIComponent(providerId)}`)
  },

  /**
   * 测试自定义供应商连接
   * @param {string} providerId - 供应商ID
   * @param {string} modelName - 要测试的模型名称
   * @returns {Promise} - 测试结果
   */
  testCustomProvider: async (providerId, modelName) => {
    return apiAdminPost(`/api/system/custom-providers/${encodeURIComponent(providerId)}/test`, {
      model_name: modelName
    })
  }
}
