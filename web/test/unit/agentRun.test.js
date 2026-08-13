import assert from 'node:assert/strict'
import test from 'node:test'

import { isSteerableMainChatRun } from '../../src/utils/agentRun.js'

test('Steer is exposed only for running main Chat requests', () => {
  assert.equal(
    isSteerableMainChatRun({ status: 'running', run_type: 'chat', source: 'chat' }),
    true
  )
  assert.equal(isSteerableMainChatRun({ status: 'pending', run_type: 'chat', source: 'chat' }), false)
  assert.equal(isSteerableMainChatRun({ status: 'running', run_type: 'resume', source: 'chat' }), false)
  assert.equal(
    isSteerableMainChatRun({ status: 'running', run_type: 'chat', source: 'agent_call' }),
    false
  )
})
