import { apiGet, apiPost, apiPut, apiDelete } from './base'
import { useUserStore } from '@/stores/user'

/**
 * 管理员API模块
 * 只有管理员和超级管理员可以访问的API
 * 权限要求: admin 或 superadmin
 *
 * 注意: 请确保在使用这些API之前检查用户是否具有管理员权限
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

// 用户管理API
export const userManagementApi = {
  /**
   * 获取用户列表
   * @returns {Promise} - 用户列表
   */
  getUsers: async () => {
    checkAdminPermission()
    return apiGet('/api/auth/users', {}, true)
  },

  /**
   * 创建新用户
   * @param {Object} userData - 用户数据
   * @returns {Promise} - 创建结果
   */
  createUser: async (userData) => {
    checkAdminPermission()
    return apiPost('/api/auth/users', userData, {}, true)
  },

  /**
   * 更新用户
   * @param {number} userId - 用户ID
   * @param {Object} userData - 用户数据
   * @returns {Promise} - 更新结果
   */
  updateUser: async (userId, userData) => {
    checkAdminPermission()
    return apiPut(`/api/auth/users/${userId}`, userData, {}, true)
  },

  /**
   * 删除用户
   * @param {number} userId - 用户ID
   * @returns {Promise} - 删除结果
   */
  deleteUser: async (userId) => {
    checkAdminPermission()
    return apiDelete(`/api/auth/users/${userId}`, {}, true)
  },
}

// 知识库管理API
export const knowledgeBaseApi = {
  /**
   * 获取所有知识库
   * @returns {Promise} - 知识库列表
   */
  getDatabases: async () => {
    checkAdminPermission()
    return apiGet('/api/data/', {}, true)
  },

  /**
   * 创建知识库
   * @param {Object} databaseData - 知识库数据
   * @returns {Promise} - 创建结果
   */
  createDatabase: async (databaseData) => {
    checkAdminPermission()
    return apiPost('/api/data/', databaseData, {}, true)
  },

  /**
   * 获取知识库详情
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 知识库详情
   */
  getDatabaseInfo: async (dbId) => {
    checkAdminPermission()
    return apiGet(`/api/data/info?db_id=${dbId}`, {}, true)
  },

  /**
   * 删除知识库
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 删除结果
   */
  deleteDatabase: async (dbId) => {
    checkAdminPermission()
    return apiDelete(`/api/data/?db_id=${dbId}`, {}, true)
  },

  /**
   * 上传文件到知识库
   * @param {FormData} formData - 包含文件的FormData
   * @param {string} dbId - 知识库ID
   * @returns {Promise} - 上传结果
   */
  uploadFile: async (formData, dbId) => {
    checkAdminPermission()
    const userStore = useUserStore()
    const authHeaders = userStore.getAuthHeaders()

    return fetch(`/api/data/upload?db_id=${dbId}`, {
      method: 'POST',
      headers: {
        ...authHeaders
      },
      body: formData
    }).then(res => {
      if (!res.ok) {
        throw new Error(`上传失败: ${res.status} ${res.statusText}`)
      }
      return res.json()
    })
  },

  /**
   * 删除文件
   * @param {string} dbId - 知识库ID
   * @param {string} fileId - 文件ID
   * @returns {Promise} - 删除结果
   */
  deleteFile: async (dbId, fileId) => {
    checkAdminPermission()
    return apiDelete('/api/data/document', {
      body: JSON.stringify({ db_id: dbId, file_id: fileId })
    }, true)
  },

  /**
   * 将文件分块
   * @param {Object} data - 分块参数
   * @returns {Promise} - 分块结果
   */
  fileToChunk: async (data) => {
    checkAdminPermission()
    return apiPost('/api/data/file-to-chunk', data, {}, true)
  },

  /**
   * 将分块添加到数据库
   * @param {Object} data - 包含db_id和file_chunks的数据
   * @returns {Promise} - 添加结果
   */
  addByChunks: async (data) => {
    checkAdminPermission()
    return apiPost('/api/data/add-by-chunks', data, {}, true)
  },

  /**
   * 查询测试
   * @param {Object} data - 查询参数
   * @returns {Promise} - 查询结果
   */
  queryTest: async (data) => {
    checkAdminPermission()
    return apiPost('/api/data/query-test', data, {}, true)
  },

  /**
   * 获取文档详情
   * @param {string} dbId - 知识库ID
   * @param {string} fileId - 文件ID
   * @returns {Promise} - 文档详情
   */
  getDocumentDetail: async (dbId, fileId) => {
    checkAdminPermission()
    return apiGet(`/api/data/document?db_id=${dbId}&file_id=${fileId}`, {}, true)
  },

  /**
   * 将URL转换为分块
   * @param {Object} data - 分块参数
   * @returns {Promise} - 分块结果
   */
  urlToChunk: async (data) => {
    checkAdminPermission()
    return apiPost('/api/data/url-to-chunk', data, {}, true)
  },

  /**
   * 更新知识库信息
   * @param {string} dbId - 知识库ID
   * @param {Object} data - 包含name和description的数据对象
   * @returns {Promise} - 更新结果
   */
  updateDatabaseInfo: async (dbId, data) => {
    checkAdminPermission()
    return apiPost('/api/data/update', {
      db_id: dbId,
      ...data
    }, {}, true)
  },
}

