import assert from 'node:assert/strict'
import test from 'node:test'
import { createPinia, disposePinia } from 'pinia'
import { createSSRApp } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createTestServer } from '../helpers/createTestServer.js'

test('重复打开同一真实目录只增加一次面包屑，子目录仍可进入', async () => {
  const previousStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
  const server = await createTestServer({ server: { middlewareMode: true, hmr: false } })
  const pinia = createPinia()
  try {
    const app = createSSRApp({ render: () => null })
    app.use(pinia)
    app.use(createRouter({ history: createMemoryHistory(), routes: [] }))
    const { useKnowledgeBaseStore } = await server.ssrLoadModule('/src/modules/knowledge/model/knowledgeBase.js')
    const store = app.runWithContext(() => useKnowledgeBaseStore())
    const folder = { file_id: 'parent', filename: '资料', is_folder: true }
    await Promise.all([store.enterFolder(folder), store.enterFolder(folder)])
    await store.enterFolder({ file_id: 'child', filename: '下级', is_folder: true })
    assert.deepEqual(store.folderBreadcrumbs.map((item) => item.file_id), [null, 'parent', 'child'])
  } finally {
    disposePinia(pinia)
    await server.close()
    if (previousStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = previousStorage
  }
})
