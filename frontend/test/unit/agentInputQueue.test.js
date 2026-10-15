import assert from 'node:assert/strict'
import path from 'node:path'
import { after, before, test } from 'node:test'
import { fileURLToPath } from 'node:url'

import { createServer } from 'vite'

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
let server
let agentApi
let useAgentInputQueue
let MessageProcessor
let getMessageGroupDisplayItems
let groupRunContinuations

before(async () => {
  const storage = new Map()
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key)
  }
  server = await createServer({ root: webRoot, server: { middlewareMode: true } })
  ;({ agentApi } = await server.ssrLoadModule('/src/apis/index.js'))
  ;({ useAgentInputQueue } = await server.ssrLoadModule(
    '/src/modules/session/model/useAgentInputQueue.js'
  ))
  ;({ default: MessageProcessor } = await server.ssrLoadModule('/src/modules/session/model/messageProcessor.js'))
  ;({ getMessageGroupDisplayItems } = await server.ssrLoadModule('/src/modules/session/model/messageGrouping.js'))
  ;({ groupRunContinuations } = await server.ssrLoadModule(
    '/src/modules/session/model/runProcessGrouping.js'
  ))
})

after(async () => {
  await server?.close()
  delete globalThis.localStorage
})

test('转引导重试复用幂等键，成功和冲突都回读队列且不写正式历史', async () => {
  const state = {
    queuedInputs: [{ input_id: 'F1', kind: 'follow_up', status: 'pending' }],
    inputQueueMonitor: null, ongoingRunGroup: { items: {}, optimisticMessages: {} }
  }
  const original = { ...agentApi }
  const { ErrorHandler } = await server.ssrLoadModule('/src/shared/lib/errorHandler.js')
  const originalHandleError = ErrorHandler.handleError
  ErrorHandler.handleError = () => {}
  const keys = []
  let reads = 0
  agentApi.getThreadInput = async () => ({ status: 'pending' })
  agentApi.getThreadQueue = async () => {
    reads++
    return { inputs: reads === 1 ? [{ input_id: 'F1', kind: 'steer', status: 'pending' }] : [] }
  }
  agentApi.promoteThreadInput = async (_thread, _input, key) => {
    keys.push(key)
    if (keys.length === 1) throw new Error('response lost')
    if (keys.length === 3) throw Object.assign(new Error('consumed'), { status: 409 })
  }
  const queue = useAgentInputQueue({ getThreadState: () => state })
  try {
    assert.equal(await queue.promoteInput('t', 'F1'), false)
    assert.equal(await queue.promoteInput('t', 'F1'), true)
    assert.equal(keys[0], keys[1])
    assert.equal(state.queuedInputs[0].kind, 'steer')
    assert.equal(await queue.promoteInput('t', 'F1'), false)
    assert.notEqual(keys[1], keys[2])
    assert.equal(reads, 2)
    assert.deepEqual(state.queuedInputs, [])
    assert.deepEqual(state.ongoingRunGroup.items, {})
  } finally {
    queue.stopAllInputMonitors('t')
    Object.assign(agentApi, original)
    ErrorHandler.handleError = originalHandleError
  }
})

test('较早队列快照不能覆盖新快照，取消一条不移除其他引导', async () => {
  const state = { queuedInputs: [], inputQueueMonitor: null, ongoingRunGroup: { items: {}, optimisticMessages: {} } }
  const original = { ...agentApi }
  let resolveOld
  agentApi.getThreadQueue = () => new Promise((resolve) => { resolveOld = resolve })
  agentApi.getThreadInput = async () => ({ status: 'pending' })
  agentApi.cancelThreadInput = async () => ({ status: 'accepted' })
  const queue = useAgentInputQueue({ getThreadState: () => state })
  try {
    const oldRead = queue.syncQueuedInputs('t')
    const rows = ['S1', 'S2'].map((input_id) => ({ input_id, kind: 'steer', status: 'pending' }))
    agentApi.getThreadQueue = async () => ({ inputs: rows })
    await queue.syncQueuedInputs('t')
    resolveOld({ inputs: [{ input_id: 'F1', kind: 'follow_up', status: 'pending' }] })
    await oldRead
    assert.deepEqual(state.queuedInputs.map((item) => item.input_id), ['S1', 'S2'])
    agentApi.getThreadQueue = async () => ({ inputs: [rows[1]] })
    assert.equal(await queue.cancelInput('t', 'S1'), true)
    assert.deepEqual(state.queuedInputs.map((item) => item.input_id), ['S2'])
    assert.deepEqual(state.ongoingRunGroup.items, {})
  } finally {
    queue.stopAllInputMonitors('t')
    Object.assign(agentApi, original)
  }
})

