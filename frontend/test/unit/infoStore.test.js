import assert from 'node:assert/strict'
import test from 'node:test'

import { createPinia, setActivePinia } from 'pinia'
import { createTestServer } from '../helpers/createTestServer.js'

test('调试模式读取受限 LocalStorage 时降级为关闭', async () => {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem() {
        throw new DOMException('blocked', 'SecurityError')
      },
      setItem() {},
      removeItem() {}
    }
  })
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom'
  })
  setActivePinia(createPinia())
  try {
    const { useInfoStore } = await server.ssrLoadModule('/src/modules/settings/model/info.js')
    const store = useInfoStore()

    assert.equal(store.debugMode, false)
    assert.deepEqual(store.branding, { name: '', logo: '', title: '', login_bg: '' })
    assert.equal('organization' in store, false)
  } finally {
    await server.close()
  }
})

test('品牌配置合并并发读取，成功缓存，失败与强制刷新可重试', async (t) => {
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom'
  })
  setActivePinia(createPinia())
  try {
    const { useInfoStore } = await server.ssrLoadModule('/src/modules/settings/model/info.js')
    const { brandApi } = await server.ssrLoadModule('/src/apis/system_api.js')
    const store = useInfoStore()
    const pending = []
    t.mock.method(brandApi, 'getInfoConfig', () => new Promise((resolve) => pending.push(resolve)))
    const first = store.loadInfoConfig()
    const second = store.loadInfoConfig()
    assert.equal(pending.length, 1)
    const data = { branding: { name: 'Test', logo: '/test.svg', title: 'Test title', login_bg: '/test.jpg' } }
    pending[0]({ success: true, data })
    assert.deepEqual(await first, data)
    assert.deepEqual(await second, data)
    assert.deepEqual(store.branding, data.branding)
    await store.loadInfoConfig()
    assert.equal(pending.length, 1)
    const forced = store.loadInfoConfig(true)
    assert.equal(pending.length, 2)
    pending[1]({ success: false })
    assert.equal(await forced, null)
    const retry = store.loadInfoConfig(true)
    assert.equal(pending.length, 3)
    pending[2]({ success: true, data: { branding: { name: 'New' } } })
    await retry
    assert.equal(store.branding.name, 'New')
    assert.equal(store.isLoading, false)
  } finally {
    await server.close()
  }
})
