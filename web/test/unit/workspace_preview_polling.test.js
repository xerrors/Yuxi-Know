import { setImmediate } from 'node:timers'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import test from 'node:test'
import { ref } from 'vue'

const source = readFileSync(new URL('../../src/views/WorkspaceView.vue', import.meta.url), 'utf8')
const helpers = source.slice(source.indexOf('const startPreviewRequest ='), source.indexOf('const loadWorkspacePreview ='))
const polling = source.slice(source.indexOf('const loadKnowledgePreview ='), source.indexOf('const syncSelectedPaths ='))
const closing = source.slice(source.indexOf('const closePreview ='), source.indexOf('const handleSavePreviewFile ='))
const lifecycle = source.slice(source.indexOf('onDeactivated(() =>'), source.indexOf('watch(useInlinePreview'))
const entry = { source: 'knowledge', kb_id: 'kb_1', file_id: 'file_1', path: '/knowledge/file_1' }

/** 执行真实预览函数和请求隔离逻辑，只替换网络与时间边界。 */
function setup(responses) {
  const timers = []
  const calls = []
  const errors = []
  const hooks = {}
  const state = { previewRequestId: ref(0), selectedEntry: ref(null), previewFile: ref(null),
    inlinePreviewVisible: ref(false), previewModalVisible: ref(false), useInlinePreview: ref(true),
    loadingPreview: ref(false), previewObjectUrl: ref('') }
  const context = { ...state, workspaceResizeObserver: null, stopPreviewResize() {},
    onDeactivated: (handler) => { hooks.deactivated = handler }, onUnmounted: (handler) => { hooks.unmounted = handler }, buildPreviewLoadingFile: (item) => ({ ...item, status: 'loading' }),
    buildPreviewErrorFile: (item, error) => ({ ...item, status: 'error', message: error.message }),
    revokePreviewObjectUrl() {}, window: { URL: { revokeObjectURL() {} }, setTimeout: (callback) => timers.push(callback) },
    message: { error: (value) => errors.push(value) }, console: { warn() {} },
    KNOWLEDGE_PREVIEW_LOAD_MESSAGES: { log: '预览失败', resolveUserMessage: (error) => error.message },
    getWorkspaceKnowledgeFileContent: async (kbId, fileId) => { calls.push([kbId, fileId]); return await responses.shift() },
    normalizePreviewFile: async (item, response) => ({ ...item, ...response }) }
  const funcs = runInNewContext(`${helpers}\n${polling}\n${closing}\n${lifecycle}\n;({ loadKnowledgePreview, startPreviewRequest })`, context)
  return { ...state, ...funcs, timers, calls, errors, hooks }
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve))
}

test('生成中显示状态，准备好后自动显示当前文件并结束等待', async () => {
  const state = setup([{ status: 'loading', message: '正在生成预览' }, { status: 'ready', content: 'pdf-byte-marker' }])
  const finished = state.loadKnowledgePreview(entry)
  await flush()
  assert.equal(state.previewFile.value.status, 'loading')
  assert.equal(state.loadingPreview.value, true)
  assert.equal(state.calls.length, 1)
  state.timers.shift()()
  await finished
  assert.equal(state.previewFile.value.content, 'pdf-byte-marker')
  assert.equal(state.loadingPreview.value, false)
  assert.equal(state.calls.length, 2)
  assert.equal(state.timers.length, 0)
})

test('切换文件后旧轮询退出且不清除新文件加载状态', async () => {
  const state = setup([{ status: 'loading' }])
  const finished = state.loadKnowledgePreview(entry)
  await flush()
  state.startPreviewRequest({ ...entry, file_id: 'file_2', path: '/knowledge/file_2' })
  state.timers.shift()()
  await finished
  assert.equal(state.selectedEntry.value.file_id, 'file_2')
  assert.equal(state.previewFile.value.file_id, 'file_2')
  assert.equal(state.loadingPreview.value, true)
  assert.equal(state.calls.length, 1)
})

test('任务失败立即呈现错误，不继续轮询', async () => {
  const state = setup([{ status: 'error', message: '预览生成失败' }])
  await state.loadKnowledgePreview(entry)
  assert.equal(state.previewFile.value.status, 'error')
  assert.equal(state.loadingPreview.value, false)
  assert.equal(state.calls.length, 1)
  assert.equal(state.timers.length, 0)
})

test('过期网络响应不能覆盖后选择的文件', async () => {
  let complete
  const pending = new Promise((resolve) => { complete = resolve })
  const state = setup([pending])
  const finished = state.loadKnowledgePreview(entry)
  state.startPreviewRequest({ ...entry, file_id: 'file_2', path: '/knowledge/file_2' })
  complete({ status: 'ready', content: 'old-pdf' })
  await finished
  assert.equal(state.previewFile.value.file_id, 'file_2')
  assert.equal(state.loadingPreview.value, true)
})

for (const event of ['deactivated', 'unmounted']) {
  test(`页面 ${event} 后结束旧轮询并释放预览`, async () => {
    const state = setup([{ status: 'loading' }])
    const finished = state.loadKnowledgePreview(entry)
    await flush()
    state.hooks[event]()
    state.timers.shift()()
    await finished
    assert.equal(state.calls.length, 1)
    assert.equal(state.loadingPreview.value, false)
    assert.equal(state.selectedEntry.value, null)
    assert.equal(state.previewFile.value, null)
  })
}
