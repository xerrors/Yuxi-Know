/** 对交付物字符串路径保序去重。 */
export function normalizeArtifacts(artifacts = []) {
  return [...new Set(artifacts.map((path) => path.trim()).filter(Boolean))]
}
