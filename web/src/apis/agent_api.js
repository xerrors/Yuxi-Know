import {
  apiGet,
  apiPost,
  apiDelete,
  apiPut,
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
   * @param {Object} data - 聊天数据
   * @returns {Promise} - 聊天响应流
   */
  sendAgentMessage: (data, options = {}) => {
    const { signal, headers: extraHeaders, ...restOptions } = options || {}
    const baseHeaders = {
      'Content-Type': 'application/json',
      ...useUserStore().getAuthHeaders()
    }

    return fetch('/api/chat/agent', {
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
   * 生成对话标题
   * @param {string} query - 查询内容
   * @param {Object} modelSpec - 模型配置
   * @returns {Promise<string>} - 生成的标题
   */
  generateTitle: async (query, modelSpec) => {
    const response = await apiPost('/api/chat/call', {
      query: `根据以下对话内容生成一个简短的标题（最多30个字符，中英文均可），不要包含 markdown 标记：\n\n${query.slice(0, 2000)}`,
      meta: { model_spec: modelSpec }
    })
    return response.response
  },

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
  getAgentHistory: (threadId) => apiGet(`/api/chat/thread/${threadId}/history`),

  /**
   * 获取指定会话的 AgentState
   * @param {string} agentId - 智能体ID
   * @param {string} threadId - 会话ID
   * @returns {Promise} - AgentState
   */
  getAgentState: (threadId) => apiGet(`/api/chat/thread/${threadId}/state`),

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
   * @param {Object} data - 恢复数据 { thread_id, answer: { question_id: answer }, approved }
   * @param {Object} options - 可选参数（signal, headers等）
   * @returns {Promise} - 恢复响应流
   */
  resumeAgentChat: (threadId, data, options = {}) => {
    const { signal, headers: extraHeaders, ...restOptions } = options || {}
    const baseHeaders = {
      'Content-Type': 'application/json',
      ...useUserStore().getAuthHeaders()
    }

    return fetch(`/api/chat/thread/${threadId}/resume`, {
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
   * 创建异步运行任务（Run）
   * @param {Object} data - run 请求体
   * @returns {Promise<Object>}
   */
  createAgentRun: (data) =>
    apiPost('/api/chat/runs', {
      query: data.query,
      agent_config_id: data.agent_config_id,
      thread_id: data.thread_id,
      meta: data.meta || {},
      image_content: data.image_content || null
    }),

  /**
   * 获取 Run 状态
   * @param {string} runId - run ID
   * @returns {Promise<Object>}
   */
  getAgentRun: (runId) => apiGet(`/api/chat/runs/${runId}`),

  /**
   * 取消 Run
   * @param {string} runId - run ID
   * @returns {Promise<Object>}
   */
  cancelAgentRun: (runId) => apiPost(`/api/chat/runs/${runId}/cancel`, {}),

  /**
   * 获取线程活跃 Run
   * @param {string} threadId - 线程ID
   * @returns {Promise<Object>}
   */
  getThreadActiveRun: (threadId) => apiGet(`/api/chat/thread/${threadId}/active_run`),

  /**
   * 打开 Run 事件 SSE 连接（调用方负责关闭）
   * @param {string} runId - run ID
   * @param {string|number} afterSeq - 起始 seq/cursor
   * @param {Object} options - { signal }
   * @returns {Promise<Response>}
   */
  streamAgentRunEvents: (runId, afterSeq = '0', options = {}) => {
    const { signal } = options
    return fetch(
      `/api/chat/runs/${runId}/events?after_seq=${encodeURIComponent(String(afterSeq))}`,
      {
        method: 'GET',
        headers: {
          ...useUserStore().getAuthHeaders()
        },
        signal
      }
    )
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
   * @param {string | null | undefined} agentId - 智能体ID，可选；不传时返回全部智能体对话
   * @param {number} limit - 返回数量限制，默认100
   * @param {number} offset - 偏移量，默认0
   * @returns {Promise} - 对话线程列表
   */
  getThreads: (agentId = null, limit = 100, offset = 0) => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset)
    })
    if (agentId) {
      params.set('agent_id', agentId)
    }
    const url = `/api/chat/threads?${params.toString()}`
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
   * @param {boolean} is_pinned - 是否置顶
   * @returns {Promise} - 更新结果
   */
  updateThread: (threadId, title, is_pinned) =>
    apiPut(`/api/chat/thread/${threadId}`, {
      title,
      is_pinned
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
   * 列出线程文件（目录）
   * @param {string} threadId
   * @param {string} path
   * @param {boolean} recursive
   * @returns {Promise}
   */
  listThreadFiles: (threadId, path = '/home/gem/user-data', recursive = false) =>
    apiGet(
      `/api/chat/thread/${threadId}/files?path=${encodeURIComponent(path)}&recursive=${recursive}`
    ),

  /**
   * 读取线程文本文件内容（分页）
   * @param {string} threadId
   * @param {string} path
   * @param {number} offset
   * @param {number} limit
   * @returns {Promise}
   */
  readThreadFile: (threadId, path, offset = 0, limit = 2000) =>
    apiGet(
      `/api/chat/thread/${threadId}/files/content?path=${encodeURIComponent(path)}&offset=${offset}&limit=${limit}`
    ),

  /**
   * 获取线程文件下载/预览 URL
   * @param {string} threadId
   * @param {string} path
   * @param {boolean} download
   * @returns {string}
   */
  getThreadArtifactUrl: (threadId, path, download = false) => {
    const encodedPath = path
      .split('/')
      .filter(Boolean)
      .map((segment) => encodeURIComponent(segment))
      .join('/')
    const query = download ? '?download=true' : ''
    return `/api/chat/thread/${threadId}/artifacts/${encodedPath}${query}`
  },

  /**
   * 下载线程文件（带鉴权）
   * @param {string} threadId
   * @param {string} path
   * @returns {Promise<Response>}
   */
  downloadThreadArtifact: (threadId, path) =>
    apiGet(threadApi.getThreadArtifactUrl(threadId, path, true), {}, true, 'blob'),

  /**
   * 保存交付物到 workspace/saved_artifacts
   * @param {string} threadId
   * @param {string} path
   * @returns {Promise}
   */
  saveThreadArtifactToWorkspace: (threadId, path) =>
    apiPost(`/api/chat/thread/${threadId}/artifacts/save`, { path }),

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
