import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { ref } from 'vue'
import { compileScript, parse } from 'vue/compiler-sfc'

const source = readFileSync(
  new URL('../../src/pages/OIDCCallbackView.vue', import.meta.url),
  'utf8'
)
const { descriptor } = parse(source)
const compiled = compileScript(descriptor, { id: 'oidc-callback' })
const executable = compiled.content
  .replace(/^import[\s\S]*?from '[^']+'\n/gm, '')
  .replace('export default', 'return')

/** 驱动真实页面逻辑，控制兑换响应到达时序。 */
function setup({ token = '', redirect = '/workspace' } = {}) {
  const hooks = {}
  const navigations = []
  const applied = []
  let resolveExchange
  const pending = new Promise((resolve) => {
    resolveExchange = resolve
  })
  let calls = 0
  const user = { token, applySession: (response) => applied.push(response) }
  const storage = new Map([['oidc_redirect', redirect]])
  const deps = {
    ref,
    onMounted: (fn) => {
      hooks.mounted = fn
    },
    onUnmounted: (fn) => {
      hooks.unmounted = fn
    },
    useRouter: () => ({ replace: async (target) => navigations.push(target) }),
    useRoute: () => ({ path: '/auth/oidc/callback', query: { code: 'private-result' } }),
    useUserStore: () => user,
    authApi: {
      exchangeOIDCCode: () => {
        calls++
        return pending
      }
    },
    clearAutoStartAttempt() {},
    sessionStorage: { getItem: (key) => storage.get(key), removeItem: (key) => storage.delete(key) }
  }
  const component = new Function(...Object.keys(deps), executable)(...Object.values(deps))
  component.setup({}, { expose() {} })
  return { hooks, navigations, applied, user, resolveExchange, calls: () => calls }
}

test('回调先清 URL，兑换成功后只跳站内目标', async () => {
  for (const redirect of [
    '/workspace',
    '//attacker.example',
    '/\\attacker.example',
    '/\n/attacker.example'
  ]) {
    const fixture = setup({ redirect })
    const done = fixture.hooks.mounted()
    await Promise.resolve()
    assert.deepEqual(fixture.navigations, [{ path: '/auth/oidc/callback', query: {} }])
    assert.equal(fixture.calls(), 1)
    fixture.resolveExchange({ access_token: 'session' })
    await done
    assert.deepEqual(fixture.applied, [{ access_token: 'session' }])
    assert.equal(fixture.navigations.at(-1), redirect === '/workspace' ? '/workspace' : '/agent')
  }
})

test('离页或切换账号后的迟到兑换响应不能覆盖当前会话', async () => {
  for (const change of ['unmount', 'switch']) {
    const fixture = setup()
    const done = fixture.hooks.mounted()
    await Promise.resolve()
    if (change === 'unmount') fixture.hooks.unmounted()
    else fixture.user.token = 'newer-session'
    fixture.resolveExchange({ access_token: 'stale-session' })
    await done
    assert.deepEqual(fixture.applied, [])
    assert.equal(fixture.navigations.length, 1)
  }
})

test('已经登录的浏览器清掉回调凭据且不重新兑换', async () => {
  const fixture = setup({ token: 'existing' })
  await fixture.hooks.mounted()
  assert.equal(fixture.calls(), 0)
  assert.deepEqual(fixture.applied, [])
  assert.equal(fixture.navigations.at(-1), '/agent')
})
