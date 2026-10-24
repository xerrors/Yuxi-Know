import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'

test('模型选择器按目录别名展示选中态，未命中或失败时回退原规则', async (t) => {
  const previousStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null, setItem() {} }
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
    plugins: [
      {
        name: 'model-selector-alias',
        enforce: 'pre',
        load(id) {
          if (id.endsWith('/src/apis/system_api.js')) {
            return 'export const modelProviderApi = globalThis.__modelSelectorApi'
          }
          if (id.endsWith('/src/stores/user.js')) {
            return 'export const useUserStore = () => ({ isAdmin: false })'
          }
          if (id.endsWith('/src/utils/modelMetadata.js')) {
            return 'export const loadModelMetadataCatalog = () => Promise.resolve({})\nexport const resolveModelDisplayMetadata = () => ({ matched: false })'
          }
        }
      }
    ]
  })
  try {
    let directoryHandler = async () => ({ success: true, data: {} })
    globalThis.__modelSelectorApi = {
      getV2Models: () => directoryHandler(),
      refreshModelCache: async () => ({ success: true })
    }
    const { invalidateModelDirectory } = await server.ssrLoadModule('/src/composables/useModelDirectory.js')
    const { default: ModelSelector } = await server.ssrLoadModule('/src/components/ModelSelectorComponent.vue')
    const setup = async (props) => {
      let component
      await renderToString(
        createSSRApp({
          setup() {
            component = ModelSelector.setup(
              { disabled: false, size: 'nano', modelType: 'chat', ...props },
              { expose() {}, emit() {} }
            )
            return () => h('div')
          }
        })
      )
      return component
    }

    await t.test('目录命中别名时选中态与标题都展示别名', async () => {
      directoryHandler = async () => ({
        success: true,
        data: { alpha: { models: [{ spec: 'alpha:chat', model_id: 'chat', display_name: 'Alpha 助手' }] } }
      })
      const component = await setup({ model_spec: 'alpha:chat', displayName: 'mini' })
      await component.syncResolvedModelAlias()
      assert.equal(component.displayModelText.value, 'Alpha 助手')
      assert.equal(component.displayModelTitle.value, 'Alpha 助手')
    })

    await t.test('目录未命中别名时回退截取名且标题保持完整 spec', async () => {
      directoryHandler = async () => ({
        success: true,
        data: { alpha: { models: [{ spec: 'alpha:other', display_name: '另一个' }] } }
      })
      invalidateModelDirectory('chat')
      const component = await setup({ model_spec: 'alpha:chat', displayName: 'mini' })
      await component.syncResolvedModelAlias()
      assert.equal(component.displayModelText.value, 'chat')
      assert.equal(component.displayModelTitle.value, 'alpha:chat')
    })

    await t.test('目录请求失败时选中态回退原规则且不抛错', async () => {
      directoryHandler = async () => {
        throw new Error('directory unavailable')
      }
      invalidateModelDirectory('chat')
      const component = await setup({ model_spec: 'alpha:chat', displayName: 'mini' })
      await component.syncResolvedModelAlias()
      assert.equal(component.resolvedModelAlias.value, '')
      assert.equal(component.displayModelText.value, 'chat')
      assert.equal(component.displayModelTitle.value, 'alpha:chat')
    })

    await t.test('慢目录返回期间切换 spec 时不回写过期别名', async () => {
      invalidateModelDirectory('chat')
      let pendingResolve
      const pending = new Promise((resolve) => {
        pendingResolve = resolve
      })
      directoryHandler = () => pending
      const rawProps = { disabled: false, size: 'nano', modelType: 'chat', model_spec: 'alpha:chat', displayName: 'short' }
      let component
      await renderToString(
        createSSRApp({
          setup() {
            component = ModelSelector.setup(rawProps, { expose() {}, emit() {} })
            return () => h('div')
          }
        })
      )
      const staleCall = component.syncResolvedModelAlias()
      rawProps.model_spec = 'beta:chat'
      pendingResolve({
        success: true,
        data: {
          alpha: { models: [{ spec: 'alpha:chat', display_name: '旧模型别名' }] },
          beta: { models: [{ spec: 'beta:chat', display_name: '新模型别名' }] }
        }
      })
      await staleCall
      assert.equal(component.resolvedModelAlias.value, '', '过期目录结果不得回写当前选中态')
      await component.syncResolvedModelAlias()
      assert.equal(component.displayModelText.value, '新模型别名')
    })
  } finally {
    await server.close()
    delete globalThis.__modelSelectorApi
    if (previousStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = previousStorage
  }
})
