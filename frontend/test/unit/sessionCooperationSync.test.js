import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { setImmediate } from 'node:timers'
import { effectScope, nextTick, ref } from 'vue'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { createTestServer } from '../helpers/createTestServer.js'

let server, api, useRuntime, useSessionCooperation, ErrorHandler
before(async () => {
  globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
  server = await createTestServer({ server: { middlewareMode: true, hmr: false } })
  ;({ agentApi: api } = await server.ssrLoadModule('/src/apis/index.js'))
  ;({ ErrorHandler } = await server.ssrLoadModule('/src/shared/lib/errorHandler.js'))
  ;({ useSessionRuntimeStore: useRuntime } = await server.ssrLoadModule(
    '/src/modules/session/model/sessionRuntime.js'
  ))
  ;({ useSessionCooperation } = await server.ssrLoadModule(
    '/src/modules/session/model/useSessionCooperation.js'
  ))
})
after(async () => {
  await server?.close()
  delete globalThis.localStorage
})
const settle = async () => {
  for (let i = 0; i < 6; i++) {
    await nextTick()
    await new Promise((resolve) => setImmediate(resolve))
  }
}

/** 组合真实摘要观察者与共享 runtime，详情协议独立于摘要。 */
function setup(t, { status = 'completed' } = {}) {
  t.mock.method(ErrorHandler, 'handleError', () => {})
  const saved = { ...api }
  const pinia = createPinia()
  setActivePinia(pinia)
  const current = {
    turnId: 'old-turn', runId: 'old-run', status,
    output: '旧轮次结果', paused: false, pending: false, inputIds: ['external'], unavailable: false
  }
  let subscriptions = 0, detailReads = 0, itemReads = 0, wire
  const waitpoint = () => current.status === 'requires_action' ? {
    kind: 'answer', id: 'waitpoint', run_id: current.runId,
    questions: [{ question_id: 'q', question: '继续吗？' }]
  } : null
  const item = () => ({
    id: current.turnId, type: 'message', role: 'assistant', status: 'completed',
    turn_id: current.turnId, content: [{ type: 'output_text', text: current.output }],
    yuxi: { message_id: current.turnId, run_id: current.runId }
  })
  Object.assign(api, {
    getCooperationSummary: async () => ({ sessions: [{ session_id: 'root' }, {
      session_id: 'child', turn_id: current.turnId, current_run_id: current.runId,
      result_run_id: current.status === 'completed' ? current.runId : null,
      turn_status: current.status === 'requires_action' ? 'waiting' : current.status,
      waiting_for: waitpoint()?.kind || null,
      queue_paused: current.paused, has_pending_input: current.pending
    }] }),
    getPublicThread: async () => ({
      id: 'child', yuxi: { current_turn: { id: current.turnId, status: current.status } }
    }),
    getThreadTurn: async () => {
      detailReads++
      if (current.unavailable) throw new Error('persistent detail unavailable')
      return { id: current.turnId, status: current.status,
        yuxi: { current_run_id: current.runId, waitpoint: waitpoint(), output: [], runs: [] } }
    },
    getSessionItems: async () => {
      itemReads++
      return { data: [item()], has_more: false, last_id: current.turnId, yuxi: { runs: [] } }
    },
    getAgentState: async () => ({ agent_state: {}, interrupt: null }),
    getThreadQueue: async () => ({
      status: current.paused ? 'paused' : 'ready', queue_paused: current.paused,
      inputs: current.pending ? current.inputIds.map((input_id) => ({ input_id, status: 'pending' })) : []
    }),
    getThreadInput: async (_threadId, input_id) => ({ input_id, status: 'pending' }),
    streamThreadEvents: async (_id, _cursor, { signal }) => {
      subscriptions++
      return new Response(new ReadableStream({
        start(controller) {
          wire = controller
          signal.addEventListener('abort', () => controller.close(), { once: true })
        }
      }))
    }
  })
  const runtime = useRuntime()
  const detach = runtime.observeThread('child', {})
  const duplicate = runtime.observeThread('child', {})
  const enabled = ref(true)
  const scope = effectScope()
  const cooperation = scope.run(() => useSessionCooperation({
    threadId: ref('root'), enabled, onSnapshot: runtime.reconcileCooperationSessions
  }))
  t.after(() => {
    scope.stop()
    detach()
    duplicate()
    disposePinia(pinia)
    Object.assign(api, saved)
  })
  return { current, runtime, cooperation, enabled,
    counts: () => ({ subscriptions, detailReads, itemReads }),
    emit: (event) => wire.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`)) }
}

test('终态成员对账只读取一次历史，恢复完成后历史已经可见', async (t) => {
  const h = setup(t)
  await settle()
  assert.deepEqual(h.runtime.threadMessages.child.map((message) => message.content), ['旧轮次结果'])
  assert.equal(h.counts().itemReads, 1, '终态收尾是唯一历史刷新 Owner')
  await h.cooperation.refresh()
  await settle()
  assert.equal(h.counts().itemReads, 1)
})

test('运行恢复等待终态历史成功，但不等待运行中的 SSE 结束', async (t) => {
  const h = setup(t, { status: 'in_progress' })
  await settle()
  assert.equal(h.runtime.getThreadState('child').isStreaming, true)
  assert.equal(await h.runtime.resumeActiveRunForThread('child'), true)
  h.current.status = 'completed'
  h.current.output = '持久终态结果'
  const read = api.getSessionItems
  let release, finished = false
  api.getSessionItems = () => new Promise((resolve) => { release = async () => resolve(await read()) })
  const restoring = h.runtime.resumeActiveRunForThread('child').then((success) => {
    finished = true
    return success
  })
  await settle()
  assert.equal(finished, false, '终态历史未读到时不能宣告恢复完成')
  await release()
  assert.equal(await restoring, true)
  assert.equal(h.runtime.threadMessages.child[0].content, '持久终态结果')
  assert.equal(h.runtime.getThreadState('child').isStreaming, false)
})

test('终态历史失败时相同摘要仍重试，不把执行状态投影当作恢复成功', async (t) => {
  const h = setup(t)
  const read = api.getSessionItems
  let attempts = 0
  api.getSessionItems = async () => {
    if (++attempts === 1) throw new Error('terminal history unavailable')
    return read()
  }
  await settle()
  assert.equal(h.runtime.getThreadState('child').historyLoaded, false)
  await h.cooperation.refresh()
  await settle()
  assert.deepEqual(h.runtime.threadMessages.child.map((message) => message.content), ['旧轮次结果'])
  assert.equal(attempts, 2)
})

test('终态历史期间有新执行使恢复失效后，相同摘要仍能重试', async (t) => {
  const h = setup(t, { status: 'in_progress' })
  await settle()
  h.current.status = 'completed'
  const read = api.getSessionItems
  let release, first = true
  api.getSessionItems = async () => {
    if (!first) return read()
    first = false
    return new Promise((resolve) => { release = async () => resolve(await read()) })
  }
  await h.cooperation.refresh()
  await settle()
  void h.runtime.startRunStream('child', 'intervening-run', null, { turnId: 'intervening-turn' })
  await settle()
  await release()
  await settle()
  assert.equal(h.runtime.getThreadState('child').currentTurnId, 'intervening-turn')
  await h.cooperation.refresh()
  await settle()
  assert.equal(h.runtime.getThreadState('child').turnStatus, 'completed')
  assert.equal(h.runtime.getThreadState('child').isStreaming, false)
})

test('运行历史期间收到进展事件后，相同摘要重读持久历史', async (t) => {
  const h = setup(t)
  await settle()
  Object.assign(h.current, { turnId: 'live-turn', runId: 'live-run', status: 'in_progress' })
  const read = api.getSessionItems
  let release, first = true
  api.getSessionItems = async () => {
    if (!first) return read()
    first = false
    return new Promise((resolve) => { release = async () => resolve(await read()) })
  }
  await h.cooperation.refresh()
  await settle()
  h.emit({ type: 'agent.session.turn.in_progress', session_id: 'child', turn_id: 'live-turn',
    turn: { status: 'in_progress' }, yuxi: { run_id: 'live-run', current_run_id: 'live-run' } })
  await settle()
  await release()
  await settle()
  h.current.output = '事件之后的持久历史'
  await h.cooperation.refresh()
  await settle()
  assert.equal(h.runtime.threadMessages.child.at(-1).content, '事件之后的持久历史')
  assert.equal(h.counts().subscriptions, 1)
})

test('已完成成员收到外部新任务后自动读取新历史并共享一个运行订阅', async (t) => {
  const h = setup(t)
  await settle()
  Object.assign(h.current, { turnId: 'new-turn', runId: 'new-run', status: 'in_progress', output: '新任务内容' })
  await h.cooperation.refresh()
  await settle()
  const state = h.runtime.getThreadState('child')
  assert.equal(state.currentTurnId, 'new-turn')
  assert.equal(state.activeRunId, 'new-run')
  assert.equal(state.isStreaming, true)
  assert.deepEqual(h.runtime.threadMessages.child.map((message) => message.content), ['旧轮次结果', '新任务内容'])
  assert.equal(h.counts().subscriptions, 1, '两个视图仍只持有一个 SSE')
  const reads = h.counts().detailReads
  await h.cooperation.refresh()
  await settle()
  assert.equal(h.counts().detailReads, reads, '相同摘要不重复读取运行详情')
})

test('人工等待被外部取消并停止队列后，旧卡片消失且历史队列重新对账', async (t) => {
  const h = setup(t, { status: 'requires_action' })
  await h.runtime.resumeActiveRunForThread('child')
  await settle()
  assert.equal(h.runtime.getThreadState('child').pendingInterrupt?.waitpointId, 'waitpoint')
  Object.assign(h.current, { status: 'cancelled', output: '已取消的持久输出', paused: true, pending: true })
  await h.cooperation.refresh()
  await settle()
  const state = h.runtime.getThreadState('child')
  assert.equal(state.pendingInterrupt, null)
  assert.equal(state.turnStatus, 'cancelled')
  assert.equal(state.isStreaming, false)
  assert.equal(state.queueSnapshot.queue_paused, true)
  assert.equal(state.queueSnapshot.status, 'paused')
  assert.equal(state.queuedInputs[0].input_id, 'external')
  assert.equal(h.runtime.threadMessages.child[0].content, '已取消的持久输出')
})

test('相同摘要在持久详情读取失败后重试，恢复成功后才去重', async (t) => {
  const h = setup(t)
  await settle()
  Object.assign(h.current, { turnId: 'retry-turn', runId: 'retry-run', status: 'in_progress', unavailable: true })
  await h.cooperation.refresh()
  await settle()
  assert.notEqual(h.runtime.getThreadState('child').currentTurnId, 'retry-turn')
  h.current.unavailable = false
  await h.cooperation.refresh()
  await settle()
  assert.equal(h.runtime.getThreadState('child').currentTurnId, 'retry-turn')
  assert.equal(h.counts().subscriptions, 1)
})

test('根页面失活后的迟到摘要不能更新成员，重新激活后追上外部任务', async (t) => {
  const h = setup(t)
  await settle()
  let release
  api.getCooperationSummary = () => new Promise((resolve) => { release = resolve })
  const pending = h.cooperation.refresh()
  h.enabled.value = false
  await settle()
  Object.assign(h.current, { turnId: 'hidden-turn', runId: 'hidden-run', status: 'in_progress', output: '恢复后新内容' })
  const snapshot = { sessions: [{ session_id: 'root' }, { session_id: 'child', turn_id: 'hidden-turn', current_run_id: 'hidden-run', turn_status: 'running' }] }
  release(snapshot)
  await pending
  await settle()
  assert.equal(h.counts().subscriptions, 0)
  api.getCooperationSummary = async () => snapshot
  h.enabled.value = true
  await settle()
  assert.equal(h.runtime.getThreadState('child').currentTurnId, 'hidden-turn')
  assert.equal(h.runtime.threadMessages.child.at(-1).content, '恢复后新内容')
})

test('执行摘要不变时仍发现第二条外部排队输入，普通单会话不增加详情读取', async (t) => {
  const h = setup(t)
  h.current.pending = true
  await settle()
  assert.deepEqual(h.runtime.getThreadState('child').queuedInputs.map((input) => input.input_id), ['external'])
  const reads = h.counts().detailReads
  h.current.inputIds.push('another-input')
  await h.cooperation.refresh()
  await settle()
  assert.deepEqual(h.runtime.getThreadState('child').queuedInputs.map((input) => input.input_id), ['external', 'another-input'])
  assert.equal(h.counts().detailReads, reads)
  api.getCooperationSummary = async () => ({ sessions: [{ session_id: 'child' }] })
  h.current.inputIds.push('single-session-input')
  await h.cooperation.refresh()
  await settle()
  assert.equal(h.runtime.getThreadState('child').queuedInputs.length, 2)
})

test('新 Turn 取代仍持有旧 SSE 的轮次时，关闭旧连接并订阅新轮次', async (t) => {
  const h = setup(t, { status: 'in_progress' })
  await settle()
  assert.equal(h.counts().subscriptions, 1)
  Object.assign(h.current, { turnId: 'next-turn', runId: 'next-run', output: '后续轮次' })
  await h.cooperation.refresh()
  await settle()
  const state = h.runtime.getThreadState('child')
  assert.equal(state.currentTurnId, 'next-turn')
  assert.equal(state.activeRunId, 'next-run')
  assert.equal(state.runStreamAbortController.signal.aborted, false)
  assert.equal(h.counts().subscriptions, 2, '新 Turn 必须拥有新订阅，而不是复用只处理旧 Turn 的连接')
})

test('摘要变化后的对账不共用变化之前的在途恢复快照', async (t) => {
  const h = setup(t)
  await settle()
  const getCurrent = api.getPublicThread
  let releaseOld, first = true
  api.getPublicThread = async () => {
    if (!first) return getCurrent()
    first = false
    return new Promise((resolve) => { releaseOld = resolve })
  }
  const old = h.runtime.resumeActiveRunForThread('child')
  await settle()
  Object.assign(h.current, { turnId: 'latest-turn', runId: 'latest-run', status: 'in_progress' })
  await h.cooperation.refresh()
  await settle()
  releaseOld({ yuxi: { current_turn: null } })
  await old
  await settle()
  await h.cooperation.refresh()
  await settle()
  assert.equal(h.runtime.getThreadState('child').currentTurnId, 'latest-turn')
  assert.equal(h.runtime.getThreadState('child').activeRunId, 'latest-run')
  assert.equal(h.counts().subscriptions, 1)
})
