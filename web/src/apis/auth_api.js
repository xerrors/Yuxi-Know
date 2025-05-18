import { apiGet, apiPost, apiDelete, apiPut } from './base'
import { useUserStore } from '@/stores/user'

/**
 * 需要用户认证的API模块
 * 用户必须登录才能访问的API
 * 权限要求: 任何已登录用户（普通用户、管理员、超级管理员）
 */

// 聊天相关API
export const chatApi = {
  /**
   * 发送聊天消息
   * @param {Object} params - 聊天参数
   * @returns {Promise} - 聊天响应流
   */
  sendMessage: (params) => {
    return fetch('/api/chat/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...useUserStore().getAuthHeaders()
      },
      body: JSON.stringify(params),
    })
  },

  /**
   * 发送可中断的聊天消息
   * @param {Object} params - 聊天参数
   * @param {AbortSignal} signal - 用于中断请求的信号控制器
   * @returns {Promise} - 聊天响应流
   */
  sendMessageWithAbort: (params, signal) => {
    return fetch('/api/chat/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...useUserStore().getAuthHeaders()
      },
      body: JSON.stringify(params),
      signal // 添加 signal 用于中断请求
    })
  },

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
  simpleCall: (query) => apiPost('/api/chat/call', { query }, {}, true),

  /**
   * 获取默认智能体
   * @returns {Promise} - 默认智能体信息
   */
  getDefaultAgent: () => apiGet('/api/chat/default_agent', {}, true),

  /**
   * 获取智能体列表
   * @returns {Promise} - 智能体列表
   */
  getAgents: () => apiGet('/api/chat/agent', {}, true),

  /**
   * 获取单个智能体详情
   * @param {string} agentId - 智能体ID
   * @returns {Promise} - 智能体详情
   */
  getAgentDetail: (agentId) => apiGet(`/api/chat/agent/${agentId}`, {}, true),

  /**
   * 获取智能体历史消息
   * @param {string} agentName - 智能体名称
   * @param {string} threadId - 会话ID
   * @returns {Promise} - 历史消息
   */
  getAgentHistory: (agentName, threadId) => apiGet(`/api/chat/agent/${agentName}/history?thread_id=${threadId}`, {}, true),

  /**
   * 获取可用工具列表
   * @returns {Promise} - 工具列表
   */
  getTools: () => apiGet('/api/chat/tools', {}, true),

  /**
   * 获取模型提供商的模型列表
   * @param {string} provider - 模型提供商
   * @returns {Promise} - 模型列表
   */
  getProviderModels: (provider) => {
    return fetch(`/api/chat/models?model_provider=${provider}`, {
      headers: {
        ...useUserStore().getAuthHeaders()
      }
    }).then(response => response.json())
  },

  /**
   * 更新模型提供商的模型列表
   * @param {string} provider - 模型提供商
   * @param {Array} models - 选中的模型列表
   * @returns {Promise} - 更新结果
   */
  updateProviderModels: (provider, models) => {
    return fetch(`/api/chat/models/update?model_provider=${provider}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...useUserStore().getAuthHeaders()
      },
      body: JSON.stringify(models)
    }).then(response => response.json())
  }
}

// 用户设置API
export const userSettingsApi = {
  /**
   * 获取用户设置
   * @returns {Promise} - 用户设置
   */
  getSettings: () => apiGet('/api/user/settings', {}, true),

  /**
   * 更新用户设置
   * @param {Object} settings - 新设置
   * @returns {Promise} - 更新结果
   */
  updateSettings: (settings) => apiPost('/api/user/settings', settings, {}, true),
}

// 对话线程相关API
export const threadApi = {
  /**
   * 获取对话线程列表
   * @param {string} agentId - 智能体ID
   * @returns {Promise} - 对话线程列表
   */
  getThreads: (agentId) => {
    const url = agentId ? `/api/chat/threads?agent_id=${agentId}` : '/api/chat/threads';
    return apiGet(url, {}, true);
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
    title: title || '新对话',
    metadata: metadata || {}
  }, {}, true),

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
  }, {}, true),

  /**
   * 删除对话线程
   * @param {string} threadId - 对话线程ID
   * @returns {Promise} - 删除结果
   */
  deleteThread: (threadId) => apiDelete(`/api/chat/thread/${threadId}`, {}, true)
};

// 其他需要用户认证的API可以继续添加到这里