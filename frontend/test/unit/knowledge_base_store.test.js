import test from 'node:test'
import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'

import { createPinia, setActivePinia } from 'pinia'
import { createApp } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createTestServer } from '../helpers/createTestServer.js'
import { message } from 'ant-design-vue'

const storageValues = new Map()
globalThis.localStorage = {
  getItem: (key) => storageValues.get(key) ?? null,
  setItem: (key, value) => storageValues.set(key, String(value)),
  removeItem: (key) => storageValues.delete(key),
  clear: () => storageValues.clear()
}

test('解析和入库动作保留参数、结果反馈与 loading 生命周期', async (t) => {
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom'
  })
  const pinia = createPinia()
  const app = createApp({})
  app.use(pinia)
  app.use(createRouter({ history: createMemoryHistory(), routes: [] }))
  setActivePinia(pinia)
  const { documentApi, knowledgeBaseApi } = await server.ssrLoadModule('/src/apis/knowledge_api.js')
  const { useKnowledgeBaseStore } = await server.ssrLoadModule(
    '/src/modules/knowledge/model/knowledgeBase.js'
  )
  const store = app.runWithContext(() => useKnowledgeBaseStore())
  store.kbId = 'kb-submit'
  const feedback = []
  t.mock.method(message, 'success', (text) => feedback.push(text))
  t.mock.method(message, 'error', (text) => feedback.push(text))
  t.mock.method(console, 'error', () => {})
  t.mock.method(knowledgeBaseApi, 'getKnowledgeBaseInfo', async () => ({
    stats: { processing_count: 0 }
  }))
  t.mock.method(documentApi, 'listDocuments', async () => ({
    items: [{ file_id: 'file-result', status: 'indexed' }],
    stats: { processing_count: 0 }
  }))

  try {
    for (const [action, apiMethod, selected, successText] of [
      ['parseFiles', 'parseDocuments', true, '解析任务已提交'],
      ['parsePendingFiles', 'parsePendingDocuments', false, '解析任务已提交'],
      ['indexFiles', 'indexDocuments', true, '入库任务已提交'],
      ['indexPendingFiles', 'indexPendingDocuments', false, '入库任务已提交']
    ]) {
      await t.test(action, async () => {
        const params = { batch_size: 2 }
        const args = selected ? [['file-selected'], params] : [params]
        let respond
        const request = t.mock.method(documentApi, apiMethod, (...received) => {
          assert.deepEqual(received, ['kb-submit', ...args])
          assert.equal(store.state.chunkLoading, true)
          return new Promise((resolve, reject) => {
            respond = (result) => result instanceof Error ? reject(result) : resolve(result)
          })
        })
        if (selected) {
          assert.equal(await store[action]([]), undefined)
          assert.equal(request.mock.callCount(), 0)
          assert.equal(store.state.chunkLoading, false)
        }
        for (const [response, expected, expectedText] of [
          [{ status: 'queued' }, true, successText],
          [{ status: 'success', message: '服务端确认' }, true, '服务端确认'],
          [{ status: 'failed' }, false, '提交失败'],
          [{ status: 'failed', message: '资源被锁定' }, false, '资源被锁定'],
          [new Error('连接中断'), false, '连接中断'],
          [new Error(), false, '请求失败']
        ]) {
          feedback.length = 0
          store.documentFiles = []
          const pending = store[action](...args)
          assert.equal(store.state.chunkLoading, true)
          respond(response)
          assert.equal(await pending, expected)
          assert.equal(store.state.chunkLoading, false)
          assert.deepEqual(feedback, [expectedText])
          assert.deepEqual(
            store.documentFiles,
            expected ? [{ file_id: 'file-result', status: 'indexed' }] : []
          )
        }
      })
    }
  } finally {
    store.stopAutoRefresh()
    store.$dispose()
    await server.close()
  }
})

