import { apiGet, apiPost, apiPut, apiDelete } from './base'

// 爬虫服务统一网关前缀：
// 前端请求 /api_v1/...，由 Vite 代理到后端 http://crawler-host/api/v1/...
// 具体代理规则见 vite.config.js 中 '^/api_v1' 配置。
const crawlerBase = 'http://8.148.22.98/crawler-api'

const buildQuery = (params = {}) => {
  const search = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    search.append(key, String(value))
  })
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

export const crawlerApi = {
  // 基础与单次抽取 ------------------------------------------------
  health: async () => {
    return apiGet(`${crawlerBase}/health`, {}, false)
  },

  extractOnce: async (payload) => {
    return apiPost(`${crawlerBase}/extract`, payload, {}, false)
  },

  getExtractResult: async (jobId) => {
    return apiGet(`${crawlerBase}/extract/${jobId}`, {}, false)
  },

  // 监控任务管理 --------------------------------------------------
  getTasks: async (params = {}) => {
    return apiGet(`${crawlerBase}/tasks${buildQuery(params)}`, {}, false)
  },

  createTask: async (payload) => {
    return apiPost(`${crawlerBase}/tasks`, payload, {}, false)
  },

  updateTask: async (taskId, payload) => {
    return apiPut(`${crawlerBase}/tasks/${taskId}`, payload, {}, false)
  },

  runTask: async (taskId) => {
    return apiPost(`${crawlerBase}/tasks/${taskId}/run`, {}, {}, false)
  },

  toggleTask: async (taskId, active) => {
    return apiPost(`${crawlerBase}/tasks/${taskId}/toggle`, { active: !!active }, {}, false)
  },

  deleteTask: async (taskId) => {
    return apiDelete(`${crawlerBase}/tasks/${taskId}`, {}, false)
  },

  getTaskResults: async (taskId, params = {}) => {
    return apiGet(
      `${crawlerBase}/tasks/${taskId}/results${buildQuery(params)}`,
      {},
      false
    )
  },

  // 执行任务与页面日志 --------------------------------------------
  getJobs: async (params = {}) => {
    return apiGet(`${crawlerBase}/jobs${buildQuery(params)}`, {}, false)
  },

  getJobPages: async (jobId, params = {}) => {
    return apiGet(
      `${crawlerBase}/jobs/${jobId}/pages${buildQuery(params)}`,
      {},
      false
    )
  },

  // 日志与页面库 --------------------------------------------------
  getLogs: async (params = {}) => {
    return apiGet(`${crawlerBase}/logs${buildQuery(params)}`, {}, false)
  },

  exportLogsUrl: (params = {}) => {
    return `${crawlerBase}/logs/export${buildQuery(params)}`
  },

  getResults: async (params = {}) => {
    return apiGet(`${crawlerBase}/results${buildQuery(params)}`, {}, false)
  },

  // 概览统计（如需使用可直接调用） ------------------------------
  getDashboardStats: async () => {
    return apiGet(`${crawlerBase}/dashboard/stats`, {}, false)
  },

  getDashboardChart: async (period = '7d') => {
    return apiGet(
      `${crawlerBase}/dashboard/chart${buildQuery({ period })}`,
      {},
      false
    )
  },

  getDashboardAlerts: async () => {
    return apiGet(`${crawlerBase}/dashboard/alerts`, {}, false)
  }
}

