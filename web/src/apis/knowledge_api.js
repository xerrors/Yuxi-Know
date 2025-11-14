import { apiAdminGet, apiAdminPost, apiAdminPut, apiAdminDelete, apiRequest } from './base'

/**
 * 知识库管理API模块
 * 包含数据库管理、文档管理、查询接口等功能
 */

// =============================================================================
// === 数据库管理分组 ===
// =============================================================================

export const databaseApi = {
  /**
   * 获取所有知识库
   * @returns {Promise} - 知识库列表
   */
  getDatabases: async () => {
    return apiAdminGet('/api/knowledge/databases')
  },

  /**
   * 创建知识库
   * @param {Object} databaseData - 知识库数据
   * @returns {Promise} - 创建结果
   */
  createDatabase: async (databaseData) => {
    return apiAdminPost('/api/knowledge/databases', databaseData)
  },

  /**
   * 获取知识库详细信息
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 知识库信息
   */
  getDatabaseInfo: async (dbId) => {
    return apiAdminGet(`/api/knowledge/databases/${dbId}`)
  },

  /**
   * 更新知识库信息
   * @param {string} dbId - 知识库ID
   * @param {Object} updateData - 更新数据
   * @returns {Promise} - 更新结果
   */
  updateDatabase: async (dbId, updateData) => {
    return apiAdminPut(`/api/knowledge/databases/${dbId}`, updateData)
  },

  /**
   * 删除知识库
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 删除结果
   */
  deleteDatabase: async (dbId) => {
    return apiAdminDelete(`/api/knowledge/databases/${dbId}`)
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
    return apiAdminPost(`/api/knowledge/databases/${dbId}/documents`, {
      items,
      params
    })
  },

  /**
   * 获取文档信息
   * @param {string} dbId - 知识库ID
   * @param {string} docId - 文档ID
   * @returns {Promise} - 文档信息
   */
  getDocumentInfo: async (dbId, docId) => {
    return apiAdminGet(`/api/knowledge/databases/${dbId}/documents/${docId}`)
  },

  /**
   * 删除文档
   * @param {string} dbId - 知识库ID
   * @param {string} docId - 文档ID
   * @returns {Promise} - 删除结果
   */
  deleteDocument: async (dbId, docId) => {
    return apiAdminDelete(`/api/knowledge/databases/${dbId}/documents/${docId}`)
  },

  /**
   * 下载文档
   * @param {string} dbId - 知识库ID
   * @param {string} docId - 文档ID
   * @returns {Promise} - Response对象
   */
  downloadDocument: async (dbId, docId) => {
    return apiAdminGet(`/api/knowledge/databases/${dbId}/documents/${docId}/download`, {}, 'blob')
  },

  /**
   * 重新分块文档
   * @param {string} dbId - 知识库ID
   * @param {Array} fileIds - 文件ID列表
   * @param {Object} params - 处理参数
   * @returns {Promise} - 重新分块结果
   */
  rechunksDocuments: async (dbId, fileIds, params = {}) => {
    return apiAdminPost(`/api/knowledge/databases/${dbId}/documents/rechunks`, {
      file_ids: fileIds,
      params
    })
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
    return apiAdminPost(`/api/knowledge/databases/${dbId}/query`, {
      query,
      meta
    })
  },

  /**
   * 测试查询知识库
   * @param {string} dbId - 知识库ID
   * @param {string} query - 查询文本
   * @param {Object} meta - 查询参数
   * @returns {Promise} - 测试结果
   */
  queryTest: async (dbId, query, meta = {}) => {
    return apiAdminPost(`/api/knowledge/databases/${dbId}/query-test`, {
      query,
      meta
    })
  },

  /**
   * 获取知识库查询参数
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 查询参数
   */
  getKnowledgeBaseQueryParams: async (dbId) => {
    return apiAdminGet(`/api/knowledge/databases/${dbId}/query-params`)
  },

  /**
   * 生成知识库的测试问题
   * @param {string} dbId - 知识库ID
   * @param {number} count - 生成问题数量，默认10
   * @returns {Promise} - 生成的问题列表
   */
  generateSampleQuestions: async (dbId, count = 10) => {
    return apiAdminPost(`/api/knowledge/databases/${dbId}/sample-questions`, {
      count
    })
  },

  /**
   * 获取知识库的测试问题
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 问题列表
   */
  getSampleQuestions: async (dbId) => {
    return apiAdminGet(`/api/knowledge/databases/${dbId}/sample-questions`)
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
    const formData = new FormData()
    formData.append('file', file)

    const url = dbId
      ? `/api/knowledge/files/upload?db_id=${dbId}`
      : '/api/knowledge/files/upload'

    return apiAdminPost(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  /**
   * 获取支持的文件类型
   * @returns {Promise} - 文件类型列表
   */
  getSupportedFileTypes: async () => {
    return apiAdminGet('/api/knowledge/files/supported-types')
  },

  /**
   * 上传文件夹（zip格式）
   * @param {File} file - zip文件
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 上传结果
   */
  uploadFolder: async (file, dbId) => {
    const formData = new FormData()
    formData.append('file', file)

    // 使用 apiRequest 直接发送 FormData，但使用统一的错误处理
    return apiRequest(`/api/knowledge/files/upload-folder?db_id=${dbId}`, {
      method: 'POST',
      body: formData,
      // 不设置 Content-Type，让浏览器自动设置 boundary
    }, true, 'json')  // 需要认证，期望JSON响应
  },

  /**
   * 处理文件夹（异步处理zip文件）
   * @param {Object} data - 处理参数
   * @param {string} data.file_path - 已上传的zip文件路径
   * @param {string} data.db_id - 知识库ID
   * @param {string} data.content_hash - 文件内容哈希
   * @returns {Promise} - 处理任务结果
   */
  processFolder: async ({ file_path, db_id, content_hash }) => {
    return apiAdminPost('/api/knowledge/files/process-folder', {
      file_path,
      db_id,
      content_hash
    })
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
    return apiAdminGet('/api/knowledge/types')
  },

  /**
   * 获取知识库统计信息
   * @returns {Promise} - 统计信息
   */
  getStatistics: async () => {
    return apiAdminGet('/api/knowledge/stats')
  }
}

// =============================================================================
// === Embedding模型状态检查分组 ===
// =============================================================================

export const embeddingApi = {
  /**
   * 获取指定embedding模型的状态
   * @param {string} modelId - 模型ID
   * @returns {Promise} - 模型状态
   */
  getModelStatus: async (modelId) => {
    return apiAdminGet(`/api/knowledge/embedding-models/${modelId}/status`)
  },

  /**
   * 获取所有embedding模型的状态
   * @returns {Promise} - 所有模型状态
   */
  getAllModelsStatus: async () => {
    return apiAdminGet('/api/knowledge/embedding-models/status')
  }
}
