export const createSearchConfigSnapshot = (queryParams, meta) => {
  const snapshot = {}
  for (const param of queryParams) {
    snapshot[param.key] = meta[param.key]
  }
  return snapshot
}

export const searchConfigChanged = (currentConfig, initialConfig) =>
  JSON.stringify(currentConfig) !== JSON.stringify(initialConfig)
