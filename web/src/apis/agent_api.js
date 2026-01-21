import {
  apiGet,
  apiPost,
  apiDelete,
  apiPut,
  apiAdminGet,
  apiAdminPost,
  apiAdminDelete,
  apiRequest
} from './base'
import { useUserStore } from '@/stores/user'

/**
 * 智能体API模块
 * 包含智能体管理、聊天、配置等功能
 * 权限要求: 任何已登录用户（普通用户、管理员、超级管理员）
 */

// =============================================================================
// === 智能体聊天分组 ===
// =============================================================================

export const agentApi = {
  /**
   * 发送聊天消息到指定智能体（流式响应）
   * @param {string} agentId - 智能体ID
   * @param {Object} data - 聊天数据
   * @returns {Promise} - 聊天响应流
   */
  sendAgentMessage: (agentId, data, options = {}) => {
    const { signal, headers: extraHeaders, ...restOptions } = options || {}
    const baseHeaders = {
      'Content-Type': 'application/json',
      ...useUserStore().getAuthHeaders()
    }

    return fetch(`/api/chat/agent/${agentId}`, {
      method: 'POST',
      body: JSON.stringify(data),
      signal,
      headers: {
        ...baseHeaders,
        ...(extraHeaders || {})
      },
      ...restOptions
    })
  },

  /**
   * 简单聊天调用（非流式）
   * @param {string} query - 查询内容
   * @returns {Promise} - 聊天响应
   */
  simpleCall: (query) => apiPost('/api/chat/call', { query }),

  /**
   * 获取默认智能体
   * @returns {Promise} - 默认智能体信息
   */
  getDefaultAgent: () => apiGet('/api/chat/default_agent'),

  /**
   * 获取智能体列表
   * @returns {Promise} - 智能体列表
   */
  getAgents: () => apiGet('/api/chat/agent'),

  /**
   * 获取单个智能体详情
   * @param {string} agentId - 智能体ID
   * @returns {Promise} - 智能体详情
   */
  getAgentDetail: (agentId) => apiGet(`/api/chat/agent/${agentId}`),

  /**
   * 获取智能体历史消息
   * @param {string} agentId - 智能体ID
   * @param {string} threadId - 会话ID
   * @returns {Promise} - 历史消息
   */
  getAgentHistory: (agentId, threadId) =>
    apiGet(`/api/chat/agent/${agentId}/history?thread_id=${threadId}`),

  /**
   * 获取指定会话的 AgentState
   * @param {string} agentId - 智能体ID
   * @param {string} threadId - 会话ID
   * @returns {Promise} - AgentState
   */
  getAgentState: (agentId, threadId) =>
    apiGet(`/api/chat/agent/${agentId}/state?thread_id=${threadId}`),

  /**
   * Submit feedback for a message
   * @param {number} messageId - Message ID
   * @param {string} rating - 'like' or 'dislike'
   * @param {string|null} reason - Optional reason for dislike
   * @returns {Promise} - Feedback response
   */
  submitMessageFeedback: (messageId, rating, reason = null) =>
    apiPost(`/api/chat/message/${messageId}/feedback`, { rating, reason }),

  /**
   * Get feedback status for a message
   * @param {number} messageId - Message ID
   * @returns {Promise} - Feedback status
   */
  getMessageFeedback: (messageId) => apiGet(`/api/chat/message/${messageId}/feedback`),

  /**
   * 获取模型提供商的模型列表
   * @param {string} provider - 模型提供商
   * @returns {Promise} - 模型列表
   */
  getProviderModels: (provider) => apiGet(`/api/chat/models?model_provider=${provider}`),

  /**
   * 更新模型提供商的模型列表
   * @param {string} provider - 模型提供商
   * @param {Array} models - 选中的模型列表
   * @returns {Promise} - 更新结果
   */
  updateProviderModels: (provider, models) =>
    apiPost(`/api/chat/models/update?model_provider=${provider}`, models),

  /**
   * 获取智能体配置
   * @param {string} agentName - 智能体名称
   * @returns {Promise} - 智能体配置
   */
  getAgentConfig: async (agentName) => {
    return apiAdminGet(`/api/chat/agent/${agentName}/config`)
  },

  /**
   * 保存智能体配置
   * @param {string} agentName - 智能体名称
   * @param {Object} config - 配置对象
   * @param {Object} options - 额外参数 (e.g., { reload_graph: true })
   * @returns {Promise} - 保存结果
   */
  saveAgentConfig: async (agentName, config, options = {}) => {
    const queryParams = new URLSearchParams(options).toString()
    const url = `/api/chat/agent/${agentName}/config` + (queryParams ? `?${queryParams}` : '')
    return apiAdminPost(url, config)
  },

  getAgentConfigs: (agentId) => apiGet(`/api/chat/agent/${agentId}/configs`),

  getAgentConfigProfile: (agentId, configId) =>
    apiGet(`/api/chat/agent/${agentId}/configs/${configId}`),

  createAgentConfigProfile: (agentId, payload) =>
    apiAdminPost(`/api/chat/agent/${agentId}/configs`, payload),

  updateAgentConfigProfile: (agentId, configId, payload) =>
    apiPut(`/api/chat/agent/${agentId}/configs/${configId}`, payload),

  setAgentConfigDefault: (agentId, configId) =>
    apiAdminPost(`/api/chat/agent/${agentId}/configs/${configId}/set_default`, {}),

  deleteAgentConfigProfile: (agentId, configId) =>
    apiAdminDelete(`/api/chat/agent/${agentId}/configs/${configId}`),

  /**
   * 设置默认智能体
   * @param {string} agentId - 智能体ID
   * @returns {Promise} - 设置结果
   */
  setDefaultAgent: async (agentId) => {
    return apiAdminPost('/api/chat/set_default_agent', { agent_id: agentId })
  },

  /**
   * 恢复被人工审批中断的对话（流式响应）
   * @param {string} agentId - 智能体ID
   * @param {Object} data - 恢复数据 { thread_id, approved }
   * @param {Object} options - 可选参数（signal, headers等）
   * @returns {Promise} - 恢复响应流
   */
  resumeAgentChat: (agentId, data, options = {}) => {
    const { signal, headers: extraHeaders, ...restOptions } = options || {}
    const baseHeaders = {
      'Content-Type': 'application/json',
      ...useUserStore().getAuthHeaders()
    }

    return fetch(`/api/chat/agent/${agentId}/resume`, {
      method: 'POST',
      body: JSON.stringify(data),
      signal,
      headers: {
        ...baseHeaders,
        ...(extraHeaders || {})
      },
      ...restOptions
    })
  }
}