test('从二级目录点击全部文件会清空 parent_id 并返回根目录', async (t) => {
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom'
  })

  try {
    const warnings = []
    t.mock.method(console, 'warn', (...args) => warnings.push(args))
    const pinia = createPinia()
    const app = createApp({})
    app.use(pinia)
    app.use(createRouter({ history: createMemoryHistory(), routes: [] }))
    setActivePinia(pinia)
    const { documentApi } = await server.ssrLoadModule('/src/apis/knowledge_api.js')
    const { useKnowledgeBaseStore } = await server.ssrLoadModule(
      '/src/modules/knowledge/model/knowledgeBase.js'
    )
    const requests = []

    documentApi.listDocuments = async (kbId, params) => {
      requests.push({ kbId, params })
      return {
        items: [],
        page: 1,
        page_size: 100,
        total: 0,
        has_more: false,
        path_prefix: ''
      }
    }

    const store = app.runWithContext(() => useKnowledgeBaseStore())
    store.kbId = 'kb_1'
    store.fileBrowser.parentId = 'folder_2'
    store.folderBreadcrumbs = [
      { file_id: null, filename: '全部文件', path_prefix: '' },
      { file_id: 'folder_2', filename: '二级目录', path_prefix: '' }
    ]

    await store.goToFolder(0)

    assert.equal(store.fileBrowser.parentId, null)
    assert.deepEqual(store.folderBreadcrumbs, [
      { file_id: null, filename: '全部文件', path_prefix: '' }
    ])
    assert.deepEqual(requests, [
      {
        kbId: 'kb_1',
        params: {
          page: 1,
          page_size: 100,
          status: 'all',
          recursive: false
        }
      }
    ])
    assert.deepEqual(warnings, [])
  } finally {
    await server.close()
  }
})

test('知识库提交跨账号返回时，不把旧入队任务登记给新账号', async (t) => {
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom'
  })
  const pinia = createPinia()
  const app = createApp({})
  app.use(pinia)
  app.use(createRouter({ history: createMemoryHistory(), routes: [] }))
  setActivePinia(pinia)
  const { documentApi, knowledgeBaseApi } = await server.ssrLoadModule('/src/apis/knowledge_api.js')
  const { useKnowledgeBaseStore } = await server.ssrLoadModule(
    '/src/modules/knowledge/model/knowledgeBase.js'
  )
  const { useUserStore } = await server.ssrLoadModule('/src/modules/identity/model/user.js')
  const { useBackgroundJobsStore } = await server.ssrLoadModule(
    '/src/modules/background-jobs/model/jobs.js'
  )
  const { backgroundJobsApi } = await server.ssrLoadModule('/src/apis/background_jobs.js')
  const knowledgeBase = app.runWithContext(() => useKnowledgeBaseStore())
  const user = useUserStore()
  const job_tracker = useBackgroundJobsStore()
  const detailRequests = []
  t.mock.method(backgroundJobsApi, 'fetchJobDetail', async (id) => {
    detailRequests.push(id)
    return { job: { id, status: 'success', progress: 100 } }
  })
  t.mock.method(message, 'success', () => {})
  t.mock.method(knowledgeBaseApi, 'getKnowledgeBaseInfo', async () => ({
    stats: { processing_count: 0 }
  }))
  t.mock.method(documentApi, 'listDocuments', async () => ({
    items: [],
    stats: { processing_count: 0 }
  }))
  try {
    for (const [action, apiMethod, args] of [
      ['addFiles', 'addDocuments', [{ items: ['fixture'], contentType: 'file', params: {} }]],
      ['parseFiles', 'parseDocuments', [['file']]],
      ['parsePendingFiles', 'parsePendingDocuments', []],
      ['indexFiles', 'indexDocuments', [['file']]],
      ['indexPendingFiles', 'indexPendingDocuments', []]
    ]) {
      await t.test(action, async () => {
        knowledgeBase.kbId = 'test-kb'
        user.token = `old-${action}`
        user.userRole = 'admin'
        let resolve
        t.mock.method(
          documentApi,
          apiMethod,
          () =>
            new Promise((done) => {
              resolve = done
            })
        )
        const pending = knowledgeBase[action](...args)
        user.logout()
        user.token = `new-${action}`
        user.userRole = 'admin'
        resolve({ status: 'queued', job_id: 'old-job' })
        assert.equal(await pending, true)
        assert.deepEqual(job_tracker.jobs, [])
        assert.equal(detailRequests.includes('old-job'), false)
        const current = knowledgeBase[action](...args)
        resolve({ status: 'queued', job_id: `new-${action}` })
        assert.equal(await current, true)
        await setImmediate()
        assert.equal(job_tracker.jobs[0].id, `new-${action}`)
        assert.equal(job_tracker.jobs[0].status, 'success')
        job_tracker.reset()
      })
    }
  } finally {
    knowledgeBase.stopAutoRefresh()
    job_tracker.$dispose()
    await server.close()
  }
})

