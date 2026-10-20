import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { setImmediate } from 'node:timers'
import { createTestServer } from '../helpers/createTestServer.js'
import { createSSRApp, effectScope, h, nextTick, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia } from 'pinia'
let server, agentApi, useSessionCooperation, CooperationTree
before(async () => {
  globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
  server = await createTestServer({ server: { middlewareMode: true, hmr: false } })
  ;({ agentApi } = await server.ssrLoadModule('/src/apis/index.js'))
  ;({ useSessionCooperation } = await server.ssrLoadModule(
    '/src/modules/session/model/useSessionCooperation.js'
  ))
  ;({ default: CooperationTree } = await server.ssrLoadModule(
    '/src/modules/session/ui/CooperationTree.vue'
  ))
  globalThis.document = { documentElement: { classList: { add() {}, remove() {} } } }
  // 协作列表的 SSR 断言不涉及颜色，仅提供浏览器样式读取接口。
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => '' })
})
after(async () => {
  await server?.close()
  delete globalThis.localStorage
  delete globalThis.document
  delete globalThis.getComputedStyle
})
const settle = async () => {
  await nextTick()
  await new Promise((resolve) => setImmediate(resolve))
}
function setup(t, get) {
  const original = agentApi.getCooperationSummary
  agentApi.getCooperationSummary = get
  const scope = effectScope(),
    threadId = ref('root'),
    enabled = ref(true)
  const observed = scope.run(() => useSessionCooperation({ threadId, enabled }))
  t.after(() => {
    scope.stop()
    agentApi.getCooperationSummary = original
  })
  return { scope, threadId, enabled, observed }
}
const response = (sessions) => ({ sessions })
test('切换会话后旧查询不能覆盖新树，已完成成员来自持久状态', async (t) => {
  let resolveOld
  const h = setup(t, (id) =>
    id === 'root'
      ? new Promise((resolve) => {
          resolveOld = resolve
        })
      : Promise.resolve(response([{ session_id: 'new', turn_status: 'completed' }]))
  )
  h.threadId.value = 'new'
  await settle()
  resolveOld(response([{ session_id: 'old', turn_status: 'failed' }]))
  await settle()
  assert.equal(h.observed.sessions.value[0].session_id, 'new')
  assert.equal(h.observed.sessions.value[0].turn_status, 'completed')
})
test('故障保留最近已知树并显示重试错误，重试后读取新状态', async (t) => {
  let offline = false
  const h = setup(t, async () => {
    if (offline) throw new Error('offline')
    return response([{ session_id: 'child', waiting_for: 'approval' }])
  })
  await settle()
  offline = true
  await h.observed.refresh()
  assert.equal(h.observed.error.value, 'offline')
  assert.equal(h.observed.sessions.value[0].waiting_for, 'approval')
  offline = false
  await h.observed.refresh()
  assert.equal(h.observed.error.value, '')
})

test('会话失活保留协作列表，重新激活读取新状态且拒绝迟到结果', async (t) => {
  let resolveLate,
    requests = 0
  const h = setup(t, async () => {
    requests += 1
    if (requests === 2)
      return new Promise((resolve) => {
        resolveLate = resolve
      })
    return response([{ session_id: 'child', turn_status: requests > 2 ? 'completed' : 'running' }])
  })
  await settle()
  const pending = h.observed.refresh()
  h.enabled.value = false
  await settle()
  assert.equal(h.observed.sessions.value[0].turn_status, 'running')
  resolveLate(response([{ session_id: 'late' }]))
  await pending
  assert.equal(h.observed.sessions.value[0].session_id, 'child')
  h.enabled.value = true
  await settle()
  assert.equal(h.observed.sessions.value[0].turn_status, 'completed')
})
test('关闭页面后定时器和在途结果都不能继续回写', async (t) => {
  t.mock.timers.enable({ apis: ['setInterval'] })
  let resolveRequest,
    requests = 0
  const h = setup(t, () => {
    requests += 1
    return new Promise((resolve) => {
      resolveRequest = resolve
    })
  })
  h.scope.stop()
  resolveRequest(response([{ session_id: 'late' }]))
  await settle()
  t.mock.timers.tick(9000)
  await settle()
  assert.equal(requests, 1)
  assert.deepEqual(h.observed.sessions.value, [])
})

