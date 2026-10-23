import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, before, test } from 'node:test'
import { computed, reactive, ref, toRaw } from 'vue'
import { createTestServer } from '../helpers/createTestServer.js'

const source = readFileSync(
  new URL('../../src/modules/session/ui/SessionWorkspace.vue', import.meta.url),
  'utf8'
)
let server, useApproval

before(async () => {
  server = await createTestServer({ server: { middlewareMode: true, hmr: false } })
  ;({ useApproval } = await server.ssrLoadModule('/src/modules/session/model/useApproval.js'))
})
after(async () => server?.close())

/** 执行组件真实提交入口，允许在请求未返回时推进共享运行状态。 */
function setupSubmission({ accepted = false } = {}) {
  const original = {
    threadId: 'thread',
    interruptedRunId: 'run-A',
    waitpointId: 'wait-A',
    kind: 'question',
    questions: [{ question_id: 'q-A', question: '旧问题' }]
  }
  const state = reactive({
    currentTurnId: 'turn',
    activeRunId: 'run-A',
    runStateVersion: 1,
    turnStatus: 'requires_action',
    pendingInterrupt: original,
    approvalSubmitting: false,
    isStreaming: false,
    replyLoadingVisible: false
  })
  const getThreadState = () => state
  const approval = useApproval({ getThreadState, fetchThreadMessages() {} })
  approval.restoreInterruptFromThreadState('thread')
  const errors = []
  let rejectRequest
  const pending = new Promise((_, reject) => { rejectRequest = reject })
  const dependencies = {
    approvalSubmitting: computed(() => state.approvalSubmitting),
    approvalState: approval.approvalState,
    getThreadState,
    message: { error: (error) => errors.push(error) },
    resumeSessionWaitpoint: () => accepted ? { run_id: 'run-B' } : pending,
    invalidateAgentStateRequest() {},
    hideApprovalState: approval.hideApprovalState,
    resetThreadExecution() {},
    fetchThreadMessages() {},
    startRunStream: () => pending,
    restorePendingInterruptForThread: approval.restoreInterruptFromThreadState,
    handleChatError: (error) => errors.push(error)
  }
  const handler = source.slice(
    source.indexOf('const handleApprovalWithStream ='),
    source.indexOf('const handleQuestionSubmit =')
  )
  const submit = new Function(
    ...Object.keys(dependencies),
    `${handler}; return handleApprovalWithStream`
  )(...Object.values(dependencies))
  const visibility = source.slice(
    source.indexOf('const currentApprovalModalVisible ='),
    source.indexOf('const currentApprovalQuestions =')
  )
  const visible = new Function(
    'computed', 'approvalState', 'visibleApprovalThreadId', 'currentThreadState',
    `${visibility}; return currentApprovalModalVisible`
  )(computed, approval.approvalState, ref('thread'), ref(state))
  return { state, approval, submit, visible, errors, reject: () => rejectRequest(new Error('延迟失败')) }
}

test('原审批未变化时提交失败，保留审批并允许重试', async () => {
  const h = setupSubmission()
  const pendingInterrupt = h.state.pendingInterrupt
  const submitting = h.submit({ 'q-A': '回答' })
  assert.equal(h.state.approvalSubmitting, true)
  h.reject()
  await submitting
  assert.equal(h.state.pendingInterrupt, pendingInterrupt)
  assert.equal(h.visible.value, true)
  assert.equal(h.state.isStreaming, false)
  assert.equal(h.state.approvalSubmitting, false)
  assert.equal(h.errors[0].message, '延迟失败')
})

for (const status of ['in_progress', 'completed', 'requires_action']) {
  test(`旧审批提交失败不能覆盖后续状态：${status}`, async () => {
    const h = setupSubmission()
    const submitting = h.submit({ 'q-A': '回答' })
    Object.assign(h.state, {
      activeRunId: status === 'completed' ? null : 'run-B',
      runStateVersion: 2,
      turnStatus: status,
      pendingInterrupt: status === 'requires_action' ? {
        threadId: 'thread', interruptedRunId: 'run-B', waitpointId: 'wait-B',
        kind: 'question', questions: [{ question_id: 'q-B', question: '新问题' }]
      } : null,
      isStreaming: status === 'in_progress',
      replyLoadingVisible: status === 'in_progress'
    })
    h.approval.hideApprovalState()
    if (status === 'requires_action') h.approval.restoreInterruptFromThreadState('thread')
    const expected = structuredClone(toRaw(h.state))
    h.reject()
    await submitting
    assert.deepEqual({ ...h.state }, { ...expected, approvalSubmitting: false })
    assert.equal(h.visible.value, status === 'requires_action')
    assert.equal(h.approval.approvalState.interruptedRunId, status === 'requires_action' ? 'run-B' : null)
  })
}

test('审批已接受后续跑连接失败，不能恢复已消费的旧审批', async () => {
  const h = setupSubmission({ accepted: true })
  const submitting = h.submit({ 'q-A': '回答' })
  await Promise.resolve()
  await Promise.resolve()
  assert.equal(h.state.pendingInterrupt, null)
  assert.equal(h.visible.value, false)
  h.reject()
  await submitting
  assert.equal(h.state.pendingInterrupt, null)
  assert.equal(h.visible.value, false)
  assert.equal(h.state.isStreaming, true)
  assert.equal(h.state.approvalSubmitting, false)
})