test('自动入库中间状态停止轮询后，作业终态仍回读正确文件与统计', async (t) => {
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom'
  })
  const pinia = createPinia(),
    app = createApp({})
  app.use(pinia)
  app.use(createRouter({ history: createMemoryHistory(), routes: [] }))
  setActivePinia(pinia)
  const { documentApi, knowledgeBaseApi } = await server.ssrLoadModule('/src/apis/knowledge_api.js')
  const { backgroundJobsApi } = await server.ssrLoadModule('/src/apis/background_jobs.js')
  const { useKnowledgeBaseStore } = await server.ssrLoadModule(
    '/src/modules/knowledge/model/knowledgeBase.js'
  )
  const { useUserStore } = await server.ssrLoadModule('/src/modules/identity/model/user.js')
  const { useBackgroundJobsStore } = await server.ssrLoadModule(
    '/src/modules/background-jobs/model/jobs.js'
  )
  const store = app.runWithContext(() => useKnowledgeBaseStore())
  const user = useUserStore(),
    jobs = useBackgroundJobsStore()
  user.token = 'file-session'
  user.userRole = 'admin'
  store.kbId = 'auto-kb'
  let status = 'parsed',
    jobStatus = 'running'
  let listReads = 0
  knowledgeBaseApi.getKnowledgeBaseInfo = async () => ({
    kb_id: 'auto-kb',
    stats: { processing_count: 0, token_count: status === 'indexed' ? 70 : 0 }
  })
  documentApi.listDocuments = async () => {
    listReads++
    return {
      items: [{ file_id: 'document', status, token_count: status === 'indexed' ? 70 : 0 }],
      stats: { processing_count: 0, token_count: status === 'indexed' ? 70 : 0 }
    }
  }
  documentApi.addDocuments = async () => ({ status: 'queued', job_id: 'auto-job' })
  backgroundJobsApi.fetchJobDetail = async (id) => ({ job: { id, status: jobStatus } })
  backgroundJobsApi.fetchJobs = async () => ({ jobs: [{ id: 'auto-job', status: jobStatus }] })
  t.mock.method(message, 'success', () => {})
  try {
    await store.addFiles({
      items: ['document.md'],
      contentType: 'file',
      params: { auto_index: true }
    })
    assert.equal(store.documentFiles[0].status, 'parsed')
    assert.equal(store.state.autoRefresh, false)
    status = 'indexed'
    jobStatus = 'success'
    await jobs.loadJobs()
    await setImmediate()
    assert.equal(store.documentFiles[0].status, 'indexed')
    assert.equal(store.documentFiles[0].token_count, 70)
    assert.equal(store.knowledgeBase.stats.token_count, 70)
    const completedReads = listReads
    await jobs.loadJobs()
    await setImmediate()
    assert.equal(listReads, completedReads)
  } finally {
    store.stopAutoRefresh()
    store.$dispose()
    jobs.$dispose()
    await server.close()
  }
})

