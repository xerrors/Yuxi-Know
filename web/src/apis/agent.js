import { apiGet, apiPost, apiDelete, apiPut, apiAdminGet, apiAdminPost } from './base'
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
  sendAgentMessage: (agentId, data) => {
    return fetch(`/api/chat/agent/${agentId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...useUserStore().getAuthHeaders()
      },
      body: JSON.stringify(data)
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
  getAgentHistory: (agentId, threadId) => apiGet(`/api/chat/agent/${agentId}/history?thread_id=${threadId}`),

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
  updateProviderModels: (provider, models) => apiPost(`/api/chat/models/update?model_provider=${provider}`, models),

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
   * @returns {Promise} - 保存结果
   */
  saveAgentConfig: async (agentName, config) => {
    return apiAdminPost(`/api/chat/agent/${agentName}/config`, config)
  },

  /**
   * 设置默认智能体
   * @param {string} agentId - 智能体ID
   * @returns {Promise} - 设置结果
   */
  setDefaultAgent: async (agentId) => {
    return apiAdminPost('/api/chat/set_default_agent', { agent_id: agentId })
  },

  /**
   * 获取所有可用工具的信息
   * @returns {Promise} - 工具信息列表
   */
  getTools: () => apiGet('/api/tool/tools')
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
    const url = agentId ? `/api/chat/threads?agent_id=${agentId}` : '/api/chat/threads';
    return apiGet(url);
  },

  /**
   * 创建新对话线程
   * @param {string} agentId - 智能体ID
   * @param {string} title - 对话标题
   * @param {Object} metadata - 元数据
   * @returns {Promise} - 创建结果
   */
  createThread: (agentId, title, metadata) => apiPost('/api/chat/thread', {
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
  updateThread: (threadId, title, description) => apiPut(`/api/chat/thread/${threadId}`, {
    title,
    description
  }),

  /**
   * 删除对话线程
   * @param {string} threadId - 对话线程ID
   * @returns {Promise} - 删除结果
   */
  deleteThread: (threadId) => apiDelete(`/api/chat/thread/${threadId}`)
};