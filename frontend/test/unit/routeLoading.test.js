import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { compileScript, parse } from 'vue/compiler-sfc'

/** 执行 App 脚本，通过独立路由与浏览器边界观测恢复行为。 */
function setupApp(matched = [], providedRouter = null) {
  const callbacks = {}
  const requests = []
  const router = providedRouter || {
    currentRoute: { value: { matched } },
    resolve: (to) => ({ href: `/base${to.fullPath}` }),
    beforeEach: (callback) => { callbacks.before = callback; return () => { delete callbacks.before } },
    onError: (callback) => { callbacks.error = callback; return () => { delete callbacks.error } },
    afterEach: (callback) => { callbacks.after = callback; return () => { delete callbacks.after } }
  }
  const deps = {
    ref, onUnmounted: (callback) => { callbacks.unmount = callback },
    useRouter: () => router, useThemeStore: () => ({}), setLucideProps() {},
    zhCN: {}, renderEmpty() {},
    window: { location: { assign: (href) => requests.push(href), reload: () => requests.push('reload') } }
  }
  const { descriptor } = parse(readFileSync(new URL('../../src/app/App.vue', import.meta.url), 'utf8'))
  const executable = compileScript(descriptor, { id: 'route-loading' }).content
    .replace(/^import[\s\S]*?from '[^']+'\n/gm, '').replace('export default', 'return')
  const component = new Function(...Object.keys(deps), executable)(...Object.values(deps))
  return { state: component.setup({}, { expose() {} }), callbacks, requests }
}

test('首屏长等待提供恢复入口，等待不伪装成失败，成功后停止提醒', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const { state, callbacks, requests } = setupApp()
  assert.equal(state.loadingTooLong.value, false)
  t.mock.timers.tick(10000)
  assert.equal(state.loadingTooLong.value, true)
  assert.equal(state.failedRoute.value, null)
  assert.deepEqual(requests, [])
  state.reloadPage()
  assert.deepEqual(requests, ['reload'])
  callbacks.after({}, {}, undefined)
  assert.equal(state.loadingTooLong.value, false)
  callbacks.unmount()
})

test('路由失败后重新加载失败目标及 base 路径，成功导航清除错误', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const { state, callbacks, requests } = setupApp([{}])
  callbacks.error(new Error('private module diagnostic'), { fullPath: '/extensions?tab=knowledge' })
  state.reloadPage()
  assert.deepEqual(requests, ['/base/extensions?tab=knowledge'])
  callbacks.after({}, {}, new Error('cancelled'))
  assert.equal(state.failedRoute.value, '/base/extensions?tab=knowledge')
  callbacks.after({}, {}, undefined)
  assert.equal(state.failedRoute.value, null)
  t.mock.timers.tick(10000)
  assert.equal(state.loadingTooLong.value, false)
  callbacks.unmount()
})

test('首屏快速完成和 App 卸载后都不会出现迟到的长等待提醒', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const ready = setupApp([{}])
  t.mock.timers.tick(10000)
  assert.equal(ready.state.loadingTooLong.value, false)
  ready.callbacks.unmount()
  for (const complete of ['after', 'unmount']) {
    const { state, callbacks } = setupApp()
    if (complete === 'after') callbacks.after({}, {}, undefined)
    else callbacks.unmount()
    t.mock.timers.tick(10000)
    assert.equal(state.loadingTooLong.value, false)
    if (complete === 'after') callbacks.unmount()
    assert.equal(callbacks.before, undefined)
    assert.equal(callbacks.error, undefined)
    assert.equal(callbacks.after, undefined)
  }
})

test('真实路由已完成新导航后，旧模块迟到失败不显示错误或覆盖重试目标', async () => {
  let rejectOldModule
  let markStarted
  const started = new Promise((resolve) => { markStarted = resolve })
  const router = createRouter({
    history: createMemoryHistory('/base/'),
    routes: [
      { path: '/login', component: { render: () => null } },
      { path: '/next', component: { render: () => null } },
      { path: '/slow', component: () => {
        markStarted()
        return new Promise((_resolve, reject) => { rejectOldModule = reject })
      } }
    ]
  })
  await router.push('/login')
  const { state, callbacks } = setupApp([], router)
  const pending = router.push('/slow').catch((error) => error)
  await started
  await router.push('/next')
  rejectOldModule(new Error('old module failed'))
  await pending
  assert.equal(router.currentRoute.value.fullPath, '/next')
  assert.equal(state.failedRoute.value, null, '旧导航错误不得出现在已成功的新页面上')
  callbacks.unmount()
})
