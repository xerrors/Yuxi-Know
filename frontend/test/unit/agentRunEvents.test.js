import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, before, test } from 'node:test'
import { setImmediate } from 'node:timers'
import { createServer } from 'vite'
import { createItemState } from '../../src/modules/session/model/agentItems.js'

let server, api, useAgentRunStream, processRunSseResponse, useAgentInputQueue
before(async () => {
  globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
  server = await createServer({ server: { middlewareMode: true, hmr: false } })
  ;({ agentApi: api } = await server.ssrLoadModule('/src/apis/index.js'))
  ;({ useAgentRunStream, processRunSseResponse } = await server.ssrLoadModule(
    '/src/modules/session/model/useAgentRunStream.js'
  ))
  ;({ useAgentInputQueue } = await server.ssrLoadModule(
    '/src/modules/session/model/useAgentInputQueue.js'
  ))
})
after(async () => {
  await server?.close()
  delete globalThis.localStorage
})
const tick = () => new Promise((resolve) => setImmediate(resolve))
const event = (type, runId = 'run', turnId = 'turn') => ({
  type,
  event_id: `${type}:${runId}`,
  session_id: 'thread',
  turn_id: turnId,
  yuxi: { run_id: runId },
  ...((type.startsWith('agent.session.turn.') && ['created', 'in_progress', 'completed', 'failed', 'cancelled'].includes(type.split('.').at(-1))) || type === 'yuxi.session.turn.waiting'
    ? { turn: { status: type === 'yuxi.session.turn.waiting' ? 'requires_action' : type.endsWith('.created') ? 'queued' : type.split('.').at(-1) } }
    : {})
})
const response = (events) =>
  new Response(
    new ReadableStream({
      start(controller) {
        events.forEach((value, index) =>
          controller.enqueue(
            new TextEncoder().encode(
              `id: 2.0.1.${index + 1}-0.3\nevent: ${value.type}\ndata: ${JSON.stringify(value)}\n\n`
            )
          )
        )
        controller.close()
      }
    })
  )
function harness(
  t,
  events,
  { status = 'running', currentRun = 'run', snapshot = async () => {} } = {}
) {
  const state = {
    currentTurnId: 'turn',
    activeRunId: currentRun,
    ongoingRunGroup: createItemState()
  }
  const delivered = [],
    terminal = []
  t.mock.method(api, 'getThreadTurn', async () => ({
    id: 'turn',
    object: 'agent.session.turn',
    status: status === 'running' ? 'in_progress' : status,
    yuxi: { current_run_id: currentRun, status }
  }))
  t.mock.method(api, 'streamThreadEvents', async () => response(events))
  const stream = useAgentRunStream({
    getThreadState: () => state,
    currentAgentId: 'agent',
    handlePublicEvent: (value) => delivered.push(value),
    fetchThreadMessages: snapshot,
    fetchAgentState() {},
    resetOngoingRunGroup() {},
    onTerminalDetected: (value) => terminal.push(value)
  })
  t.after(() => stream.stopRunStreamSubscription('thread'))
  return { state, stream, delivered, terminal }
}

test('SSE 每条 data 直接消费；等待异步快照时缓冲后续事件', async () => {
  const order = []
  const events = [event('yuxi.session.resync'), event('agent.session.turn.output_text.delta')]
  await processRunSseResponse(response(events), async (_type, data) => {
    order.push(data.type)
    if (data.type === 'yuxi.session.resync') {
      await tick()
      order.push('snapshot-applied')
    }
  })
  assert.deepEqual(order, [
    'yuxi.session.resync',
    'snapshot-applied',
    'agent.session.turn.output_text.delta'
  ])
})

test('resync 回读 items 和 Turn 后继续消费终态，cursor 保持订阅位置', async (t) => {
  const order = []
  const h = harness(t, [event('yuxi.session.resync'), event('agent.session.turn.completed')], {
    snapshot: async () => {
      order.push('snapshot')
      await tick()
    }
  })
  await h.stream.startRunStream('thread', 'run', null, { turnId: 'turn' })
  await tick()
  assert.equal(order[0], 'snapshot')
  assert.equal(h.state.turnStatus, 'completed')
  assert.match(h.state.threadCursor, /^2\./)
  assert.equal(h.terminal.length, 1)
})