test('切库或切账号后，旧文件与统计响应不能覆盖新页面', async (t) => {
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom'
  })
  const pinia = createPinia(),
    app = createApp({})
  app.use(pinia)
  app.use(createRouter({ history: createMemoryHistory(), routes: [] }))
  setActivePinia(pinia)
  const { documentApi, knowledgeBaseApi } = await server.ssrLoadModule('/src/apis/knowledge_api.js')
  const { useKnowledgeBaseStore } = await server.ssrLoadModule(
    '/src/modules/knowledge/model/knowledgeBase.js'
  )
  const { useUserStore } = await server.ssrLoadModule('/src/modules/identity/model/user.js')
  const store = app.runWithContext(() => useKnowledgeBaseStore()),
    user = useUserStore()
  try {
    for (const change of ['knowledge-base', 'account']) {
      await t.test(change, async () => {
        store.kbId = 'old-kb'
        user.token = 'old-account'
        let resolveInfo, resolveFiles
        knowledgeBaseApi.getKnowledgeBaseInfo = () =>
          new Promise((resolve) => {
            resolveInfo = resolve
          })
        documentApi.listDocuments = () =>
          new Promise((resolve) => {
            resolveFiles = resolve
          })
        const pending = Promise.all([
          store.getKnowledgeBaseInfo(undefined, true),
          store.loadDocumentFiles()
        ])
        if (change === 'knowledge-base') store.kbId = 'new-kb'
        else user.token = 'new-account'
        store.knowledgeBase = { kb_id: 'current', stats: { token_count: 99 } }
        store.documentFiles = [{ file_id: 'current' }]
        resolveInfo({ kb_id: 'old-kb', stats: { token_count: 1 } })
        resolveFiles({ items: [{ file_id: 'old-file' }] })
        await pending
        assert.equal(store.knowledgeBase.kb_id, 'current')
        assert.equal(store.knowledgeBase.stats.token_count, 99)
        assert.equal(store.documentFiles[0].file_id, 'current')
      })
    }
  } finally {
    store.stopAutoRefresh()
    store.$dispose()
    await server.close()
  }
})

test('同库旧请求晚到不能回退入库状态，元信息不能覆盖更新的文件统计', async () => {
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom'
  })
  const pinia = createPinia()
  const app = createApp({})
  app.use(pinia)
  app.use(createRouter({ history: createMemoryHistory(), routes: [] }))
  setActivePinia(pinia)
  const { documentApi, knowledgeBaseApi } = await server.ssrLoadModule('/src/apis/knowledge_api.js')
  const { useKnowledgeBaseStore } = await server.ssrLoadModule(
    '/src/modules/knowledge/model/knowledgeBase.js'
  )
  const store = app.runWithContext(() => useKnowledgeBaseStore())
  store.kbId = 'same-kb'
  const snapshot = (status, count) => ({
    kb_id: 'same-kb',
    items: [{ file_id: 'document', status }],
    stats: { processing_count: 0, token_count: count }
  })
  try {
    let resolveInfo, resolveFiles
    knowledgeBaseApi.getKnowledgeBaseInfo = () =>
      new Promise((resolve) => {
        resolveInfo = resolve
      })
    documentApi.listDocuments = () =>
      new Promise((resolve) => {
        resolveFiles = resolve
      })
    const older = Promise.all([
      store.getKnowledgeBaseInfo(undefined, true),
      store.loadDocumentFiles()
    ])
    knowledgeBaseApi.getKnowledgeBaseInfo = async () => snapshot('indexed', 70)
    documentApi.listDocuments = async () => snapshot('indexed', 70)
    await Promise.all([
      store.getKnowledgeBaseInfo(undefined, true, true),
      store.loadDocumentFiles({ isBackground: true })
    ])
    assert.equal(store.state.knowledgeBaseLoading, false)
    assert.equal(store.state.lock, false)
    assert.equal(store.fileBrowser.loading, false)
    resolveInfo(snapshot('parsed', 0))
    resolveFiles(snapshot('parsed', 0))
    await older
    assert.equal(store.documentFiles[0].status, 'indexed')
    assert.equal(store.knowledgeBase.stats.token_count, 70)

    knowledgeBaseApi.getKnowledgeBaseInfo = () =>
      new Promise((resolve) => {
        resolveInfo = resolve
      })
    const metadata = store.getKnowledgeBaseInfo(undefined, true)
    await store.loadDocumentFiles()
    resolveInfo(snapshot('parsed', 0))
    await metadata
    assert.equal(store.documentFiles[0].status, 'indexed')
    assert.equal(store.knowledgeBase.stats.token_count, 70)
    assert.equal(store.knowledgeBase.files.document.status, 'indexed')
  } finally {
    store.stopAutoRefresh()
    store.$dispose()
    await server.close()
  }
})
