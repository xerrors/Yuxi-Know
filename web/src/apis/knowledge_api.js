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
  },

  /**
   * 使用 AI 生成或优化知识库描述
   * @param {string} name - 知识库名称
   * @param {string} currentDescription - 当前描述（可选）
   * @param {Array} fileList - 文件列表（可选）
   * @returns {Promise} - 生成结果
   */
  generateDescription: async (name, currentDescription = '', fileList = []) => {
    return apiAdminPost('/api/knowledge/generate-description', {
      name,
      current_description: currentDescription,
      file_list: fileList
    })
  },

  /**
   * 获取当前用户有权访问的知识库列表（用于智能体配置）
   * @returns {Promise} - 可访问的知识库列表
   */
  getAccessibleDatabases: async () => {
    return apiAdminGet('/api/knowledge/databases/accessible')
  }
}

// =============================================================================
// === 文档管理分组 ===
// =============================================================================

export const documentApi = {
  /**
   * 创建文件夹
   * @param {string} dbId - 知识库ID
   * @param {string} folderName - 文件夹名称
   * @param {string} parentId - 父文件夹ID
   * @returns {Promise} - 创建结果
   */
  createFolder: async (dbId, folderName, parentId = null) => {
    return apiAdminPost(`/api/knowledge/databases/${dbId}/folders`, {
      folder_name: folderName,
      parent_id: parentId
    })
  },

  /**
   * 移动文档/文件夹
   * @param {string} dbId - 知识库ID
   * @param {string} docId - 文档/文件夹ID
   * @param {string} newParentId - 新的父文件夹ID
   * @returns {Promise} - 移动结果
   */
  moveDocument: async (dbId, docId, newParentId) => {
    return apiAdminPut(`/api/knowledge/databases/${dbId}/documents/${docId}/move`, {
      new_parent_id: newParentId
    })
  },

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
   * 手动触发文档解析
   * @param {string} dbId - 知识库ID
   * @param {Array} fileIds - 文件ID列表
   * @returns {Promise} - 解析任务结果
   */
  parseDocuments: async (dbId, fileIds) => {
    return apiAdminPost(`/api/knowledge/databases/${dbId}/documents/parse`, fileIds)
  },

  /**
   * 手动触发文档入库
   * @param {string} dbId - 知识库ID
   * @param {Array} fileIds - 文件ID列表
   * @param {Object} params - 处理参数
   * @returns {Promise} - 入库任务结果
   */
  indexDocuments: async (dbId, fileIds, params = {}) => {
    return apiAdminPost(`/api/knowledge/databases/${dbId}/documents/index`, {
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
   * 更新知识库查询参数
   * @param {string} dbId - 知识库ID
   * @param {Object} params - 查询参数
   * @returns {Promise} - 更新结果
   */
  updateKnowledgeBaseQueryParams: async (dbId, params) => {
    return apiAdminPut(`/api/knowledge/databases/${dbId}/query-params`, params)
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
   * 抓取 URL 内容
   * @param {string} url - 目标 URL
   * @param {string} dbId - 知识库 ID
   * @returns {Promise} - 抓取结果
   */
  fetchUrl: async (url, dbId = null) => {
    return apiAdminPost('/api/knowledge/files/fetch-url', {
      url,
      db_id: dbId
    })
  },

  /**
   * 上传文件
   * @param {File} file - 文件对象
   * @param {string} dbId - 知识库ID（可选）
   * @returns {Promise} - 上传结果
   */
  uploadFile: async (file, dbId = null) => {
    const formData = new FormData()
    formData.append('file', file)

    const url = dbId ? `/api/knowledge/files/upload?db_id=${dbId}` : '/api/knowledge/files/upload'

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
    return apiRequest(
      `/api/knowledge/files/upload-folder?db_id=${dbId}`,
      {
        method: 'POST',
        body: formData
        // 不设置 Content-Type，让浏览器自动设置 boundary
      },
      true,
      'json'
    ) // 需要认证，期望JSON响应
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

// =============================================================================
// === RAG评估分组 ===
// =============================================================================

export const evaluationApi = {
  /**
   * 上传评估基准文件
   * @param {string} dbId - 知识库ID
   * @param {File} file - JSONL文件
   * @param {Object} metadata - 基准元数据
   * @returns {Promise} - 上传结果
   */
  uploadBenchmark: async (dbId, file, metadata = {}) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('name', metadata.name || '')
    formData.append('description', metadata.description || '')

    // 调试：打印 FormData 内容
    console.log('FormData 内容:')
    for (let [key, value] of formData.entries()) {
      console.log(key, value)
    }
    console.log('file type:', file ? file.type : 'undefined')
    console.log('file name:', file ? file.name : 'undefined')

    // 直接传递 FormData，apiAdminPost 会正确处理
    return apiAdminPost(`/api/evaluation/databases/${dbId}/benchmarks/upload`, formData)
  },

  /**
   * 获取评估基准列表
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 基准列表
   */
  getBenchmarks: async (dbId) => {
    return apiAdminGet(`/api/evaluation/databases/${dbId}/benchmarks`)
  },

  /**
   * 获取评估基准详情
   * @param {string} benchmarkId - 基准ID
   * @returns {Promise} - 基准详情
   */
  getBenchmark: async (benchmarkId) => {
    return apiAdminGet(`/api/evaluation/benchmarks/${benchmarkId}`)
  },
  /**
   * 获取评估基准详情（带db_id）
   * @param {string} dbId - 知识库ID
   * @param {string} benchmarkId - 基准ID
   */
  getBenchmarkByDb: async (dbId, benchmarkId, page = 1, pageSize = 50) => {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString()
    })
    return apiAdminGet(`/api/evaluation/databases/${dbId}/benchmarks/${benchmarkId}?${params}`)
  },

  /**
   * 删除评估基准
   * @param {string} benchmarkId - 基准ID
   * @returns {Promise} - 删除结果
   */
  deleteBenchmark: async (benchmarkId) => {
    return apiAdminDelete(`/api/evaluation/benchmarks/${benchmarkId}`)
  },

  /**
   * 自动生成评估基准
   * @param {string} dbId - 知识库ID
   * @param {Object} params - 生成参数
   * @param {number} params.count - 生成问题数量
   * @param {boolean} params.include_answers - 是否生成答案
   * @param {Object} params.llm_config - LLM配置
   * @returns {Promise} - 生成结果
   */
  generateBenchmark: async (dbId, params) => {
    return apiAdminPost(`/api/evaluation/databases/${dbId}/benchmarks/generate`, params)
  },

  /**
   * 运行RAG评估
   * @param {string} dbId - 知识库ID
   * @param {Object} params - 评估参数
   * @param {string} params.benchmark_id - 基准ID
   * @param {Object} params.retrieval_config - 检索配置
   * @returns {Promise} - 评估任务ID
   */
  runEvaluation: async (dbId, params) => {
    return apiAdminPost(`/api/evaluation/databases/${dbId}/run`, params)
  },

  /**
   * 获取评估结果
   * @param {string} taskId - 任务ID
   * @returns {Promise} - 评估结果
   */
  getEvaluationResults: async (taskId) => {
    // 已废弃：请改用 getEvaluationResultsByDb
    return apiAdminGet(`/api/evaluation/${taskId}/results`)
  },

  /**
   * 删除评估结果
   * @param {string} taskId - 任务ID
   * @returns {Promise} - 删除结果
   */
  deleteEvaluationResult: async (taskId) => {
    // 已废弃：请改用 deleteEvaluationResultByDb
    return apiAdminDelete(`/api/evaluation/${taskId}`)
  },

  // 新接口：带 db_id 的评估结果查询与删除
  getEvaluationResultsByDb: async (dbId, taskId, params = {}) => {
    const queryParams = new URLSearchParams()

    if (params.page) queryParams.append('page', params.page)
    if (params.pageSize) queryParams.append('page_size', params.pageSize)
    if (params.errorOnly !== undefined) queryParams.append('error_only', params.errorOnly)

    const url = `/api/evaluation/databases/${dbId}/results/${taskId}${queryParams.toString() ? '?' + queryParams.toString() : ''}`
    return apiAdminGet(url)
  },
  deleteEvaluationResultByDb: async (dbId, taskId) => {
    return apiAdminDelete(`/api/evaluation/databases/${dbId}/results/${taskId}`)
  },

  /**
   * 获取知识库的评估历史记录
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 评估历史列表
   */
  getEvaluationHistory: async (dbId) => {
    return apiAdminGet(`/api/evaluation/databases/${dbId}/history`)
  }
}