test('waiting 立即禁发并保留自身 Run，父终态回调不包含子 Thread', async (t) => {
  const h = harness(t, [event('yuxi.session.turn.waiting')])
  await h.stream.startRunStream('thread', 'run', null, { turnId: 'turn' })
  await tick()
  assert.equal(h.state.turnStatus, 'requires_action')
  assert.equal(h.state.activeRunSteerable, false)
  assert.equal(h.state.activeRunId, 'run')
  assert.equal(h.terminal.length, 0)
})

test('旧 Run 的 waiting 和其他 Turn 的终态不能结束恢复后的 Run', async (t) => {
  const h = harness(
    t,
    [
      event('yuxi.session.turn.waiting', 'old'),
      event('agent.session.turn.completed', 'foreign', 'foreign-turn'),
      event('agent.session.turn.completed', 'new')
    ],
    { currentRun: 'new' }
  )
  await h.stream.startRunStream('thread', 'new', null, { turnId: 'turn' })
  await tick()
  assert.equal(h.delivered.length, 1)
  assert.equal(h.delivered[0].yuxi.run_id, 'new')
  assert.equal(h.state.turnStatus, 'completed')
  assert.deepEqual(h.terminal[0].touchedThreadIds, ['thread'])
})

test('Run settled 不结束 Turn；只有 Turn 终态收尾', async (t) => {
  const h = harness(t, [event('yuxi.session.run.settled'), event('agent.session.turn.completed')])
  await h.stream.startRunStream('thread', 'run', null, { turnId: 'turn' })
  await tick()
  assert.equal(h.delivered.length, 2)
  assert.equal(h.terminal.length, 1)
})

test('FIFO 领取后用真实 item 替换乐观输入并订阅所属 Turn', async (t) => {
  const state = {
    queuedInputs: [],
    inputQueueMonitor: null,
    ongoingRunGroup: {
      ...createItemState(),
      optimisticMessages: { input: { id: 'local' } }
    }
  }
  const item = {
    id: 'input_1',
    type: 'message',
    role: 'user',
    status: 'completed',
    content: [],
    yuxi: { input_id: 'input' }
  }
  t.mock.method(api, 'getThreadQueue', async () => ({
    inputs: [{ input_id: 'input', status: 'pending' }]
  }))
  t.mock.method(api, 'getThreadInput', async () => ({
    status: 'consumed',
    run_id: 'run',
    turn_id: 'turn',
    items: [item]
  }))
  const started = []
  const queue = useAgentInputQueue({
    getThreadState: () => state,
    resetOngoingRunGroup() {},
    startRunStream: (...args) => started.push(args)
  })
  t.after(() => queue.stopAllInputMonitors('thread'))
  await queue.syncQueuedInputs('thread')
  await tick()
  assert.deepEqual(state.ongoingRunGroup.items.input_1, item)
  assert.deepEqual(state.ongoingRunGroup.optimisticMessages, {})
  assert.deepEqual(started, [['thread', 'run', null, { turnId: 'turn', inputId: 'input' }]])
})

test('旧 Turn 等待历史回读时启动新 FIFO 流，旧收尾不能中止新订阅或审批', async (t) => {
  let releaseHistory
  const history = new Promise((resolve) => {
    releaseHistory = resolve
  })
  let secondController,
    resetCount = 0,
    terminalCount = 0
  const state = { currentTurnId: 'turn', activeRunId: 'run', ongoingRunGroup: createItemState() }
  t.mock.method(api, 'getThreadTurn', async (_thread, turnId) => ({
    id: turnId,
    yuxi: { current_run_id: 'next', status: 'running' }
  }))
  t.mock.method(api, 'streamThreadEvents', async (_thread, _cursor, { signal }) => {
    if (!secondController) {
      secondController = signal
      return response([event('agent.session.turn.completed')])
    }
    secondController = signal
    return new Response(
      new ReadableStream({
        start(controller) {
          signal.addEventListener('abort', () => controller.close(), { once: true })
        }
      })
    )
  })
  const stream = useAgentRunStream({
    getThreadState: () => state,
    currentAgentId: 'agent',
    handlePublicEvent() {},
    fetchThreadMessages: () => history,
    fetchAgentState() {},
    resetOngoingRunGroup: () => {
      resetCount++
      state.runStreamAbortController?.abort()
    },
    onTerminalDetected: () => terminalCount++
  })
  await stream.startRunStream('thread', 'run', null, { turnId: 'turn' })
  const following = stream.startRunStream('thread', 'next', null, { turnId: 'next-turn' })
  await tick()
  releaseHistory()
  await tick()
  assert.equal(state.currentTurnId, 'next-turn')
  assert.equal(secondController.aborted, false)
  assert.equal(resetCount, 0)
  assert.equal(terminalCount, 0)
  stream.stopRunStreamSubscription('thread')
  await following
})