// 图数据库管理API
export const graphApi = {
  /**
   * 获取图数据库状态
   * @returns {Promise} - 图数据库状态
   */
  getGraphInfo: async () => {
    checkAdminPermission()
    return apiGet('/api/data/graph', {}, true)
  },

  /**
   * 获取节点
   * @param {string} dbName - 图数据库名称
   * @param {number} num - 节点数量
   * @returns {Promise} - 节点数据
   */
  getNodes: async (dbName, num) => {
    checkAdminPermission()
    return apiGet(`/api/data/graph/nodes?kgdb_name=${dbName}&num=${num}`, {}, true)
  },

  /**
   * 查询实体
   * @param {string} entityName - 实体名称
   * @returns {Promise} - 查询结果
   */
  queryNode: async (entityName) => {
    checkAdminPermission()
    return apiGet(`/api/data/graph/node?entity_name=${entityName}`, {}, true)
  },

  /**
   * 添加JSONL文件到图数据库
   * @param {string} filePath - 文件路径
   * @returns {Promise} - 添加结果
   */
  addByJsonl: async (filePath) => {
    checkAdminPermission()
    return apiPost('/api/data/graph/add-by-jsonl', { file_path: filePath }, {}, true)
  },

  /**
   * 为未索引节点添加索引
   * @param {string} dbName - 图数据库名称
   * @returns {Promise} - 索引结果
   */
  indexNodes: async (dbName) => {
    checkAdminPermission()
    return apiPost('/api/data/graph/index-nodes', { kgdb_name: dbName }, {}, true)
  },
}

// 系统配置API
export const systemConfigApi = {
  /**
   * 设置默认智能体
   * @param {string} agentId - 智能体ID
   * @returns {Promise} - 设置结果
   */
  setDefaultAgent: async (agentId) => {
    checkAdminPermission()
    return apiPost('/api/chat/set_default_agent', { agent_id: agentId }, {}, true)
  },

  /**
   * 获取系统配置
   * @returns {Promise} - 系统配置
   */
  getSystemConfig: async () => {
    checkAdminPermission()
    return apiGet('/api/config', {}, true)
  },

  /**
   * 获取智能体配置
   * @param {string} agentId - 智能体ID
   * @returns {Promise} - 智能体配置
   */
  getAgentConfig: async (agentId) => {
    checkAdminPermission()
    return apiGet(`/api/chat/agent/${agentId}/config`, {}, true)
  },

  /**
   * 保存智能体配置
   * @param {string} agentId - 智能体ID
   * @param {Object} config - 配置内容
   * @returns {Promise} - 保存结果
   */
  saveAgentConfig: async (agentId, config) => {
    checkAdminPermission()
    return apiPost(`/api/chat/agent/${agentId}/config`, config, {}, true)
  },

  /**
   * 更新某个配置
   * @param {Object} items - 配置项
   * @returns {Promise} - 更新结果
   */
  updateConfigItems: async (items) => {
    checkAdminPermission()
    console.log("updateConfigItems", items)
    return apiPost('/api/config/update', items, {}, true)
  },

  /**
   * 重启服务
   * @returns {Promise} - 重启结果
   */
  restartServer: async () => {
    checkSuperAdminPermission()
    return apiPost('/api/restart', {}, {}, true)
  }
}

// 日志API
export const logApi = {
  /**
   * 获取系统日志
   * @param {Object} params - 日志查询参数
   * @returns {Promise} - 日志数据
   */
  getLogs: async (params = {}) => {
    checkAdminPermission()
    return apiGet('/api/log', { params }, true)
  },
}

// 通用admin
export const adminApi = {
  /**
   * 获取所有智能体
   * @param {Object} params - 查询参数
   * @returns {Promise} - 查询结果
   */
  adminGet: async (params, url) => {
    checkAdminPermission()
    return apiGet(url, { params }, true)
  },

  /**
   * 更新某个配置
   * @param {Object} items - 配置项
   * @returns {Promise} - 更新结果
   */
  adminPost: async (data, url) => {
    checkAdminPermission()
    return apiPost(url, data, {}, true)
  },
}
