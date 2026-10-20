import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import test from 'node:test'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { createTestServer } from '../helpers/createTestServer.js'

const storageValues = new Map()
globalThis.localStorage = {
  getItem: (key) => storageValues.get(key) ?? null,
  setItem: (key, value) => storageValues.set(key, String(value)),
  removeItem: (key) => storageValues.delete(key),
  clear: () => storageValues.clear()
}

async function collectSourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) files.push(...(await collectSourceFiles(path)))
    else if (/\.(js|vue)$/.test(entry.name)) files.push(path)
  }
  return files
}

test('超级管理员 API 无权限时 fail-closed 且不发起请求', async () => {
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    ssr: { noExternal: ['ant-design-vue'] },
    plugins: [
      {
        name: 'test-message-api',
        enforce: 'pre',
        resolveId(id) {
          return id === 'ant-design-vue' ? '\0test-message-api' : null
        },
        load(id) {
          if (id !== '\0test-message-api') return null
          return 'export const message = { error() {} }'
        }
      }
    ]
  })
  const pinia = createPinia()
  const originalFetch = globalThis.fetch
  let fetchCalls = 0
  globalThis.fetch = async () => {
    fetchCalls += 1
    throw new Error('不应发送超级管理员请求')
  }
  setActivePinia(pinia)

  try {
    const { useUserStore } = await server.ssrLoadModule('/src/modules/identity/model/user.js')
    const { apiSuperAdminGet } = await server.ssrLoadModule('/src/apis/base.js')
    useUserStore().userRole = 'admin'

    assert.throws(() => apiSuperAdminGet('/api/super-admin-only'), {
      message: '需要超级管理员权限'
    })
    assert.equal(fetchCalls, 0)
  } finally {
    globalThis.fetch = originalFetch
    disposePinia(pinia)
    await server.close()
  }
})

test('user_token 的持久化写入只有 identity Store 拥有', async () => {
  const sourceFiles = await collectSourceFiles(new URL('../../src', import.meta.url).pathname)
  const writers = []
  for (const path of sourceFiles) {
    const source = await readFile(path, 'utf8')
    if (/localStorage\.setItem\(['"]user_token['"]/.test(source)) writers.push(path)
  }

  assert.deepEqual(
    writers,
    [new URL('../../src/modules/identity/model/user.js', import.meta.url).pathname]
  )
})

test('API 层不直接导入 identity，HTTP 与 SSE 共用认证上下文', async () => {
  const apiDirectory = new URL('../../src/apis', import.meta.url).pathname
  const sourceFiles = await collectSourceFiles(apiDirectory)
  const forbiddenImports = []
  for (const path of sourceFiles) {
    const source = await readFile(path, 'utf8')
    if (/from ['"](?:@\/)?(?:\.\.\/)*modules\/identity/.test(source)) {
      forbiddenImports.push(path)
    }
  }

  assert.deepEqual(forbiddenImports, [])
  const agentApi = await readFile(new URL('../../src/apis/agent_api.js', import.meta.url), 'utf8')
  assert.equal(agentApi.includes("getApiAuthHeaders"), true)
  assert.equal(agentApi.includes("useUserStore"), false)
})
