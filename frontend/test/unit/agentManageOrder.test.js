import assert from 'node:assert/strict'
import test from 'node:test'

import { filterAndSortAgents } from '../../src/modules/agents/model/agentOrder.js'

test('管理列表按创建时间正序，搜索与重命名保持顺序且不修改来源', () => {
  const managedAgents = [
    {
      id: 4,
      name: 'Y 问答',
      agent_id: 'same-time',
      backend_id: 'ChatbotAgent',
      is_builtin: true,
      created_at: '2026-10-02T03:00:00Z'
    },
    {
      id: 1,
      name: 'A 内置',
      agent_id: 'builtin',
      backend_id: 'ChatbotAgent',
      is_builtin: true,
      created_at: '2026-10-01T00:00:00Z'
    },
    {
      id: 3,
      name: 'Z 问答',
      agent_id: 'newer',
      backend_id: 'WorkerAgent',
      created_at: '2026-10-02T03:00:00Z'
    },
    {
      id: 9,
      name: 'B 问答',
      agent_id: 'older',
      backend_id: 'WorkerAgent',
      created_at: '2026-10-02T10:00:00+08:00'
    }
  ]

  assert.deepEqual(
    filterAndSortAgents(managedAgents, '').map((agent) => agent.id),
    [1, 9, 3, 4]
  )
  assert.deepEqual(
    filterAndSortAgents(managedAgents, '问答').map((agent) => agent.id),
    [9, 3, 4]
  )
  assert.deepEqual(
    filterAndSortAgents(managedAgents, ' older ').map((agent) => agent.id),
    [9]
  )
  assert.deepEqual(
    filterAndSortAgents(managedAgents, '  CHATBOTAGENT  ').map((agent) => agent.id),
    [1, 4]
  )
  assert.deepEqual(
    filterAndSortAgents(managedAgents, 'workeragent').map((agent) => agent.id),
    [9, 3]
  )
  managedAgents[2].name = 'A 问答'
  assert.deepEqual(
    filterAndSortAgents(managedAgents, '问答').map((agent) => agent.id),
    [9, 3, 4]
  )
  assert.deepEqual(
    managedAgents.map((agent) => agent.id),
    [4, 1, 3, 9]
  )
  assert.deepEqual(filterAndSortAgents(managedAgents, '没有匹配'), [])
})