test('审批前后的工具和思考跨关联 Run 连续展示，正文仍独立', () => {
  const runs = [
    { id: 'first', turn_id: 'turn-1', status: 'interrupted', timing: { created_at: '2026-09-16T00:00:00Z' } },
    {
      id: 'resume',
      turn_id: 'turn-1',
      run_type: 'resume',
      status: 'completed',
      timing: { created_at: '2026-09-16T00:01:00Z' }
    }
  ]
  const history = [
    { id: 'human', run_id: 'first', type: 'human', content: '完成任务' },
    { id: 'm1', run_id: 'first', type: 'ai', tool_calls: [{ id: 't1', name: 'ls', args: {} }] },
    {
      id: 'm2',
      run_id: 'first',
      type: 'ai',
      reasoning_content: 'thinking1',
      tool_calls: [
        { id: 't2', name: 'read_file', args: {} },
        { id: 't3', name: 'ask_user_question', args: {}, status: 'success' }
      ]
    },
    {
      id: 'answer',
      run_id: 'resume',
      type: 'human',
      content: '{"type":"approval","decisions":[{"call_id":"t3","decision":"approve"}]}',
      message_type: 'resume'
    },
    {
      id: 'm3',
      run_id: 'resume',
      type: 'ai',
      reasoning_content: 'thinking2',
      tool_calls: [{ id: 't4', name: 'ls', args: {} }]
    },
    { id: 'm4', run_id: 'resume', type: 'ai', content: '最终回答' }
  ]
  const runGroups = MessageProcessor.convertServerHistoryToMessages(history, runs)
  const groups = groupRunContinuations(runGroups)
  assert.equal(groups.length, 1)
  const items = getMessageGroupDisplayItems(groups[0])
  assert.deepEqual(
    items.map((item) => item.type),
    ['message', 'tool-group', 'message']
  )
  assert.deepEqual(
    items[1].entries.map((entry) => (entry.type === 'tool' ? entry.toolCall.id : entry.content)),
    ['t1', 'thinking1', 't2', 't3', 'thinking2', 't4']
  )
  assert.equal(items[2].message.content, '最终回答')
  assert.equal(runGroups.length, 2)
  const streaming = groupRunContinuations([
    runGroups[0],
    { ...runGroups[1], status: 'streaming', messages: runGroups[1].messages.slice(0, 1) }
  ])
  assert.equal(streaming[0].status, 'streaming')
  assert.equal(getMessageGroupDisplayItems(streaming[0])[1].key, items[1].key)
})

test('协作恢复的实时消息没有 Run 快照时，仍与等待工具连续展示', () => {
  const waiting = {
    run: { id: 'before', turn_id: 'turn-1', status: 'interrupted' },
    messages: [{
      id: 'wait', type: 'ai', run_id: 'before', turn_id: 'turn-1',
      tool_calls: [{ id: 'wait-call', name: 'wait_inputs', status: 'waiting', args: {} }]
    }]
  }
  const live = {
    status: 'streaming',
    messages: [{
      id: 'thinking', type: 'ai', run_id: 'after', turn_id: 'turn-1',
      reasoning_content: '继续核验'
    }]
  }
  const groups = groupRunContinuations([waiting, live])
  assert.equal(groups.length, 1)
  const items = getMessageGroupDisplayItems(groups[0])
  assert.equal(items.length, 1)
  assert.deepEqual(items[0].entries.map((entry) => entry.type), ['tool', 'reasoning'])
  assert.equal(items[0].toolCalls[0].status, 'waiting')
  assert.deepEqual(groups[0].messages.map((message) => message.run_id), ['before', 'after'])
  assert.equal(groups[0].run.id, 'after')
  assert.equal(groups[0].status, 'streaming')
  for (const messages of [
    [{ ...live.messages[0], turn_id: 'turn-2' }],
    [{ ...live.messages[0], turn_id: undefined }],
    [{ id: 'user', type: 'human', content: '继续' }, ...live.messages]
  ]) {
    assert.equal(groupRunContinuations([waiting, { ...live, messages }]).length, 2)
  }
})

