import { apiAdminGet } from './base'

/**
 * Dashboard API模块
 * 用于管理员查看所有用户的对话记录
 */

export const dashboardApi = {
  /**
   * 获取所有对话记录
   * @param {Object} params - 查询参数
   * @param {string} params.user_id - 用户ID过滤
   * @param {string} params.agent_id - 智能体ID过滤
   * @param {string} params.status - 状态过滤 (active/deleted/all)
   * @param {number} params.limit - 每页数量
   * @param {number} params.offset - 偏移量
   * @returns {Promise<Array>} - 对话列表
   */
  getConversations: (params = {}) => {
    const queryParams = new URLSearchParams()
    if (params.user_id) queryParams.append('user_id', params.user_id)
    if (params.agent_id) queryParams.append('agent_id', params.agent_id)
    if (params.status) queryParams.append('status', params.status)
    if (params.limit) queryParams.append('limit', params.limit)
    if (params.offset) queryParams.append('offset', params.offset)

    return apiAdminGet(`/api/dashboard/conversations?${queryParams.toString()}`)
  },

  /**
   * 获取对话详情
   * @param {string} threadId - 对话线程ID
   * @returns {Promise<Object>} - 对话详情
   */
  getConversationDetail: (threadId) => {
    return apiAdminGet(`/api/dashboard/conversations/${threadId}`)
  },

  /**
   * 获取Dashboard统计信息
   * @returns {Promise<Object>} - 统计信息
   */
  getStats: () => {
    return apiAdminGet('/api/dashboard/stats')
  },

  /**
   * 获取用户反馈列表
   * @param {Object} params - 查询参数
   * @param {string} params.rating - 反馈类型过滤 (like/dislike/all)
   * @param {string} params.agent_id - 智能体ID过滤
   * @returns {Promise<Array>} - 反馈列表
   */
  getFeedbacks: (params = {}) => {
    const queryParams = new URLSearchParams()
    if (params.rating && params.rating !== 'all') queryParams.append('rating', params.rating)
    if (params.agent_id) queryParams.append('agent_id', params.agent_id)

    return apiAdminGet(`/api/dashboard/feedbacks?${queryParams.toString()}`)
  },

  // ========== 新增并行API接口 ==========

  /**
   * 获取用户活跃度统计
   * @returns {Promise<Object>} - 用户活跃度统计信息
   */
  getUserStats: () => {
    return apiAdminGet('/api/dashboard/stats/users')
  },

  /**
   * 获取工具调用统计
   * @returns {Promise<Object>} - 工具调用统计信息
   */
  getToolStats: () => {
    return apiAdminGet('/api/dashboard/stats/tools')
  },

  /**
   * 获取知识库统计
   * @returns {Promise<Object>} - 知识库统计信息
   */
  getKnowledgeStats: () => {
    return apiAdminGet('/api/dashboard/stats/knowledge')
  },

  /**
   * 获取AI智能体分析数据
   * @returns {Promise<Object>} - AI智能体分析信息
   */
  getAgentStats: () => {
    return apiAdminGet('/api/dashboard/stats/agents')
  },

  /**
   * 批量获取所有统计数据（并行请求）
   * @returns {Promise<Object>} - 所有统计数据
   */
  getAllStats: async () => {
    try {
      const [basicStats, userStats, toolStats, knowledgeStats, agentStats] = await Promise.all([
        apiAdminGet('/api/dashboard/stats'),
        apiAdminGet('/api/dashboard/stats/users'),
        apiAdminGet('/api/dashboard/stats/tools'),
        apiAdminGet('/api/dashboard/stats/knowledge'),
        apiAdminGet('/api/dashboard/stats/agents')
      ])

      return {
        basic: basicStats,
        users: userStats,
        tools: toolStats,
        knowledge: knowledgeStats,
        agents: agentStats
      }
    } catch (error) {
      console.error('批量获取统计数据失败:', error)
      throw error
    }
  },

  /**
   * 获取调用统计时间序列数据
   * @param {string} type - 数据类型 (models/agents/tokens/tools)
   * @param {string} timeRange - 时间范围 (14hours/14days/14weeks)
   * @returns {Promise<Object>} - 时间序列统计数据
   */
  getCallTimeseries: (type = 'models', timeRange = '14days') => {
    return apiAdminGet(`/api/dashboard/stats/calls/timeseries?type=${type}&time_range=${timeRange}`)
  }
}
