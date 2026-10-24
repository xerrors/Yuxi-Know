import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'

test('消息引用栏按目录唯一别名展示模型名，歧义或失败时回退原始名称', async (t) => {
  const previousStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null, setItem() {} }
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
    plugins: [
      {
        name: 'refs-model-alias',
        enforce: 'pre',
        load(id) {
          if (id.endsWith('/src/apis/system_api.js')) {
            return 'export const modelProviderApi = globalThis.__refsApi'
          }
        }
      }
    ]
  })
  try {
    let directoryHandler = async () => ({ success: true, data: {} })
    globalThis.__refsApi = { getV2Models: () => directoryHandler() }
    const { invalidateModelDirectory } = await server.ssrLoadModule('/src/composables/useModelDirectory.js')
    const { default: RefsComponent } = await server.ssrLoadModule('/src/components/RefsComponent.vue')

    const mount = async (modelName) => {
      let component
      await renderToString(
        createSSRApp({
          setup() {
            component = RefsComponent.setup(
              { message: { status: 'finished', response_metadata: { model_name: modelName } }, showRefs: ['model'] },
              { expose() {}, emit() {} }
            )
            return () => h('div')
          }
        })
      )
      await new Promise((resolve) => setTimeout(resolve, 0))
      return component
    }

    await t.test('model_id 唯一命中时展示别名', async () => {
      directoryHandler = async () => ({
        success: true,
        data: { alpha: { models: [{ spec: 'alpha:chat', model_id: 'chat', display_name: 'Alpha 助手' }] } }
      })
      const component = await mount('chat')
      assert.equal(component.displayModelName.value, 'Alpha 助手')
    })

    await t.test('跨供应商同名 model_id 保留原始名称', async () => {
      directoryHandler = async () => ({
        success: true,
        data: {
          alpha: { models: [{ spec: 'alpha:shared', model_id: 'shared', display_name: 'Alpha 共享' }] },
          beta: { models: [{ spec: 'beta:shared', model_id: 'shared', display_name: 'Beta 共享' }] }
        }
      })
      invalidateModelDirectory('chat')
      const component = await mount('shared')
      assert.equal(component.displayModelName.value, 'shared')
    })

    await t.test('目录请求失败时回退原始名称', async () => {
      directoryHandler = async () => {
        throw new Error('directory unavailable')
      }
      invalidateModelDirectory('chat')
      const component = await mount('chat')
      assert.equal(component.displayModelName.value, 'chat')
    })
  } finally {
    await server.close()
    delete globalThis.__refsApi
    if (previousStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = previousStorage
  }
})