// =============================================================================
// === 多模态图片支持分组 ===
// =============================================================================

export const multimodalApi = {
  /**
   * 上传图片并获取base64编码
   * @param {File} file - 图片文件
   * @returns {Promise} - 上传结果
   */
  uploadImage: (file) => {
    const formData = new FormData()
    formData.append('file', file)

    return apiRequest(
      '/api/chat/image/upload',
      {
        method: 'POST',
        body: formData
      },
      true
    )
  }
}

// =============================================================================
// === 对话线程分组 ===
// =============================================================================

export const threadApi = {
  /**
   * 获取对话线程列表
   * @param {string} agentId - 智能体ID
   * @returns {Promise} - 对话线程列表
   */
  getThreads: (agentId) => {
    const url = `/api/chat/threads?agent_id=${agentId}`
    return apiGet(url)
  },

  /**
   * 创建新对话线程
   * @param {string} agentId - 智能体ID
   * @param {string} title - 对话标题
   * @param {Object} metadata - 元数据
   * @returns {Promise} - 创建结果
   */
  createThread: (agentId, title, metadata) =>
    apiPost('/api/chat/thread', {
      agent_id: agentId,
      title: title || '新的对话',
      metadata: metadata || {}
    }),

  /**
   * 更新对话线程
   * @param {string} threadId - 对话线程ID
   * @param {string} title - 对话标题
   * @param {string} description - 对话描述
   * @returns {Promise} - 更新结果
   */
  updateThread: (threadId, title, description) =>
    apiPut(`/api/chat/thread/${threadId}`, {
      title,
      description
    }),

  /**
   * 删除对话线程
   * @param {string} threadId - 对话线程ID
   * @returns {Promise} - 删除结果
   */
  deleteThread: (threadId) => apiDelete(`/api/chat/thread/${threadId}`),

  /**
   * 获取线程附件列表
   * @param {string} threadId - 对话线程ID
   * @returns {Promise}
   */
  getThreadAttachments: (threadId) => apiGet(`/api/chat/thread/${threadId}/attachments`),

  /**
   * 上传附件
   * @param {string} threadId
   * @param {File} file
   * @returns {Promise}
   */
  uploadThreadAttachment: (threadId, file) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiRequest(`/api/chat/thread/${threadId}/attachments`, {
      method: 'POST',
      body: formData
    })
  },

  /**
   * 删除附件
   * @param {string} threadId
   * @param {string} fileId
   * @returns {Promise}
   */
  deleteThreadAttachment: (threadId, fileId) =>
    apiDelete(`/api/chat/thread/${threadId}/attachments/${fileId}`)
}
