/** 管理列表按创建时间正序；搜索只过滤展示，不修改来源。 */
export function filterAndSortAgents(agents, keyword) {
  const normalized = String(keyword || '')
    .trim()
    .toLowerCase()
  const list = agents || []
  const filtered = normalized
    ? list.filter((agent) =>
        [agent.name, agent.agent_id, agent.backend_id].some((value) =>
          String(value || '')
            .toLowerCase()
            .includes(normalized)
        )
      )
    : list
  return [...filtered].sort(
    (a, b) => Date.parse(a.created_at) - Date.parse(b.created_at) || a.id - b.id
  )
}
