import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createTestServer } from '../helpers/createTestServer.js'
import { createPinia, disposePinia, setActivePinia } from 'pinia'

let server, api, useStore
before(async () => {
  globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
  server = await createTestServer({ server: { middlewareMode: true, hmr: false } })
  ;({ agentApi: api } = await server.ssrLoadModule('/src/apis/index.js'))
  ;({ useTurnReferencesStore: useStore } = await server.ssrLoadModule(
    '/src/modules/session/model/turnReferences.js'
  ))
})
after(async () => {
  await server?.close()
  delete globalThis.localStorage
})

function setup(t) {
  const pinia = createPinia()
  setActivePinia(pinia)
  t.after(() => disposePinia(pinia))
  return useStore()
}

test('来源读取失败可重试，持久结果刷新后恢复', async (t) => {
  const store = setup(t)
  const saved = { citations: [{ source_id: 's1' }], sources: [{ id: 's1' }] }
  t.mock.method(api, 'getTurnReferences', async () => { throw new Error('读取失败') })
  await store.load('thread-a', 'turn-a')
  assert.equal(store.getEntry('thread-a', 'turn-a').loaded, false)
  assert.equal(store.getEntry('thread-a', 'turn-a').error, '读取失败')
  t.mock.method(api, 'getTurnReferences', async () => ({ available: true, sources: saved.sources, references: saved }))
  await store.load('thread-a', 'turn-a')
  assert.deepEqual(store.getEntry('thread-a', 'turn-a').references, saved)
  assert.equal(store.getEntry('thread-a', 'turn-a').error, '')
})

test('切换会话期间的晚到标注结果仍写入原 Turn', async (t) => {
  const store = setup(t)
  let complete
  t.mock.method(api, 'annotateTurnReferences', () => new Promise((resolve) => { complete = resolve }))
  const pending = store.annotate('thread-a', 'turn-a')
  const next = store.getEntry('thread-b', 'turn-b')
  assert.equal(store.getEntry('thread-a', 'turn-a').annotating, true)
  const saved = { citations: [], sources: [] }
  complete(saved)
  await pending
  assert.deepEqual(store.getEntry('thread-a', 'turn-a').references, saved)
  assert.equal(next.references, null)
  assert.equal(next.annotating, false)
})

test('标注失败保留可重试入口，空匹配是有效的持久结果', async (t) => {
  const store = setup(t)
  t.mock.method(api, 'annotateTurnReferences', async () => { throw new Error('模型返回无效结果') })
  await store.annotate('thread-a', 'turn-a')
  const entry = store.getEntry('thread-a', 'turn-a')
  assert.equal(entry.annotating, false)
  assert.equal(entry.references, null)
  assert.equal(entry.error, '模型返回无效结果')
  t.mock.method(api, 'annotateTurnReferences', async () => ({ citations: [], sources: [] }))
  await store.annotate('thread-a', 'turn-a')
  assert.deepEqual(entry.references.citations, [])
  assert.equal(entry.error, '')
})
