import { apiDelete, apiGet, apiPost } from './base'

const buildQuery = (params) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value))
    }
  })
  return query.toString()
}

const buildViewerQuery = (threadId, path, agentId = null, agentConfigId = null) => {
  return buildQuery({
    thread_id: threadId,
    path,
    agent_id: agentId,
    agent_config_id: agentConfigId
  })
}

export const getViewerFileSystemTree = (
  threadId,
  path = '/',
  agentId = null,
  agentConfigId = null
) => {
  const query = buildViewerQuery(threadId, path, agentId, agentConfigId)
  return apiGet(`/api/viewer/filesystem/tree?${query}`)
}

export const getViewerFileContent = (threadId, path, agentId = null, agentConfigId = null) => {
  const query = buildViewerQuery(threadId, path, agentId, agentConfigId)
  return apiGet(`/api/viewer/filesystem/file?${query}`)
}

export const downloadViewerFile = (threadId, path, agentId = null, agentConfigId = null) => {
  const query = buildViewerQuery(threadId, path, agentId, agentConfigId)
  return apiGet(`/api/viewer/filesystem/download?${query}`, {}, true, 'blob')
}

export const deleteViewerFile = (threadId, path, agentId = null, agentConfigId = null) => {
  const query = buildViewerQuery(threadId, path, agentId, agentConfigId)
  return apiDelete(`/api/viewer/filesystem/file?${query}`)
}

export const createViewerDirectory = (
  threadId,
  parentPath,
  name,
  agentId = null,
  agentConfigId = null
) => {
  return apiPost('/api/viewer/filesystem/directory', {
    thread_id: threadId,
    parent_path: parentPath,
    name,
    agent_id: agentId,
    agent_config_id: agentConfigId
  })
}

export const uploadViewerFile = (
  threadId,
  parentPath,
  file,
  agentId = null,
  agentConfigId = null
) => {
  const formData = new FormData()
  formData.set('thread_id', threadId)
  formData.set('parent_path', parentPath)
  if (agentId !== undefined && agentId !== null && agentId !== '') {
    formData.set('agent_id', agentId)
  }
  if (agentConfigId !== undefined && agentConfigId !== null && agentConfigId !== '') {
    formData.set('agent_config_id', agentConfigId)
  }
  formData.set('file', file)
  return apiPost('/api/viewer/filesystem/upload', formData)
}
