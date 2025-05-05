import { apiGet, apiPost, apiDelete } from './base'
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
   * 获取可用工具列表
   * @returns {Promise} - 工具列表
   */
  getTools: () => apiGet('/api/chat/tools', {}, true),

  // /**
  //  * 获取对话历史
  //  * @returns {Promise} - 对话历史列表
  //  */
  // getConversations: () => apiGet('/api/chat/conversations', {}, true),

  // /**
  //  * 获取特定对话
  //  * @param {string} conversationId - 对话ID
  //  * @returns {Promise} - 对话详情
  //  */
  // getConversation: (conversationId) =>
  //   apiGet(`/api/chat/conversations/${conversationId}`, {}, true),

  // /**
  //  * 删除对话
  //  * @param {string} conversationId - 对话ID
  //  * @returns {Promise} - 删除结果
  //  */
  // deleteConversation: (conversationId) =>
  //   apiDelete(`/api/chat/conversations/${conversationId}`, {}, true),

  // /**
  //  * 更新对话标题
  //  * @param {string} conversationId - 对话ID
  //  * @param {string} title - 新标题
  //  * @returns {Promise} - 更新结果
  //  */
  // updateConversationTitle: (conversationId, title) =>
  //   apiPost(`/api/chat/conversations/${conversationId}/title`, { title }, {}, true),
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

// 其他需要用户认证的API可以继续添加到这里