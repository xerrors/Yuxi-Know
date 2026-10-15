import { apiGet, apiPost } from './base'

export const sandboxApi = {
  get: () => apiGet('/api/user/sandbox'),
  rebuild: () => apiPost('/api/user/sandbox/rebuild'),
  diskUsage: () => apiPost('/api/user/sandbox/disk-usage')
}
