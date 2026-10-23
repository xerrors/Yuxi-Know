import assert from 'node:assert/strict'
import test from 'node:test'
import { createTestServer } from '../helpers/createTestServer.js'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'

/** 提供可控的慢请求，验证真实组件的可观察状态。 */
function deferred() {
  let resolve
  let reject
  const promise = new Promise((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

const models = { fixture: { models: [{ spec: 'fixture:chat', display_name: '测试模型' }] } }

test('模型弹层的加载、关闭和失败重试', async (t) => {
  const previousStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null, setItem() {} }
  const server = await createTestServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
    plugins: [
      {
        name: 'model-selector-requests',
        enforce: 'pre',
        load(id) {
          if (id.endsWith('/src/apis/system_api.js'))
            return 'export const modelProviderApi = globalThis.__modelSelectorApi'
          if (id.endsWith('/src/modules/identity/model/user.js'))
            return 'export const useUserStore = () => ({ isAdmin: false })'
          if (id.endsWith('/src/modules/settings/model/modelMetadata.js'))
            return `
          export const loadModelMetadataCatalog = () => globalThis.__modelSelectorCatalog.promise
          export const resolveModelDisplayMetadata = () => ({ matched: false })`
        }
      }
    ]
  })
  try {
    let request
    let requestedType
    globalThis.__modelSelectorApi = {
      getV2Models: (type) => {
        requestedType = type
        return request.promise
      },
      refreshModelCache: async () => ({ success: true })
    }
    const { default: ModelSelector } = await server.ssrLoadModule(
      '/src/modules/agents/ui/ModelSelectorComponent.vue'
    )
    const setup = async (overrides = {}) => {
      let component
      await renderToString(
        createSSRApp({
          setup() {
            component = ModelSelector.setup(
              { disabled: false, size: 'nano', model_spec: '', modelType: 'chat', ...overrides },
              { expose() {}, emit() {} }
            )
            return () => h('div')
          }
        })
      )
      return component
    }

    await t.test(
      '未完成请求时立即展开，关闭后完成请求也不重新打开',
      { timeout: 2000 },
      async () => {
        request = deferred()
        globalThis.__modelSelectorCatalog = deferred()
        const component = await setup()
        component.handleOpenChange(true)
        assert.equal(component.dropdownOpen.value, true)
        assert.equal(component.loadingV2Models.value, true)
        component.handleOpenChange(false)
        request.resolve({ success: true, data: models })
        await component.fetchV2Models()
        assert.equal(component.dropdownOpen.value, false)
        assert.equal(component.loadingV2Models.value, false)
        assert.deepEqual(component.v2Models.value, models)
      }
    )

    await t.test('目录先显示，不等待可选元数据', { timeout: 2000 }, async () => {
      request = deferred()
      globalThis.__modelSelectorCatalog = deferred()
      const component = await setup()
      component.handleOpenChange(true)
      request.resolve({ success: true, data: models })
      await component.fetchV2Models()
      assert.equal(component.loadingV2Models.value, false)
      assert.equal(component.hasFilteredModels.value, true)
      assert.equal(component.dropdownOpen.value, true)
    })

    await t.test('请求失败保留展开并提供错误，重试成功清除错误', { timeout: 2000 }, async () => {
      request = deferred()
      globalThis.__modelSelectorCatalog = deferred()
      const component = await setup()
      component.handleOpenChange(true)
      request.reject(new Error('fixture unavailable'))
      await component.fetchV2Models()
      assert.equal(component.dropdownOpen.value, true)
      assert.equal(component.loadingV2Models.value, false)
      assert.ok(component.modelsError.value)
      request = deferred()
      const retry = component.fetchV2Models()
      request.resolve({ success: true, data: models })
      await retry
      assert.equal(component.modelsError.value, '')
      assert.deepEqual(component.v2Models.value, models)
    })
    await t.test('Embedding 和 Re-ranker 只展示各自目录，禁用时不打开', async () => {
      for (const modelType of ['embedding', 'rerank']) {
        request = deferred()
        const component = await setup({ modelType })
        component.handleOpenChange(true)
        request.resolve({ success: true, data: models })
        await component.fetchV2Models()
        assert.equal(requestedType, modelType)
        assert.deepEqual(component.v2Models.value, models)
        const disabled = await setup({ modelType, disabled: true })
        disabled.handleOpenChange(true)
        assert.equal(disabled.dropdownOpen.value, false)
        assert.equal(disabled.loadingV2Models.value, false)
      }
    })
    await t.test('表单包装器保留 update:value 与 change 的选择结果', async () => {
      for (const name of ['EmbeddingModelSelector', 'RerankModelSelector']) {
        const { default: Wrapper } = await server.ssrLoadModule(`/src/modules/settings/ui/${name}.vue`)
        const events = []
        let component
        await renderToString(
          createSSRApp({
            setup() {
              component = Wrapper.setup({}, { expose() {}, emit: (...event) => events.push(event) })
              return () => h('div')
            }
          })
        )
        component.handleSelect('fixture:selected')
        assert.deepEqual(events, [
          ['update:value', 'fixture:selected'],
          ['change', 'fixture:selected']
        ])
      }
    })

    await t.test('检查结果替换原文字，通过和异常都能再次检查', async () => {
      const component = await setup({ size: 'small', model_spec: 'fixture:chat' })
      let statusRequest
      globalThis.__modelSelectorApi.getModelStatusBySpec = () => statusRequest.promise
      assert.equal(component.modelCheckLabel.value, '检查')
      for (const status of ['available', 'unavailable', 'available']) {
        statusRequest = deferred()
        const pending = component.checkCurrentModelStatus()
        assert.equal(component.state.checkingStatus, true)
        statusRequest.resolve({ data: { status, message: '测试结果' } })
        await pending
        assert.equal(component.state.checkingStatus, false)
        assert.equal(component.modelCheckLabel.value, status === 'available' ? '通过' : '异常')
        assert.match(component.getCurrentModelStatusTitle(), /测试结果；点击重新检查/)
      }
    })

    await t.test('检查中重复调用不产生第二个请求，完成后允许重试', async () => {
      const component = await setup({ model_spec: 'fixture:chat' })
      const statusRequest = deferred()
      let requests = 0
      globalThis.__modelSelectorApi.getModelStatusBySpec = () => {
        requests += 1
        return statusRequest.promise
      }
      const pending = component.checkCurrentModelStatus()
      await component.checkCurrentModelStatus()
      assert.equal(requests, 1)
      assert.equal(component.state.currentModelStatus, null)
      statusRequest.resolve({ data: { status: 'available' } })
      await pending
      await component.checkCurrentModelStatus()
      assert.equal(requests, 2)
      assert.equal(component.modelCheckLabel.value, '通过')
    })

    await t.test('请求异常显示异常并保留详情，再次检查可以恢复通过', async () => {
      const component = await setup({ model_spec: 'fixture:chat' })
      globalThis.__modelSelectorApi.getModelStatusBySpec = async () => { throw new Error('测试连接失败') }
      await component.checkCurrentModelStatus()
      assert.equal(component.state.checkingStatus, false)
      assert.equal(component.modelCheckLabel.value, '异常')
      assert.match(component.getCurrentModelStatusTitle(), /测试连接失败/)
      globalThis.__modelSelectorApi.getModelStatusBySpec = async () => ({ data: { status: 'available' } })
      await component.checkCurrentModelStatus()
      assert.equal(component.modelCheckLabel.value, '通过')
    })

    await t.test('切换模型后不显示前一个模型迟到的通过或异常', async () => {
      for (const fails of [false, true]) {
        const component = await setup({ model_spec: 'fixture:before' })
        const statusRequest = deferred()
        globalThis.__modelSelectorApi.getModelStatusBySpec = () => statusRequest.promise
        const pending = component.checkCurrentModelStatus()
        component.props.model_spec = 'fixture:after'
        if (fails) statusRequest.reject(new Error('前一个模型的失败'))
        else statusRequest.resolve({ data: { status: 'available' } })
        await pending
        assert.equal(component.modelCheckLabel.value, '检查')
        assert.equal(component.state.currentModelStatus, null)
        assert.equal(component.state.checkingStatus, false)
      }
    })
  } finally {
    await server.close()
    globalThis.localStorage = previousStorage
    delete globalThis.__modelSelectorApi
    delete globalThis.__modelSelectorCatalog
  }
})
