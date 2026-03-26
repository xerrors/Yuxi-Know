import { apiGet, apiPost, apiPut, apiDelete } from './base'

export const apikeyApi = {
  list: (skip = 0, limit = 100) => apiGet('/api/apikey/', { params: { skip, limit } }),

  create: (data) => apiPost('/api/apikey/', data),

  get: (id) => apiGet(`/api/apikey/${id}`),

  update: (id, data) => apiPut(`/api/apikey/${id}`, data),

  delete: (id) => apiDelete(`/api/apikey/${id}`),

  regenerate: (id) => apiPost(`/api/apikey/${id}/regenerate`)
}