test('普通 HTTP 环境没有 randomUUID 时仍能投递整树停止和继续', async (t) => {
  const originalCrypto = Object.getOwnPropertyDescriptor(globalThis, 'crypto')
  Object.defineProperty(globalThis, 'crypto', { configurable: true, value: {} })
  const originalControl = agentApi.controlSessionTree
  const calls = []
  agentApi.controlSessionTree = async (...args) => calls.push(args)
  t.after(() => {
    agentApi.controlSessionTree = originalControl
    if (originalCrypto) Object.defineProperty(globalThis, 'crypto', originalCrypto)
    else delete globalThis.crypto
  })
  const { default: component } = await server.ssrLoadModule(
    '/src/modules/session/ui/CooperationTree.vue'
  )
  let state
  await renderToString(
    createSSRApp({
      setup() {
        state = component.setup(
          { currentId: 'root', sessions: [], error: '' },
          { expose() {}, emit() {} }
        )
        return () => h('div')
      }
    })
  )
  await state.control(true)
  await state.control(false)
  assert.deepEqual(
    calls.map(([id, stopped]) => [id, stopped]),
    [
      ['root', true],
      ['root', false]
    ]
  )
  assert.ok(calls.every(([, , key]) => typeof key === 'string' && key.length > 0))
  assert.notEqual(calls[0][2], calls[1][2])
})

test('协作任务结束或只有已暂停队列时，汇总与列表都隐藏停止按钮', async () => {
  for (const compact of [true, false]) {
    for (const session of [
      null,
      { turn_status: null },
      { turn_status: 'completed' },
      { turn_status: 'failed' },
      { turn_status: 'cancelled' },
      { turn_status: 'completed', has_pending_input: true, queue_paused: true }
    ]) {
      const sessions = session ? [{ session_id: 'root', path: '/root', ...session }] : []
      const app = createSSRApp(CooperationTree, { currentId: 'root', sessions, compact })
      app.use(createPinia())
      const html = await renderToString(app)
      assert.doesNotMatch(html, /aria-label="停止全部"/, JSON.stringify({ compact, session }))
    }
  }
})

test('未结束的协作轮次或未暂停的排队输入保留停止按钮', async () => {
  for (const compact of [true, false]) {
    for (const session of [
      { turn_status: 'running', run_status: 'running' },
      { turn_status: 'running', run_status: 'pending' },
      { turn_status: 'waiting', waiting_for: 'approval' },
      { turn_status: 'waiting', waiting_for: 'answer' },
      { turn_status: 'waiting', waiting_for: 'cooperation' },
      { turn_status: 'cancelling' },
      { turn_status: 'completed', has_pending_input: true, queue_paused: false }
    ]) {
      const sessions = [
        { session_id: 'root', path: '/root', turn_status: 'completed' },
        { session_id: 'child', path: '/root/child', name: 'child', ...session }
      ]
      const app = createSSRApp(CooperationTree, { currentId: 'root', sessions, compact })
      app.use(createPinia())
      const html = await renderToString(app)
      assert.match(html, /aria-label="停止全部"/, JSON.stringify({ compact, session }))
    }
  }
})

test('每次刷新只请求一次完整协作摘要，超过百项的成员全部保留', async (t) => {
  const calls = []
  const sessions = Array.from({ length: 107 }, (_, i) => ({
    session_id: `member-${i}`,
    turn_status: i === 106 ? 'running' : 'completed'
  }))
  const h = setup(t, async (...args) => {
    calls.push(args)
    return response(sessions)
  })
  await settle()
  assert.deepEqual(calls, [['root']])
  assert.deepEqual(h.observed.sessions.value, sessions)
  await h.observed.refresh()
  assert.deepEqual(calls, [['root'], ['root']])
  assert.equal(h.observed.sessions.value.at(-1).turn_status, 'running')
})

test('完整协作列表展示百项后的运行成员，没有分页入口或不完整计数', async () => {
  const sessions = Array.from({ length: 107 }, (_, i) => ({
    session_id: `member-${i}`,
    path: `/root/worker${i}`,
    name: `worker${i}`,
    turn_status: i === 106 ? 'running' : 'completed'
  }))
  const app = createSSRApp(CooperationTree, { currentId: 'root', sessions })
  app.use(createPinia())
  const html = await renderToString(app)
  assert.match(html, /打开会话 worker106/)
  assert.match(html, /1 执行中/)
  assert.match(html, /aria-label="停止全部"/)
  assert.doesNotMatch(html, /加载更多|已加载：|107\+/)
})
