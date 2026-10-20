import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers'

import { createPinia, setActivePinia } from 'pinia'
import { createTestServer } from '../helpers/createTestServer.js'

globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {}
}

test('线程创建期间共享 Store 拒绝外层切换，创建结果可显式提交', async () => {
  const server = await createTestServer({ server: { middlewareMode: true }, appType: 'custom' })
  setActivePinia(createPinia())
  try {
    const { useChatThreadsStore } = await server.ssrLoadModule(
      '/src/modules/session/model/chatThreads.js'
    )
    const store = useChatThreadsStore()
    store.setCurrentThreadId('thread-before')
    store.setThreadCreationInFlight(true)

    assert.equal(store.setCurrentThreadId('thread-sidebar'), false)
    assert.equal(store.currentThreadId, 'thread-before')
    assert.equal(store.setCurrentThreadId('thread-created', { force: true }), true)
    assert.equal(store.currentThreadId, 'thread-created')

    store.setThreadCreationInFlight(false)
  } finally {
    await server.close()
  }
})

test('Project 删除后 Store 只移除对应 Session 并清空当前选择', async () => {
  const server = await createTestServer({ server: { middlewareMode: true }, appType: 'custom' })
  setActivePinia(createPinia())
  try {
    const { useChatThreadsStore } = await server.ssrLoadModule(
      '/src/modules/session/model/chatThreads.js'
    )
    const store = useChatThreadsStore()
    store.threads = [
      { id: 'a', yuxi: { project_id: 'project-a' } },
      { id: 'b', yuxi: { project_id: 'project-b' } }
    ]
    store.setCurrentThreadId('a')
    assert.deepEqual(store.removeThreadsByProject('project-a'), ['a'])
    assert.deepEqual(store.threads, [{ id: 'b', yuxi: { project_id: 'project-b' } }])
    assert.equal(store.currentThreadId, null)
  } finally {
    await server.close()
  }
})

for (const mutation of ['pin', 'archive', 'create', 'detail']) {
  test(`列表游标不被 ${mutation} 操作改变，下一页保留边界 Session`, async () => {
    const server = await createTestServer({
      server: { middlewareMode: true, hmr: false },
      appType: 'custom'
    })
    setActivePinia(createPinia())
    try {
      const { threadApi } = await server.ssrLoadModule('/src/apis/agent_api.js')
      const calls = []
      threadApi.getThreads = async (_agentId, limit, after, { isPinned } = {}) => {
        if (isPinned) return { data: [], last_id: null, has_more: false }
        calls.push({ limit, after })
        return !after
          ? {
              object: 'list',
              data: [
                { id: 'first', yuxi: { is_pinned: true } },
                { id: 'boundary', yuxi: {} }
              ],
              last_id: 'boundary',
              has_more: true
            }
          : { object: 'list', data: [{ id: 'next', yuxi: {} }], last_id: 'next', has_more: false }
      }
      threadApi.updateThread = async () => ({ id: 'boundary', yuxi: { is_pinned: true } })
      threadApi.archiveThread = async () => ({ id: 'boundary', yuxi: { archived: true } })
      threadApi.createThread = async () => ({ id: 'created', yuxi: {} })
      const { useChatThreadsStore } = await server.ssrLoadModule(
        '/src/modules/session/model/chatThreads.js'
      )
      const store = useChatThreadsStore()
      await store.loadThreads()
      if (mutation === 'pin') await store.updateThread('boundary', null, true)
      if (mutation === 'archive') await store.archiveThread('boundary')
      if (mutation === 'create') await store.createThread('agent')
      if (mutation === 'detail')
        store.upsertThread({ id: 'child', yuxi: { parent_session_id: 'first' } })
      await store.loadMoreThreads()
      assert.deepEqual(calls, [
        { limit: 100, after: undefined },
        { limit: 100, after: 'boundary' }
      ])
      assert.equal(
        store.threads.some((session) => session.id === 'next'),
        true
      )
      assert.equal(store.hasMoreThreads, false)
    } finally {
      await server.close()
    }
  })
}