test('thinking 与相邻工具按顺序合并，正文和错误仍独立显示', () => {
  const messages = [
    { id: 'a1', type: 'ai', reasoning_content: '先检查', tool_calls: [{ id: 't1', name: 'ls', args: {} }] },
    { id: 'a2', type: 'ai', reasoning_content: '再确认', tool_calls: [{ id: 't2', name: 'read_file', args: {} }] },
    { id: 'a3', type: 'ai', reasoning_content: '得到结论', content: '最终回答' }
  ]
  const items = getMessageGroupDisplayItems({ messages })
  assert.deepEqual(items.map((item) => item.type), ['tool-group', 'message'])
  assert.deepEqual(items[0].entries.map((entry) => entry.type), ['reasoning', 'tool', 'reasoning', 'tool', 'reasoning'])
  assert.deepEqual(items[0].entries.filter((entry) => entry.type === 'reasoning').map((entry) => entry.content), ['先检查', '再确认', '得到结论'])
  assert.equal(items[0].toolCalls.length, 2)
  assert.equal(items[1].message.content, '最终回答')
  assert.equal(items[1].message.reasoning_content, '')
  assert.equal(messages[2].reasoning_content, '得到结论')

  const thinkingOnly = getMessageGroupDisplayItems({ messages: [{ id: 'a', type: 'ai', reasoning_content: '思考中' }] })
  assert.equal(thinkingOnly.length, 1)
  assert.equal(thinkingOnly[0].type, 'tool-group')
  assert.equal(thinkingOnly[0].entries[0].content, '思考中')
  assert.deepEqual(thinkingOnly[0].toolCalls, [])
  assert.deepEqual(getMessageGroupDisplayItems({ messages: [{ type: 'ai', content: '' }] }), [])

  const failed = getMessageGroupDisplayItems({ messages: [{ type: 'ai', reasoning_content: '检查中断', error_type: 'interrupted' }] })
  assert.deepEqual(failed.map((item) => item.type), ['tool-group', 'message'])
  assert.equal(failed[1].message.error_type, 'interrupted')
})

test('同一消息的 thinking、正文和工具分段使用不同的稳定 key', () => {
  const message = { id: 'mixed', type: 'ai', reasoning_content: '计划', content: '先查文件', tool_calls: [{ id: 't1', name: 'ls', args: {} }] }
  const items = getMessageGroupDisplayItems({ messages: [message] })
  assert.deepEqual(items.map((item) => item.type), ['tool-group', 'message', 'tool-group'])
  assert.equal(new Set(items.map((item) => item.key)).size, 3)
  assert.equal(items[0].entries[0].content, '计划')
  assert.equal(items[2].entries[0].toolCall.id, 't1')
  const updated = getMessageGroupDisplayItems({ messages: [{ ...message, content: '先查文件，再整理' }] })
  assert.deepEqual(updated.map((item) => item.key), items.map((item) => item.key))
})

test('完整队列快照保留独立 steer 节点并遵循服务器优先顺序', async () => {
  const state = {
    queuedInputs: [
      { input_id: 'F1', kind: 'follow_up', status: 'pending', content: '普通消息' },
      { input_id: 'S1', kind: 'steer', status: 'pending', content: '旧内容' },
      { input_id: 'S1', kind: 'steer', status: 'pending', content: '重复投影' },
      { input_id: 'local', status: 'sending' }
    ],
    inputQueueMonitor: null,
    ongoingRunGroup: { items: {}, optimisticMessages: {} }
  }
  const originalQueue = agentApi.getThreadQueue
  const originalInput = agentApi.getThreadInput
  const queue = useAgentInputQueue({ getThreadState: () => state })
  agentApi.getThreadInput = async () => ({ status: 'pending' })
  agentApi.getThreadQueue = async () => ({ inputs: [
    { input_id: 'S1', kind: 'steer', status: 'pending', content: 'S1' },
    { input_id: 'S2', kind: 'steer', status: 'pending', content: 'S2' },
    { input_id: 'F1', kind: 'follow_up', status: 'pending', content: '普通消息' }
  ] })
  try {
    await queue.syncQueuedInputs('thread-1')
    assert.deepEqual(state.queuedInputs.map((input) => input.input_id), ['S1', 'S2', 'F1', 'local'])
    assert.equal(state.queuedInputs[0].content, 'S1')
    assert.deepEqual(state.ongoingRunGroup.items, {})
    assert.ok(state.inputQueueMonitor)
    assert.deepEqual([...state.inputQueueMonitor.inputIds], ['S1', 'S2', 'F1'])
    agentApi.getThreadQueue = async () => ({ inputs: [
      { input_id: 'F1', kind: 'follow_up', status: 'pending', content: '普通消息' }
    ] })
    await queue.syncQueuedInputs('thread-1')
    assert.deepEqual(state.queuedInputs.map((input) => input.input_id), ['F1', 'local'])
  } finally {
    queue.stopAllInputMonitors('thread-1')
    agentApi.getThreadQueue = originalQueue
    agentApi.getThreadInput = originalInput
  }
})

