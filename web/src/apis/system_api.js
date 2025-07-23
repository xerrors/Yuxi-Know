import { apiGet, apiPost } from './base'
import { useUserStore } from '@/stores/user'

/**
 * 系统管理API模块
 * 包含系统配置、健康检查、信息管理等功能
 */

// 检查当前用户是否有管理员权限
const checkAdminPermission = () => {
  const userStore = useUserStore()
  if (!userStore.isAdmin) {
    throw new Error('需要管理员权限')
  }
  return true
}

// 检查当前用户是否有超级管理员权限
const checkSuperAdminPermission = () => {
  const userStore = useUserStore()
  if (!userStore.isSuperAdmin) {
    throw new Error('需要超级管理员权限')
  }
  return true
}

// =============================================================================
// === 健康检查分组 ===
// =============================================================================

export const healthApi = {
  /**
   * 系统健康检查（公开接口）
   * @returns {Promise} - 健康检查结果
   */
  checkHealth: () => apiGet('/api/system/health'),

  /**
   * OCR服务健康检查
   * @returns {Promise} - OCR服务健康状态
   */
  checkOcrHealth: async () => {
    checkAdminPermission()
    return apiGet('/api/system/health/ocr', {}, true)
  }
}

// =============================================================================
// === 配置管理分组 ===
// =============================================================================

export const configApi = {
  /**
   * 获取系统配置
   * @returns {Promise} - 系统配置
   */
  getConfig: async () => {
    checkAdminPermission()
    return apiGet('/api/system/config', {}, true)
  },

  /**
   * 更新单个配置项
   * @param {string} key - 配置键
   * @param {any} value - 配置值
   * @returns {Promise} - 更新结果
   */
  updateConfig: async (key, value) => {
    checkAdminPermission()
    return apiPost('/api/system/config', { key, value }, {}, true)
  },

  /**
   * 批量更新配置项
   * @param {Object} items - 配置项对象
   * @returns {Promise} - 更新结果
   */
  updateConfigBatch: async (items) => {
    checkAdminPermission()
    return apiPost('/api/system/config/update', items, {}, true)
  },

  /**
   * 重启系统（仅超级管理员）
   * @returns {Promise} - 重启结果
   */
  restartSystem: async () => {
    checkSuperAdminPermission()
    return apiPost('/api/system/restart', {}, {}, true)
  },

  /**
   * 获取系统日志
   * @returns {Promise} - 系统日志
   */
  getLogs: async () => {
    checkAdminPermission()
    return apiGet('/api/system/logs', {}, true)
  }
}

// =============================================================================
// === 信息管理分组 ===
// =============================================================================

export const infoApi = {
  /**
   * 获取系统信息配置（公开接口）
   * @returns {Promise} - 系统信息配置
   */
  getInfoConfig: () => apiGet('/api/system/info'),

  /**
   * 重新加载信息配置
   * @returns {Promise} - 重新加载结果
   */
  reloadInfoConfig: async () => {
    checkAdminPermission()
    return apiPost('/api/system/info/reload', {}, {}, true)
  }
}

// =============================================================================
// === OCR服务分组 ===
// =============================================================================

export const ocrApi = {
  /**
   * 获取OCR服务统计信息
   * @returns {Promise} - OCR统计信息
   */
  getStats: async () => {
    checkAdminPermission()
    return apiGet('/api/system/ocr/stats', {}, true)
  },

  /**
   * 获取OCR服务健康状态
   * @returns {Promise} - OCR健康状态
   */
  getHealth: async () => {
    checkAdminPermission()
    return apiGet('/api/system/ocr/health', {}, true)
  }
}

// =============================================================================
// === 智能体配置分组 ===
// =============================================================================

export const agentConfigApi = {
  /**
   * 获取智能体配置
   * @param {string} agentName - 智能体名称
   * @returns {Promise} - 智能体配置
   */
  getAgentConfig: async (agentName) => {
    checkAdminPermission()
    return apiGet(`/api/chat/agent/${agentName}/config`, {}, true)
  },

  /**
   * 保存智能体配置
   * @param {string} agentName - 智能体名称
   * @param {Object} config - 配置对象
   * @returns {Promise} - 保存结果
   */
  saveAgentConfig: async (agentName, config) => {
    checkAdminPermission()
    return apiPost(`/api/chat/agent/${agentName}/config`, config, {}, true)
  },

  /**
   * 设置默认智能体
   * @param {string} agentId - 智能体ID
   * @returns {Promise} - 设置结果
   */
  setDefaultAgent: async (agentId) => {
    checkAdminPermission()
    return apiPost('/api/chat/set_default_agent', { agent_id: agentId }, {}, true)
  }
}

