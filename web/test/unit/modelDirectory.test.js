import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'

test('模型目录按 spec 与唯一 model_id 解析别名，并支持失效重载', async () => {
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
    plugins: [
      {
        name: 'model-directory-requests',
        enforce: 'pre',
        load(id) {
          if (id.endsWith('/src/apis/system_api.js')) {
            return 'export const modelProviderApi = globalThis.__modelDirectoryApi'
          }
        }
      }
    ]
  })
  try {
    let calls = 0
    globalThis.__modelDirectoryApi = {
      getV2Models: async () => {
        calls += 1
        return {
          success: true,
          data: {
            alpha: {
              models: [
                { spec: 'alpha:chat', model_id: 'chat', display_name: '通用对话' },
                { spec: 'alpha:shared', model_id: 'shared', display_name: 'Alpha 共享' }
              ]
            },
            beta: {
              models: [{ spec: 'beta:shared', model_id: 'shared', display_name: 'Beta 共享' }]
            }
          }
        }
      }
    }

    const { invalidateModelDirectory, useModelDirectory } = await server.ssrLoadModule(
      '/src/composables/useModelDirectory.js'
    )
    const directory = useModelDirectory('chat')

    assert.equal(directory.resolveDisplayName({ spec: 'alpha:chat' }), '')
    const data = await directory.load()
    assert.equal(calls, 1)
    assert.deepEqual(Object.keys(data), ['alpha', 'beta'])
    assert.equal(directory.resolveDisplayName({ spec: 'alpha:chat' }), '通用对话')
    assert.equal(directory.resolveDisplayName({ modelId: 'chat' }), '通用对话')
    assert.equal(directory.resolveDisplayName({ modelId: 'shared' }), '')
    assert.equal(directory.resolveDisplayName({ spec: 'missing' }), '')

    await directory.load()
    assert.equal(calls, 1)

    invalidateModelDirectory('chat')
    await directory.load()
    assert.equal(calls, 2)
  } finally {
    await server.close()
    delete globalThis.__modelDirectoryApi
  }
})

test('失效后乱序完成的在途旧响应不回写共享目录', async () => {
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
    plugins: [
      {
        name: 'model-directory-stale',
        enforce: 'pre',
        load(id) {
          if (id.endsWith('/src/apis/system_api.js')) {
            return 'export const modelProviderApi = globalThis.__modelDirectoryApi'
          }
        }
      }
    ]
  })
  try {
    const pendingOld = {}
    const oldResponse = new Promise((resolve) => {
      pendingOld.resolve = resolve
    })
    let calls = 0
    globalThis.__modelDirectoryApi = {
      getV2Models: () => {
        calls += 1
        if (calls === 1) return oldResponse
        return Promise.resolve({
          success: true,
          data: { alpha: { models: [{ spec: 'alpha:chat', model_id: 'chat', display_name: '新别名' }] } }
        })
      }
    }

    const { invalidateModelDirectory, useModelDirectory } = await server.ssrLoadModule(
      '/src/composables/useModelDirectory.js'
    )
    const directory = useModelDirectory('chat')

    const firstLoad = directory.load()
    invalidateModelDirectory('chat')
    const second = await directory.load()
    assert.equal(second['alpha'].models[0].display_name, '新别名')

    pendingOld.resolve({
      success: true,
      data: { alpha: { models: [{ spec: 'alpha:chat', model_id: 'chat', display_name: '旧别名' }] } }
    })
    const staleResolved = await firstLoad
    assert.equal(staleResolved['alpha'].models[0].display_name, '新别名')
    assert.equal(directory.resolveDisplayName({ spec: 'alpha:chat' }), '新别名')
    assert.equal(calls, 2)
  } finally {
    await server.close()
    delete globalThis.__modelDirectoryApi
  }
})
