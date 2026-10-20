import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createServer } from 'vite'

let server, createSessionRouteCache
before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false } })
  ;({ createSessionRouteCache } = await server.ssrLoadModule('/src/app/layouts/sessionRouteCache.ts'))
})
after(() => server.close())

/** 使用真实路由验证交接与会话身份隔离。 */
async function setup() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/agent', name: 'AgentComp', component: {} },
      { path: '/agent/:thread_id', name: 'AgentCompWithThreadId', component: {} },
      { path: '/workspace', component: {} }
    ]
  })
  await router.push('/agent')
  return { router, cache: createSessionRouteCache(router) }
}

test('首条发送沿用新建视图，下次新建与已有会话各自独立', async () => {
  const { router, cache } = await setup()
  const draft = cache.key(router.currentRoute.value)
  await cache.adopt('first')
  assert.equal(router.currentRoute.value.path, '/agent/first')
  assert.equal(cache.key(router.currentRoute.value), draft, '正式 URL 必须保留原视图 key')
  await router.push('/agent')
  const nextDraft = cache.key(router.currentRoute.value)
  assert.notEqual(nextDraft, draft)
  await cache.adopt('second')
  assert.equal(cache.key(router.currentRoute.value), nextDraft)
  await router.push('/agent/first')
  assert.equal(cache.key(router.currentRoute.value), draft)
  await router.push('/agent/existing')
  assert.equal(cache.key(router.currentRoute.value), '/agent/existing')
  await router.push('/workspace')
  assert.equal(cache.key(router.currentRoute.value), '/workspace')
})

test('导航取消或抛错保留新建身份，不让目标会话占用该视图', async () => {
  for (const throws of [false, true]) {
    const { router, cache } = await setup()
    router.onError(() => {})
    const draft = cache.key(router.currentRoute.value)
    const remove = router.beforeEach(() => {
      if (throws) throw new Error('navigation failed')
      return false
    })
    if (throws) await assert.rejects(cache.adopt('cancelled'), /navigation failed/)
    else await cache.adopt('cancelled')
    assert.equal(cache.key(router.currentRoute.value), draft)
    remove()
    await router.push('/workspace')
    await router.push('/agent/cancelled')
    assert.equal(cache.key(router.currentRoute.value), '/agent/cancelled')
  }
})

test('已离开新建页的迟到交接不改变当前路由和身份', async () => {
  const { router, cache } = await setup()
  await router.push('/agent/existing')
  await cache.adopt('late')
  assert.equal(router.currentRoute.value.path, '/agent/existing')
  assert.equal(cache.key(router.currentRoute.value), '/agent/existing')
})

test('导航被守卫重定向时不把目标会话登记为已交接', async () => {
  const { router, cache } = await setup()
  const draft = cache.key(router.currentRoute.value)
  const remove = router.beforeEach((to) => to.name === 'AgentCompWithThreadId' ? '/workspace' : undefined)
  await cache.adopt('redirected')
  assert.equal(router.currentRoute.value.path, '/workspace')
  remove()
  await router.push('/agent')
  assert.equal(cache.key(router.currentRoute.value), draft)
  await router.push('/agent/redirected')
  assert.equal(cache.key(router.currentRoute.value), '/agent/redirected')
})

for (const successorFirst of [true, false]) {
test(`同目标后继导航${successorFirst ? '先' : '后'}完成都保留交接身份，并分配独立新建页`, async () => {
  const { router, cache } = await setup()
  const draft = cache.key(router.currentRoute.value)
  let release, enter, releaseSuccessor, enterSuccessor
  const waiting = new Promise((resolve) => { release = resolve })
  const entered = new Promise((resolve) => { enter = resolve })
  const successorWaiting = new Promise((resolve) => { releaseSuccessor = resolve })
  const successorEntered = new Promise((resolve) => { enterSuccessor = resolve })
  let first = true
  router.beforeEach(() => {
    if (!first) {
      enterSuccessor()
      return successorWaiting
    }
    first = false
    enter()
    return waiting
  })
  const adoption = cache.adopt('same')
  await entered
  const successor = router.push('/agent/same')
  await successorEntered
  if (successorFirst) {
    releaseSuccessor()
    await successor
    assert.equal(cache.key(router.currentRoute.value), draft)
    release()
    await adoption
  } else {
    release()
    await adoption
    assert.equal(router.currentRoute.value.path, '/agent')
    releaseSuccessor()
    await successor
  }
  assert.equal(cache.key(router.currentRoute.value), draft, '原导航取消不能撤销已经显示的视图身份')
  await router.push('/agent')
  assert.notEqual(cache.key(router.currentRoute.value), draft)
})
}
