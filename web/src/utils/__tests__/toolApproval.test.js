import assert from 'node:assert/strict'

import {
  buildToolApprovalDecisions,
  hasPendingInterruptPayload,
  isRunInterruptedConflict,
  isThreadWaitingForUserAction,
  isToolApprovalMode,
  resolveToolApprovalMode
} from '../toolApproval.js'

assert.equal(isToolApprovalMode('default'), true)
assert.equal(isToolApprovalMode('always_trust'), true)
assert.equal(isToolApprovalMode('unknown'), false)
assert.equal(
  resolveToolApprovalMode({
    hasThread: false,
    savedMode: 'always_trust',
    agentMode: 'default'
  }),
  'always_trust'
)
assert.equal(
  resolveToolApprovalMode({
    hasThread: false,
    agentMode: 'always_trust'
  }),
  'always_trust'
)
assert.equal(
  resolveToolApprovalMode({
    hasThread: true,
    threadMode: 'default',
    savedMode: 'always_trust',
    agentMode: 'always_trust'
  }),
  'default'
)
assert.equal(
  resolveToolApprovalMode({
    hasThread: true,
    savedMode: 'always_trust',
    agentMode: 'always_trust'
  }),
  'default'
)

assert.deepEqual(buildToolApprovalDecisions({ 0: 'approve', 1: 'reject' }, 2), [
  { type: 'approve' },
  { type: 'reject', message: '用户拒绝执行该操作' }
])
assert.equal(hasPendingInterruptPayload({ kind: 'question', questions: [{}] }), true)
assert.equal(hasPendingInterruptPayload({ kind: 'tool_approval', actionRequests: [{}] }), true)
assert.equal(hasPendingInterruptPayload({ kind: 'tool_approval', actionRequests: [] }), false)
assert.equal(
  isThreadWaitingForUserAction({
    pendingInterrupt: { kind: 'question', questions: [{ id: 'q-1' }] }
  }),
  true
)
assert.equal(isThreadWaitingForUserAction({ queueSnapshot: { status: 'interrupted' } }), true)
assert.equal(
  isThreadWaitingForUserAction({
    pendingInterrupt: null,
    queueSnapshot: { status: 'paused' }
  }),
  false
)
assert.equal(
  isRunInterruptedConflict({
    response: { status: 409, data: { detail: { code: 'run_interrupted' } } }
  }),
  true
)
assert.equal(isRunInterruptedConflict(new Error('线程正在等待用户回答或审批')), false)

console.log('toolApproval: all assertions passed')