test('下一页与归档串行执行，归档结果不会重新出现在列表', async () => {
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom'
  })
  setActivePinia(createPinia())
  try {
    const { threadApi } = await server.ssrLoadModule('/src/apis/agent_api.js')
    let resolvePage
    const operations = []
    threadApi.getThreads = async (_agentId, _limit, after, { isPinned } = {}) => {
      if (isPinned) return { data: [], last_id: null, has_more: false }
      if (!after)
        return { data: [{ id: 'boundary', yuxi: {} }], last_id: 'boundary', has_more: true }
      operations.push('page')
      return new Promise((resolve) => {
        resolvePage = resolve
      })
    }
    threadApi.archiveThread = async () => {
      operations.push('archive')
    }
    const { useChatThreadsStore } = await server.ssrLoadModule(
      '/src/modules/session/model/chatThreads.js'
    )
    const store = useChatThreadsStore()
    await store.loadThreads()
    const loading = store.loadMoreThreads()
    await new Promise(setImmediate)
    const archiving = store.archiveThread('boundary')
    assert.deepEqual(operations, ['page'])
    resolvePage({ data: [{ id: 'next', yuxi: {} }], last_id: 'next', has_more: false })
    await Promise.all([loading, archiving])
    assert.deepEqual(operations, ['page', 'archive'])
    assert.deepEqual(
      store.threads.map((session) => session.id),
      ['next']
    )
  } finally {
    await server.close()
  }
})

test('较老的置顶 Session 始终展示，刷新状态不改变普通列表游标', async () => {
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom'
  })
  setActivePinia(createPinia())
  try {
    const { threadApi } = await server.ssrLoadModule('/src/apis/agent_api.js')
    let pinnedStatus = 'idle'
    const nextCursors = []
    threadApi.getThreads = async (_agentId, _limit, after, { isPinned } = {}) => {
      if (isPinned)
        return {
          data: [{ id: 'old-pin', status: pinnedStatus, yuxi: { is_pinned: true } }],
          last_id: 'old-pin',
          has_more: false
        }
      if (after) nextCursors.push(after)
      return after
        ? { data: [{ id: 'next', yuxi: {} }], last_id: 'next', has_more: false }
        : { data: [{ id: 'newest', yuxi: {} }], last_id: 'newest', has_more: true }
    }
    const { useChatThreadsStore } = await server.ssrLoadModule(
      '/src/modules/session/model/chatThreads.js'
    )
    const store = useChatThreadsStore()
    await store.loadThreads()
    assert.deepEqual(
      store.threads.map((item) => item.id),
      ['newest', 'old-pin']
    )
    pinnedStatus = 'in_progress'
    await store.syncThreadStatuses()
    assert.equal(store.threads.find((item) => item.id === 'old-pin').status, 'in_progress')
    await store.loadMoreThreads()
    assert.deepEqual(nextCursors, ['newest'])
    assert.deepEqual(
      store.threads.map((item) => item.id),
      ['newest', 'old-pin', 'next']
    )
  } finally {
    await server.close()
  }
})

test('后台状态读取与改名串行，迟到资源不会覆盖已保存的标题', async () => {
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom'
  })
  setActivePinia(createPinia())
  try {
    const { threadApi } = await server.ssrLoadModule('/src/apis/agent_api.js')
    let resolvePage
    const writes = []
    threadApi.getThreads = async (_agentId, _limit, _after, { isPinned } = {}) => {
      if (isPinned) return { data: [], last_id: null, has_more: false }
      return new Promise((resolve) => {
        resolvePage = resolve
      })
    }
    threadApi.updateThread = async () => {
      writes.push('rename')
      return { id: 'session', yuxi: { title: '已保存的新标题' } }
    }
    const { useChatThreadsStore } = await server.ssrLoadModule(
      '/src/modules/session/model/chatThreads.js'
    )
    const store = useChatThreadsStore()
    store.upsertThread({ id: 'session', yuxi: { title: '旧标题' } })
    const syncing = store.syncThreadStatuses()
    await new Promise(setImmediate)
    const renamed = store.updateThread('session', '已保存的新标题')
    assert.deepEqual(writes, [])
    resolvePage({
      data: [{ id: 'session', status: 'idle', yuxi: { title: '旧标题' } }],
      has_more: false
    })
    await Promise.all([syncing, renamed])
    assert.deepEqual(writes, ['rename'])
    assert.equal(store.threads[0].yuxi.title, '已保存的新标题')
  } finally {
    await server.close()
  }
})
