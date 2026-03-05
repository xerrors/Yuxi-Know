import { apiAdminGet } from './base'

/**
 * 工具管理 API 模块
 * 包含系统内置工具的查询功能
 */

const BASE_URL = '/api/system/tools'

/**
 * 获取工具列表
 * @param {string} category - 可选，按分类筛选
 * @returns {Promise} - 工具列表
 */
export const getTools = async (category = null) => {
  const params = category ? { category } : {}
  return apiAdminGet(BASE_URL, params)
}

/**
 * 获取工具选项列表（用于下拉选择）
 * @returns {Promise} - 工具选项
 */
export const getToolOptions = async () => {
  return apiAdminGet(`${BASE_URL}/options`)
}

// =============================================================================
// === 导出为对象形式（兼容现有代码风格）===
// =============================================================================

export const toolApi = {
  getTools,
  getToolOptions
}

export default toolApi
