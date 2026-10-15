import assert from 'node:assert/strict'
import test from 'node:test'

import { useAgentThreadState } from '../../src/modules/session/model/useAgentThreadState.js'

test('重置当前 Turn 投影时保留已排队 Input 的监视', () => {
  const chatState = { threadStates: {} }
  const { getThreadState, resetOngoingRunGroup } = useAgentThreadState({
    chatState
  })
  const state = getThreadState('thread-1')
  const controller = new AbortController()
  let runAborted = false
  state.runStreamAbortController = { abort: () => (runAborted = true) }
  state.inputQueueMonitor = { controller, timer: null, inputIds: new Set(['input-2']) }
  state.ongoingRunGroup.items['input-1'] = { type: 'message', content: [{ type: 'output_text', text: '第一轮回复' }] }

  resetOngoingRunGroup('thread-1', { preserveInputMonitors: true })

  assert.equal(runAborted, true)
  assert.equal(controller.signal.aborted, false)
  assert.deepEqual([...state.inputQueueMonitor.inputIds], ['input-2'])
  assert.deepEqual(state.ongoingRunGroup.items, {})
})

for (const action of ['reset', 'cleanup']) {
  test(`${action} 停止 Input 监视与重连计时器`, async () => {
    const chatState = { threadStates: {} }
    const { getThreadState, resetOngoingRunGroup, cleanupThreadState } = useAgentThreadState({
      chatState
    })
    const state = getThreadState('thread-1')
    const controller = new AbortController()
    let retried = false
    state.inputQueueMonitor = {
      inputIds: new Set(['input-1']),
      controller,
      timer: setTimeout(() => { retried = true }, 20)
    }

    if (action === 'reset') resetOngoingRunGroup('thread-1')
    else cleanupThreadState('thread-1')

    await new Promise((resolve) => setTimeout(resolve, 40))
    assert.equal(controller.signal.aborted, true)
    assert.equal(retried, false)
    assert.equal(state.inputQueueMonitor, null)
  })
}
