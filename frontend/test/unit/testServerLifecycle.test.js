import assert from 'node:assert/strict'
import { access } from 'node:fs/promises'
import { setTimeout } from 'node:timers/promises'
import test from 'node:test'
import { createTestServer } from '../helpers/createTestServer.js'

test('SSR 测试保留真实依赖和 Vue 编译，关闭后缓存不被客户端预构建重新创建', async (t) => {
  const originalStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
  t.after(() => {
    if (originalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalStorage
  })
  const server = await createTestServer({ server: { middlewareMode: true, hmr: false } })
  const cacheDir = server.config.cacheDir
  try {
    assert.equal(server.environments.client.depsOptimizer, undefined)
    const { formatFullDateTime } = await server.ssrLoadModule('/src/shared/lib/time.js')
    assert.equal(formatFullDateTime('2026-10-21T00:00:00Z'), '2026-10-21 08:00:00')
    const { default: modal } = await server.ssrLoadModule('/src/modules/knowledge/ui/FileUploadModal.vue')
    assert.equal(typeof modal.setup, 'function')
    await access(cacheDir)
  } finally {
    await server.close()
  }
  await assert.rejects(access(cacheDir), { code: 'ENOENT' })
  // 超过客户端优化器的 100ms debounce，验证关闭后的临时目录仍不存在。
  await setTimeout(300)
  await assert.rejects(access(cacheDir), { code: 'ENOENT' })
})


for (const phase of ['configureServer', 'buildStart']) {
  test(`${phase} 失败关闭已创建的 watcher 并回收独占缓存`, async () => {
    const failure = new Error('test server initialization failed')
    let created
    try {
      await assert.rejects(
        createTestServer({
          server: { middlewareMode: true, hmr: false },
          plugins: [{
            name: 'fail-test-server-initialization',
            configureServer(server) {
              created = server
              if (phase === 'configureServer') throw failure
            },
            buildStart() { throw failure }
          }]
        }),
        (error) => error === failure
      )
      assert.ok(created, '失败发生在真实 Vite server 创建之后')
      assert.equal(created.watcher.closed, true)
      await assert.rejects(access(created.config.cacheDir), { code: 'ENOENT' })
    } finally {
      await created?.close()
    }
  })
}

test('配置解析失败仍回收自己创建的缓存', async () => {
  const failure = new Error('test config resolution failed')
  let cacheDir
  await assert.rejects(
    createTestServer({
      plugins: [{
        name: 'fail-test-config',
        configResolved(config) {
          cacheDir = config.cacheDir
          throw failure
        }
      }]
    }),
    (error) => error === failure
  )
  assert.ok(cacheDir)
  await assert.rejects(access(cacheDir), { code: 'ENOENT' })
})

test('关闭报错仍回收缓存，重复关闭不留资源', async () => {
  const failure = new Error('test close failed')
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    plugins: [{
      name: 'fail-after-test-server-close',
      configureServer(created) {
        const close = created.close.bind(created)
        created.close = async () => {
          await close()
          throw failure
        }
      }
    }]
  })
  for (let attempt = 0; attempt < 2; attempt++) {
    await assert.rejects(server.close(), (error) => error === failure)
    assert.equal(server.watcher.closed, true)
    await assert.rejects(access(server.config.cacheDir), { code: 'ENOENT' })
  }
})
