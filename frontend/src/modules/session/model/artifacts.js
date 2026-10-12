/** 提取交付物路径，兼容旧 checkpoint 对象并按路径保序去重。 */
export function normalizeArtifacts(artifacts = []) {
  const byPath = new Map()
  for (const item of artifacts) {
    const path = typeof item === 'string' ? item.trim() : item?.path?.trim()
    if (!path) continue
    byPath.set(path, { path })
  }
  return [...byPath.values()]
}
