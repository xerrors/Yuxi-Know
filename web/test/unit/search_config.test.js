import assert from 'node:assert/strict'
import test from 'node:test'

import { createSearchConfigSnapshot, searchConfigChanged } from '../../src/utils/searchConfig.js'

test('检索配置快照只包含服务端声明的参数', () => {
  const snapshot = createSearchConfigSnapshot(
    [{ key: 'top_k' }, { key: 'use_rerank' }],
    { top_k: 5, use_rerank: true, stale_local_value: 'ignore' }
  )

  assert.deepEqual(snapshot, { top_k: 5, use_rerank: true })
})

test('检索配置恢复原值后不再标记为 dirty', () => {
  const initial = { top_k: 5, use_rerank: true }

  assert.equal(searchConfigChanged({ top_k: 10, use_rerank: true }, initial), true)
  assert.equal(searchConfigChanged({ top_k: 5, use_rerank: true }, initial), false)
})