test('协作等待保留 SSE，自动恢复的 Run 重新允许 steer 并接收最终输出', async (t) => {
  const h = harness(t, [])
  let controller,
    signal,
    currentRun = 'run'
  t.mock.method(api, 'getThreadTurn', async () => ({
    id: 'turn',
    object: 'agent.session.turn',
    status: 'in_progress',
    yuxi: { current_run_id: currentRun, status: 'running' }
  }))
  t.mock.method(api, 'streamThreadEvents', async (_id, _cursor, options) => {
    signal = options.signal
    return new Response(
      new ReadableStream({
        start(value) {
          controller = value
        }
      })
    )
  })
  const emit = (value) =>
    controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(value)}\n\n`))
  const subscribed = h.stream.startRunStream('thread', 'run', null, { turnId: 'turn' })
  await tick()
  emit({ ...event('yuxi.session.turn.waiting'), turn: { status: 'in_progress' }, waitpoint: { kind: 'cooperation' } })
  await tick()
  assert.equal(h.state.turnStatus, 'in_progress')
  assert.equal(h.state.activeRunSteerable, false)
  assert.equal(signal.aborted, false)
  h.state.queuedInputs ||= []
  h.state.ongoingRunGroup ||= { ...createItemState(), optimisticMessages: {} }
  h.state.ongoingRunGroup.optimisticMessages ||= {}
  const source = readFileSync(
    new URL('../../src/modules/session/ui/SessionWorkspace.vue', import.meta.url),
    'utf8'
  )
  const sendSource = source.slice(
    source.indexOf('const handleSendMessage ='),
    source.indexOf('const handleDirectSteer =')
  )
  const dependencies = {
    userInput: { value: '队列里的新工作' },
    currentAgent: { value: {} },
    sendCooldownActive: { value: false },
    props: {},
    isLoadingMessages: { value: false },
    isWaitingForUserAction: { value: false },
    startSendCooldown() {},
    currentChatId: { value: 'thread' },
    currentModelSpec: { value: null },
    currentToolApprovalMode: { value: 'always_trust' },
    nextTick: tick,
    scrollController: { scrollToBottom() {} },
    getThreadState: () => h.state,
    approvalState: {},
    currentPendingThreadAttachments: { value: [] },
    threadMessages: { value: {} },
    createClientRequestId: () => 'queued-input',
    draftFilesByThread: { value: {} },
    pendingSends: { value: {} },
    fetchThreadAttachments: async () => {},
    buildOptimisticHumanMessage: ({ inputId, text }) => ({
      id: inputId,
      type: 'human',
      content: text
    }),
    resetOngoingRunGroup: () => h.state.runStreamAbortController?.abort(),
    submitSessionInput: async () => ({ input_id: 'queued-input', turn_id: null, run_id: null }),
    agentApi: {
      getThreadInput: async () => ({ items: [] })
    },
    mergeItemSnapshot() {},
    startInputMonitor() {},
    resumeQueuedInputs: async () => {},
    isRunInterruptedConflict: () => false,
    handleChatError: (error) => {
      throw error
    }
  }
  const send = new Function(
    ...Object.keys(dependencies),
    `${sendSource}; return handleSendMessage`
  )(...Object.values(dependencies))
  await send()
  assert.equal(signal.aborted, false, '协作等待追加工作不能关闭当前 Turn 的 SSE')
  assert.equal(h.state.queuedInputs[0].input_id, 'queued-input')
  currentRun = 'resumed'
  emit(event('agent.session.turn.in_progress', 'resumed'))
  await tick()
  assert.equal(h.state.activeRunId, 'resumed')
  assert.equal(h.state.turnStatus, 'in_progress')
  assert.equal(h.state.isStreaming, true)
  assert.equal(h.state.activeRunSteerable, true)
  assert.equal(h.state.cooperationWaiting, false)
  emit({ ...event('agent.session.turn.output_text.delta', 'resumed'), delta: 'result' })
  emit(event('agent.session.turn.completed', 'resumed'))
  controller.close()
  await subscribed
  await tick()
  assert.equal(h.state.turnStatus, 'completed')
  assert.equal(h.delivered.find((value) => value.delta)?.delta, 'result')
  assert.equal(h.terminal.length, 1)
})
