import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createServer } from 'vite'
import { createPinia, disposePinia, setActivePinia } from 'pinia'

let server, api, useStore
before(async () => {
  globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
  server = await createServer({ server: { middlewareMode: true, hmr: false } })
  ;({ agentApi: api } = await server.ssrLoadModule('/src/apis/index.js'))
  ;({ useSessionFeedbackStore: useStore } = await server.ssrLoadModule('/src/modules/session/model/sessionFeedback.js'))
})
after(async () => {
  await server?.close()
  delete globalThis.localStorage
})

function setup(t) {
  const pinia = createPinia()
  setActivePinia(pinia)
  t.after(() => disposePinia(pinia))
  return useStore()
}

test('当前消息页批量恢复评价，未知目标保持无评价', async (t) => {
  const store = setup(t)
  const batches = []
  t.mock.method(api, 'getSessionFeedback', async (_thread, ids) => {
    batches.push(ids)
    return { items: ids.includes('r1') ? [{ id: 'saved', run_id: 'r1', rating: 'dislike', reason: '需要改进' }] : [] }
  })
  const ids = Array.from({ length: 101 }, (_, index) => `r${index}`)
  await Promise.all([store.load('thread', ids), store.load('thread', ids)])
  assert.deepEqual(batches.map((batch) => batch.length), [100, 1])
  assert.equal(store.getEntry('thread', 'r1').record.rating, 'dislike')
  assert.equal(store.getEntry('thread', 'r1').draft, '需要改进')
  assert.equal(store.getEntry('thread', 'r0').record, null)
  assert.equal(store.getEntry('thread', 'r0').loaded, true)
})

test('保存前不显示成功，单个目标阻止并发操作', async (t) => {
  const store = setup(t), entry = store.getEntry('thread', 'run')
  entry.loaded = true
  let complete, requests = 0
  t.mock.method(api, 'putUserFeedback', () => {
    requests++
    return new Promise((resolve) => { complete = resolve })
  })
  const pending = store.rate('thread', 'turn', 'run', 'like')
  assert.equal(entry.pending, true)
  assert.equal(entry.record, null)
  await store.rate('thread', 'turn', 'run', 'dislike')
  assert.equal(requests, 1)
  complete({ id: 'saved', rating: 'like', reason: null })
  await pending
  assert.equal(entry.record.rating, 'like')
  assert.equal(entry.pending, false)
})

test('编辑失败保留草稿和原评价，重试按服务端返回裁剪值更新', async (t) => {
  const store = setup(t), entry = store.getEntry('thread', 'run')
  Object.assign(entry, { loaded: true, record: { id: 'saved', rating: 'dislike', reason: '旧说明' }, draft: '  新说明  ', editing: true })
  t.mock.method(api, 'putUserFeedback', async () => { throw new Error('写入失败') })
  await store.saveReason('thread', 'turn', 'run')
  assert.equal(entry.record.reason, '旧说明')
  assert.equal(entry.draft, '  新说明  ')
  assert.equal(entry.editing, true)
  assert.equal(entry.error, '写入失败')
  t.mock.method(api, 'putUserFeedback', async () => ({ id: 'saved', rating: 'dislike', reason: '新说明' }))
  await store.saveReason('thread', 'turn', 'run')
  assert.equal(entry.draft, '新说明')
  assert.equal(entry.error, '')
})

test('切换评价清空说明，重复选中撤销；撤销失败保留记录', async (t) => {
  const store = setup(t), entry = store.getEntry('thread', 'run')
  Object.assign(entry, { loaded: true, record: { rating: 'dislike', reason: '负面原因' }, draft: '负面原因' })
  t.mock.method(api, 'putUserFeedback', async (_thread, _turn, body) => {
    assert.equal(body.reason, null)
    return { id: 'saved', ...body }
  })
  await store.rate('thread', 'turn', 'run', 'like')
  assert.equal(entry.draft, '')
  t.mock.method(api, 'deleteUserFeedback', async () => { throw new Error('撤销失败') })
  await store.rate('thread', 'turn', 'run', 'like')
  assert.equal(entry.record.rating, 'like')
  t.mock.method(api, 'deleteUserFeedback', async () => {})
  await store.rate('thread', 'turn', 'run', 'like')
  assert.equal(entry.record, null)
})

