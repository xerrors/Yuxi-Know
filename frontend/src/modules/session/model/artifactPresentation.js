import { normalizeArtifacts } from './artifacts.js'

/** 交付路径倒序展示为文件项，保持原始字符串路径的稳定身份。 */
export function buildArtifactItems(artifacts) {
  return normalizeArtifacts(artifacts)
    .reverse()
    .map((path) => ({ path, name: path.split('/').pop() || path }))
}

/** 折叠时只展示前三项，展开时展示全部。 */
export function visibleArtifactItems(items, expanded) {
  return expanded ? items : items.slice(0, 3)
}
