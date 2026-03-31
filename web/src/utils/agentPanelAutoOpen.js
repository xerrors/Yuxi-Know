const USER_DATA_UPLOADS_PREFIX = '/home/gem/user-data/uploads/'
const USER_DATA_OUTPUTS_PREFIX = '/home/gem/user-data/outputs/'

const isTrackedPanelFilePath = (path) => {
  const normalizedPath = String(path || '')
  return (
    normalizedPath.startsWith(USER_DATA_UPLOADS_PREFIX) ||
    normalizedPath.startsWith(USER_DATA_OUTPUTS_PREFIX)
  )
}

export const shouldAutoOpenAgentPanel = (threadFiles) => {
  if (!Array.isArray(threadFiles) || threadFiles.length === 0) return false

  return threadFiles.some((item) => item?.is_dir !== true && isTrackedPanelFilePath(item?.path))
}

export { USER_DATA_OUTPUTS_PREFIX, USER_DATA_UPLOADS_PREFIX }
