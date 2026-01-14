import { apiAdminGet, apiAdminPost } from './base'

/**
 * 思维导图API模块
 * 提供思维导图相关的接口功能
 */

// =============================================================================
// === 知识库管理 ===
// =============================================================================

export const mindmapApi = {
  /**
   * 获取所有知识库概览（用于选择）
   * @returns {Promise} - 知识库列表
   */
  getDatabases: async () => {
    return apiAdminGet('/api/mindmap/databases')
  },

  /**
   * 获取指定知识库的文件列表
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 文件列表
   */
  getDatabaseFiles: async (dbId) => {
    return apiAdminGet(`/api/mindmap/databases/${dbId}/files`)
  },

  /**
   * AI生成思维导图
   * @param {string} dbId - 知识库ID
   * @param {Array<string>} fileIds - 选择的文件ID列表（为空则使用所有文件）
   * @param {string} userPrompt - 用户自定义提示词
   * @returns {Promise} - 思维导图数据
   */
  generateMindmap: async (dbId, fileIds = [], userPrompt = '') => {
    return apiAdminPost('/api/mindmap/generate', {
      db_id: dbId,
      file_ids: fileIds,
      user_prompt: userPrompt
    })
  },

  /**
   * 获取知识库的思维导图
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 思维导图数据
   */
  getByDatabase: async (dbId) => {
    return apiAdminGet(`/api/mindmap/database/${dbId}`)
  }
}