test('尚未接收的本地输入不能被取消或订阅', async () => {
  const state = {
    queuedInputs: [{ input_id: 'local-key', status: 'sending' }],
    inputQueueMonitor: null,
    ongoingRunGroup: { items: {}, optimisticMessages: {} }
  }
  const originalQueue = agentApi.getThreadQueue
  const originalInput = agentApi.getThreadInput
  const originalCancel = agentApi.cancelThreadInput
  const calls = []
  agentApi.getThreadQueue = async () => ({ inputs: [] })
  agentApi.getThreadInput = async () => { calls.push('input'); throw new Error('not persisted') }
  agentApi.cancelThreadInput = async () => { calls.push('cancel'); throw new Error('not persisted') }
  try {
    const queue = useAgentInputQueue({ getThreadState: () => state })
    await queue.resumeQueuedInputs('thread-1')
    assert.equal(await queue.cancelInput('thread-1', 'local-key'), false)
    assert.deepEqual(state.queuedInputs, [{ input_id: 'local-key', status: 'sending' }])
    assert.deepEqual(calls, [])
  } finally {
    agentApi.getThreadQueue = originalQueue
    agentApi.getThreadInput = originalInput
    agentApi.cancelThreadInput = originalCancel
  }
})


test('交付物展示不把最后可见工具后的正文收入过程区', () => {
  for (const artifactTool of [
    { name: 'present_artifacts', args: { filepaths: ['/dog.png'] }, status: 'success' },
    { function: { name: 'present_artifacts', arguments: '{"filepaths":["/dog.png"]}' }, status: 'success' }
  ]) {
    const messages = [
      { id: 'human', type: 'human', content: '生成小狗图片' },
      { id: 'prepare', type: 'ai', content: '检查图片文件', tool_calls: [{ name: 'ls', args: {} }] },
      { id: 'answer', type: 'ai', content: '图片已生成，这是图片说明。', tool_calls: [artifactTool] },
      { id: 'confirm', type: 'ai', content: '图片已展示，可下载。' }
    ]
    const original = structuredClone(messages)
    const items = getMessageGroupDisplayItems({ messages }, { collapseIntermediate: true })
    assert.deepEqual(items.map(item => item.type), ['message', 'process-group', 'message', 'message'])
    assert.deepEqual(items[1].items.map(item => item.key), ['prepare', 'tool-group-prepare-tools'])
    assert.equal(items[1].toolCallCount, 1)
    assert.deepEqual(items.slice(2).map(item => item.message.id), ['answer', 'confirm'])
    assert.deepEqual(MessageProcessor.extractArtifactsFromMessageGroup({ messages }), ['/dog.png'])
    assert.deepEqual(messages, original)
  }
})

test('只有交付物展示时正文全部保留，混合调用或后续执行工具仍参与过程折叠', () => {
  const present = { name: 'present_artifacts', args: { filepaths: ['/dog.png'] }, status: 'success' }
  const execute = { name: 'bash', args: { command: 'check' } }
  const answer = { id: 'answer', type: 'ai', content: '图片说明', tool_calls: [present] }
  const confirm = { id: 'confirm', type: 'ai', content: '展示完成' }
  const human = { id: 'human', type: 'human', content: '生成图片' }
  for (const messages of [[human, answer], [human, answer, confirm]]) {
    const items = getMessageGroupDisplayItems({ messages }, { collapseIntermediate: true })
    assert.deepEqual(items.map(item => item.message.id), messages.map(message => message.id))
  }
  for (const messages of [
    [{ ...answer, tool_calls: [present, execute] }, confirm],
    [answer, { id: 'check', type: 'ai', content: '继续检查', tool_calls: [execute] }, confirm]
  ]) {
    const items = getMessageGroupDisplayItems({ messages }, { collapseIntermediate: true })
    assert.deepEqual(items.map(item => item.type), ['process-group', 'message'])
    assert.equal(items[0].toolCallCount, 1)
    assert.equal(items[0].items.at(-1).toolCalls[0].name, 'bash')
    assert.equal(items[1].message.id, 'confirm')
    const live = getMessageGroupDisplayItems({ messages })
    assert.equal(live.some(item => item.type === 'process-group'), false)
  }
})