test('空说明可以提交，关闭弹窗后刷新保留未保存草稿', async (t) => {
  const store = setup(t), entry = store.getEntry('thread', 'run')
  Object.assign(entry, { loaded: true, record: { id: 'saved', run_id: 'run', rating: 'like', reason: '旧说明' }, draft: '', editing: true })
  t.mock.method(api, 'putUserFeedback', async (_thread, _turn, body) => {
    assert.equal(body.rating, 'like')
    assert.equal(body.reason, '')
    return { id: 'saved', run_id: 'run', rating: 'like', reason: null }
  })
  await store.saveReason('thread', 'turn', 'run')
  assert.equal(entry.record.reason, null)
  assert.equal(entry.editing, false)
  entry.draft = '未提交的具体建议'
  t.mock.method(api, 'getSessionFeedback', async () => ({ items: [{ id: 'saved', run_id: 'run', rating: 'like', reason: null }] }))
  await store.load('thread', ['run'], true)
  assert.equal(entry.draft, '未提交的具体建议')
  assert.equal(entry.record.reason, null)
})

test('迟到读取不能覆盖已成功保存的新评价', async (t) => {
  const store = setup(t), entry = store.getEntry('thread', 'run')
  entry.loaded = true
  let release
  t.mock.method(api, 'getSessionFeedback', () => new Promise((resolve) => { release = resolve }))
  const reading = store.load('thread', ['run'], true)
  t.mock.method(api, 'putUserFeedback', async () => ({ id: 'new', rating: 'like' }))
  await store.rate('thread', 'turn', 'run', 'like')
  release({ items: [{ id: 'old', run_id: 'run', rating: 'dislike' }] })
  await reading
  assert.equal(entry.record.id, 'new')
})

test('保存期间启动的读取不能覆盖新评价，其他目标仍能恢复', async (t) => {
  const store = setup(t), entry = store.getEntry('thread', 'run')
  Object.assign(entry, { loaded: true, record: { id: 'old', rating: 'dislike' } })
  let finishWrite, finishRead
  t.mock.method(api, 'putUserFeedback', () => new Promise((resolve) => { finishWrite = resolve }))
  t.mock.method(api, 'getSessionFeedback', () => new Promise((resolve) => { finishRead = resolve }))
  const writing = store.rate('thread', 'turn', 'run', 'like')
  const reading = store.load('thread', ['run', 'other'], true)
  finishWrite({ id: 'new', rating: 'like', reason: null })
  await writing
  finishRead({ items: [
    { id: 'old', run_id: 'run', rating: 'dislike' },
    { id: 'other-saved', run_id: 'other', rating: 'like' }
  ] })
  await reading
  assert.equal(entry.record.id, 'new')
  assert.equal(entry.record.rating, 'like')
  assert.equal(store.getEntry('thread', 'other').record.id, 'other-saved')
})

test('读取失败不伪装成无评价，切换账号后旧响应不能恢复缓存', async (t) => {
  const store = setup(t)
  t.mock.method(api, 'getSessionFeedback', async () => { throw new Error('读取失败') })
  await store.load('thread', ['run'])
  assert.equal(store.getEntry('thread', 'run').loaded, false)
  let release
  t.mock.method(api, 'getSessionFeedback', () => new Promise((resolve) => { release = resolve }))
  const reading = store.load('thread', ['run'])
  store.reset()
  release({ items: [{ id: 'old-account', run_id: 'run', rating: 'like' }] })
  await reading
  assert.equal(store.getEntry('thread', 'run').record, null)
  assert.equal(store.getEntry('thread', 'run').loaded, false)
})

test('预设原因与文字一次提交，失败后保留原文字供重试', async (t) => {
  const store = setup(t), entry = store.getEntry('thread', 'run')
  Object.assign(entry, { loaded: true, record: { rating: 'like', reason: null }, draft: '具体步骤有帮助', editing: true })
  const combined = '解决了我的问题；内容准确清晰\n\n具体步骤有帮助'
  t.mock.method(api, 'putUserFeedback', async (_thread, _turn, body) => {
    assert.equal(body.reason, combined)
    throw new Error('写入失败')
  })
  await store.saveReason('thread', 'turn', 'run', combined)
  assert.equal(entry.draft, '具体步骤有帮助')
  assert.equal(entry.record.reason, null)
  assert.equal(entry.editing, true)
  t.mock.method(api, 'putUserFeedback', async (_thread, _turn, body) => ({ id: 'saved', ...body }))
  await store.saveReason('thread', 'turn', 'run', combined)
  assert.equal(entry.record.reason, combined)
  assert.equal(entry.editing, false)
})
