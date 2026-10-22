import assert from 'node:assert/strict'
import test from 'node:test'

import {
  COOPERATION_DEPTH_KEY,
  applyCooperationDepth
} from '../../src/modules/settings/model/cooperationDepth.js'

test('协作深度只提交完整的非负整数，清空或非法输入保留原配置', () => {
  assert.equal(COOPERATION_DEPTH_KEY, 'max_cooperation_depth')
  const writes = []
  for (const input of [null, undefined, '', '2', -1, 1.5, 0, 2]) {
    applyCooperationDepth(input, (value) => writes.push([COOPERATION_DEPTH_KEY, value]))
  }

  assert.deepEqual(writes, [
    [COOPERATION_DEPTH_KEY, 0],
    [COOPERATION_DEPTH_KEY, 2]
  ])
})
