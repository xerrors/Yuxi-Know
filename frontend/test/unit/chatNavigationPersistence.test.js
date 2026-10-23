import assert from 'node:assert/strict'
import test from 'node:test'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import persistedState from 'pinia-plugin-persistedstate'
import { createApp, nextTick } from 'vue'
import { createTestServer } from '../helpers/createTestServer.js'

test('导航偏好跨刷新保留，按认证账号隔离，临时展示和消息不写入存储', async (t) => {
  const saved = new Map()
  globalThis.localStorage = {
    getItem: key => saved.get(key) ?? null,
    setItem: (key, value) => saved.set(key, value),
    removeItem: key => saved.delete(key)
  }
  const server = await createTestServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' })
  let pinia
  try {
    const { useChatUIStore } = await server.ssrLoadModule('/src/modules/session/model/chatUI.js')
    const { useChatThreadsStore } = await server.ssrLoadModule('/src/modules/session/model/chatThreads.js')
    const { threadApi } = await server.ssrLoadModule('/src/apis/index.js')
    const { useUserStore } = await server.ssrLoadModule('/src/modules/identity/model/user.js')
    /** 重建真实 Pinia，模拟浏览器重新加载且认证稍后到达。 */
    function reload(userId = null) {
      if (pinia) disposePinia(pinia)
      pinia = createPinia().use(persistedState)
      createApp({}).use(pinia)
      setActivePinia(pinia)
      const user = useUserStore()
      user.userId = userId
      return { ui: useChatUIStore(), threads: useChatThreadsStore(), user }
    }
    let { ui, threads } = reload(1)
    threads.setCurrentThreadId('thread-a')
    ui.sidebarCollapsed = true
    ui.sessionsPinned = true
    ui.sessionPeekOpen = true
    ui.expandedProjects.add('project-a')
    await nextTick()
    assert.deepEqual(JSON.parse(saved.get('chat-ui-store')), {
      sidebarCollapsed: true,
      navigationByUser: { 1: { lastThreadId: 'thread-a', sessionsPinned: true } }
    })
    let state = reload()
    assert.equal(state.ui.lastThreadId, null)
    assert.equal(state.ui.sessionsPinned, false)
    state.ui.lastThreadId = 'unauthenticated-write'
    state.ui.sessionsPinned = false
    state.user.userId = 1
    assert.equal(state.ui.lastThreadId, 'thread-a')
    assert.equal(state.ui.sessionsPinned, true)
    assert.equal(state.ui.sidebarCollapsed, true)
    assert.equal(state.threads.currentThreadId, null, '持久目标不能冒充已加载的工作区')
    assert.equal(state.ui.sessionPeekOpen, false)
    assert.equal(state.ui.expandedProjects.size, 0)
    state.threads.setCurrentThreadId('thread-a')
    state.ui.sessionPeekOpen = true
    state.ui.projectPendingId = 'old-account-pending'
    state.user.userId = 2
    assert.equal(state.threads.currentThreadId, null, '账号变更必须清理内存选择且不改写任一账号偏好')
    assert.equal(state.ui.projectPendingId, null, '账号切换不能继承旧项目请求的禁用状态')
    assert.equal(state.ui.sessionPeekOpen, false, '账号切换不能继承临时浮层')
    assert.equal(state.ui.lastThreadId, null, '不能从上一账号残留的当前线程复制目标')
    assert.equal(state.ui.sessionsPinned, false)
    state.threads.setCurrentThreadId('thread-b')
    state.ui.sessionsPinned = true
    await nextTick()
    state = reload(1)
    assert.equal(state.ui.lastThreadId, 'thread-a')
    assert.equal(state.ui.sessionsPinned, true)
    state.threads.setThreadCreationInFlight(true)
    assert.equal(state.threads.setCurrentThreadId(null), false)
    assert.equal(state.ui.lastThreadId, 'thread-a', '创建事务拒绝的切换不能覆盖返回目标')
    state.threads.setThreadCreationInFlight(false)
    state.threads.setCurrentThreadId(null)
    state.ui.sessionsPinned = false
    await nextTick()
    state = reload(1)
    assert.equal(state.ui.lastThreadId, null, '显式新建或失效回退须清除旧目标')
    assert.equal(state.ui.sessionsPinned, false, '显式收起须跨刷新保持')
    state = reload(2)
    assert.equal(state.ui.lastThreadId, 'thread-b')
    assert.equal(state.ui.sessionsPinned, true)
    state.threads.upsertThread({ id: 'thread-b', yuxi: { project_id: 'removed' } })
    state.threads.removeThreadsByProject('removed')
    // 刷新后的偏好独立于未选择的工作区，项目移除也须清除它。
    assert.equal(state.ui.lastThreadId, null)
    state.threads.setCurrentThreadId('shared-thread')
    let finishArchive
    const archiveRequest = t.mock.method(threadApi, 'archiveThread', () => new Promise(resolve => { finishArchive = resolve }))
    const archiving = state.threads.archiveThread('shared-thread')
    await Promise.resolve()
    await Promise.resolve()
    state.user.userId = 1
    state.threads.setCurrentThreadId('shared-thread')
    finishArchive()
    await archiving
    assert.equal(state.ui.lastThreadId, 'shared-thread', '旧账号归档响应不能清掉新账号的同名目标')
    let finishQueue
    const blockingOperation = state.threads.withThreadListUpdate(() => new Promise(resolve => { finishQueue = resolve }))
    await Promise.resolve()
    await Promise.resolve()
    const queuedArchive = state.threads.archiveThread('shared-thread')
    state.user.userId = 2
    state.threads.setCurrentThreadId('shared-thread')
    finishQueue()
    await blockingOperation
    await queuedArchive
    assert.equal(archiveRequest.mock.callCount(), 1, '排队期间切换账号不能用新身份发起旧请求')
    assert.equal(state.ui.lastThreadId, 'shared-thread')
    saved.set('chat-ui-store', JSON.stringify({ navigationByUser: { 1: { lastThreadId: 42, sessionsPinned: 'true' } } }))
    state = reload(1)
    assert.equal(state.ui.lastThreadId, null)
    assert.equal(state.ui.sessionsPinned, false)
  } finally {
    if (pinia) disposePinia(pinia)
    await server.close()
    delete globalThis.localStorage
  }
})
