import { apiGet, apiPost, apiPut, apiDelete } from './base'
import { useUserStore } from '@/stores/user'

/**
 * 知识库管理API模块
 * 包含数据库管理、文档管理、查询接口等功能
 */

// 检查当前用户是否有管理员权限
const checkAdminPermission = () => {
  const userStore = useUserStore()
  if (!userStore.isAdmin) {
    throw new Error('需要管理员权限')
  }
  return true
}

// =============================================================================
// === 数据库管理分组 ===
// =============================================================================

export const databaseApi = {
  /**
   * 获取所有知识库
   * @returns {Promise} - 知识库列表
   */
  getDatabases: async () => {
    checkAdminPermission()
    return apiGet('/api/knowledge/databases', {}, true)
  },

  /**
   * 创建知识库
   * @param {Object} databaseData - 知识库数据
   * @returns {Promise} - 创建结果
   */
  createDatabase: async (databaseData) => {
    checkAdminPermission()
    return apiPost('/api/knowledge/databases', {
      database_name: databaseData.database_name,
      description: databaseData.description,
      embed_model_name: databaseData.embed_model_name,
      kb_type: databaseData.kb_type || 'lightrag',
      ...databaseData.extra_config
    }, {}, true)
  },

  /**
   * 获取知识库详细信息
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 知识库信息
   */
  getDatabaseInfo: async (dbId) => {
    checkAdminPermission()
    return apiGet(`/api/knowledge/databases/${dbId}`, {}, true)
  },

  /**
   * 更新知识库信息
   * @param {string} dbId - 知识库ID
   * @param {Object} updateData - 更新数据
   * @returns {Promise} - 更新结果
   */
  updateDatabase: async (dbId, updateData) => {
    checkAdminPermission()
    return apiPut(`/api/knowledge/databases/${dbId}`, updateData, {}, true)
  },

  /**
   * 删除知识库
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 删除结果
   */
  deleteDatabase: async (dbId) => {
    checkAdminPermission()
    return apiDelete(`/api/knowledge/databases/${dbId}`, {}, true)
  }
}

// =============================================================================
// === 文档管理分组 ===
// =============================================================================

export const documentApi = {
  /**
   * 添加文档到知识库
   * @param {string} dbId - 知识库ID
   * @param {Array} items - 文档列表
   * @param {Object} params - 处理参数
   * @returns {Promise} - 添加结果
   */
  addDocuments: async (dbId, items, params = {}) => {
    checkAdminPermission()
    return apiPost(`/api/knowledge/databases/${dbId}/documents`, {
      items,
      params
    }, {}, true)
  },

  /**
   * 获取文档信息
   * @param {string} dbId - 知识库ID
   * @param {string} docId - 文档ID
   * @returns {Promise} - 文档信息
   */
  getDocumentInfo: async (dbId, docId) => {
    checkAdminPermission()
    return apiGet(`/api/knowledge/databases/${dbId}/documents/${docId}`, {}, true)
  },

  /**
   * 删除文档
   * @param {string} dbId - 知识库ID
   * @param {string} docId - 文档ID
   * @returns {Promise} - 删除结果
   */
  deleteDocument: async (dbId, docId) => {
    checkAdminPermission()
    return apiDelete(`/api/knowledge/databases/${dbId}/documents/${docId}`, {}, true)
  }
}

// =============================================================================
// === 查询分组 ===
// =============================================================================

export const queryApi = {
  /**
   * 查询知识库
   * @param {string} dbId - 知识库ID
   * @param {string} query - 查询文本
   * @param {Object} meta - 查询参数
   * @returns {Promise} - 查询结果
   */
  queryKnowledgeBase: async (dbId, query, meta = {}) => {
    checkAdminPermission()
    return apiPost(`/api/knowledge/databases/${dbId}/query`, {
      query,
      meta
    }, {}, true)
  },

  /**
   * 测试查询知识库
   * @param {string} dbId - 知识库ID
   * @param {string} query - 查询文本
   * @param {Object} meta - 查询参数
   * @returns {Promise} - 测试结果
   */
  queryTest: async (dbId, query, meta = {}) => {
    checkAdminPermission()
    return apiPost(`/api/knowledge/databases/${dbId}/query-test`, {
      query,
      meta
    }, {}, true)
  },

  /**
   * 获取知识库查询参数
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 查询参数
   */
  getKnowledgeBaseQueryParams: async (dbId) => {
    checkAdminPermission()
    return apiGet(`/api/knowledge/databases/${dbId}/query-params`, {}, true)
  }
}

// =============================================================================
// === 文件管理分组 ===
// =============================================================================

export const fileApi = {
  /**
   * 上传文件
   * @param {File} file - 文件对象
   * @param {string} dbId - 知识库ID（可选）
   * @returns {Promise} - 上传结果
   */
  uploadFile: async (file, dbId = null) => {
    checkAdminPermission()
    
    const formData = new FormData()
    formData.append('file', file)
    
    const url = dbId 
      ? `/api/knowledge/files/upload?db_id=${dbId}`
      : '/api/knowledge/files/upload'
    
    return apiPost(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }, true)
  }
}

// =============================================================================
// === 知识库类型分组 ===
// =============================================================================

export const typeApi = {
  /**
   * 获取支持的知识库类型
   * @returns {Promise} - 知识库类型列表
   */
  getKnowledgeBaseTypes: async () => {
    checkAdminPermission()
    return apiGet('/api/knowledge/types', {}, true)
  },

  /**
   * 获取知识库统计信息
   * @returns {Promise} - 统计信息
   */
  getStatistics: async () => {
    checkAdminPermission()
    return apiGet('/api/knowledge/stats', {}, true)
  }
}

 