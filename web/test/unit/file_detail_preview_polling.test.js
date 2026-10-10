import { setImmediate } from 'node:timers'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import test from 'node:test'
import { computed, reactive, ref } from 'vue'

const source = readFileSync(new URL('../../src/components/FileDetailModal.vue', import.meta.url), 'utf8')
const resets = source.slice(source.indexOf('const revokeSourcePreviewUrl ='), source.indexOf('const normalizeFileMeta ='))
const polling = source.slice(source.indexOf('const loadSourcePreview ='), source.indexOf('// 下载菜单点击处理'))
const watches = source.slice(source.lastIndexOf('watch(', source.indexOf('// 统计信息')), source.indexOf('// 统计信息'))

const visibility = source.slice(source.indexOf('const componentActive ='), source.indexOf('const file = ref(null)'))
const lifecycle = source.slice(source.indexOf('onActivated(() =>'), source.indexOf('</script>'))

/** 执行真实弹窗函数、视图 watcher 与卸载清理，仅替换接口与时钟。 */
function setup(responses) {
  const timers = []
  const calls = []
  const revoked = []
  const hooks = {}
  const props = reactive({ open: true, kbId: 'kb_1', fileId: 'file_1' })
  const emitted = []
  const visibilityState = runInNewContext(`${visibility}; ({ componentActive, visible })`, {
    computed, ref, props, emit: (event, value) => emitted.push([event, value])
  })
  const state = { file: ref({ file_id: 'file_1', filename: 'book.xlsx' }),
    sourcePreview: ref({ loading: false, url: '', content: '', type: '', message: '', supported: true }),
    viewMode: ref('source'), hasSourcePreview: ref(true), ...visibilityState,
    sourcePreviewCandidateType: ref('office'), contentState: ref({}), basicLoading: ref(false),
    detailError: ref(''), downloadingOriginal: ref(false), downloadingMarkdown: ref(false) }
  const context = { ...state, props, console: { error() {} }, message: { error() {} },
    window: { URL: { revokeObjectURL: (url) => revoked.push(url) },
      setTimeout: (callback, delay) => { assert.equal(delay, 2000); timers.push(callback) } },
    watch: (_sources, callback) => { hooks.viewChanged = callback },
    onActivated: (callback) => { hooks.activated = callback },
    onDeactivated: (callback) => { hooks.deactivated = callback },
    onBeforeUnmount: (callback) => { hooks.unmounted = callback },
    getWorkspaceKnowledgeFileContent: async (kbId, fileId) => { calls.push([kbId, fileId]); return await responses.shift() },
    normalizePreviewResponse: async (response) => response }
  const functions = runInNewContext(`let basicRequestSeq = 0, contentRequestSeq = 0, sourceRequestSeq = 0;
    ${resets}
${polling}
${watches}
${lifecycle};
    ({ loadSourcePreview, resetSourcePreview })`, context)
  return { ...state, ...functions, props, timers, calls, revoked, hooks, emitted }
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve))
}

test('详情弹窗生成中保持等待，完成后自动显示 PDF', async () => {
  const state = setup([{ status: 'loading', message: '正在生成预览' },
    { status: 'ready', previewType: 'pdf', previewUrl: 'blob:ready' }])
  const finished = state.loadSourcePreview()
  await flush()
  assert.equal(state.sourcePreview.value.loading, true)
  assert.equal(state.sourcePreview.value.message, '正在生成预览')
  await state.loadSourcePreview()
  assert.equal(state.calls.length, 1, '重复 watcher 不启动并行读取')
  state.timers.shift()()
  await finished
  assert.equal(state.sourcePreview.value.url, 'blob:ready')
  assert.equal(state.sourcePreview.value.type, 'pdf')
  assert.equal(state.sourcePreview.value.loading, false)
  assert.equal(state.calls.length, 2)
})

test('详情弹窗失败进入终态并停止轮询', async () => {
  const state = setup([{ status: 'error', supported: false, message: '预览生成失败' }])
  await state.loadSourcePreview()
  assert.equal(state.sourcePreview.value.message, '预览生成失败')
  assert.equal(state.sourcePreview.value.supported, false)
  assert.equal(state.sourcePreview.value.loading, false)
  assert.equal(state.timers.length, 0)
})

for (const event of ['close', 'view', 'unmount', 'deactivate', 'file']) {
  test(`详情弹窗 ${event} 后旧轮询结束，返回源文件可以重新加载`, async () => {
    const state = setup([{ status: 'loading', message: '正在生成预览' },
      { status: 'ready', previewUrl: 'blob:new' }])
    const finished = state.loadSourcePreview()
    await flush()
    if (event === 'unmount') state.hooks.unmounted()
    else if (event === 'deactivate') {
      state.hooks.deactivated()
      assert.equal(state.visible.value, false)
    } else if (event === 'file') {
      state.resetSourcePreview()
      state.props.fileId = 'file_2'
      state.file.value = { file_id: 'file_2', filename: 'new.xlsx' }
    } else {
      state.viewMode.value = event === 'view' ? 'markdown' : 'source'
      state.props.open = event !== 'close'
      await state.hooks.viewChanged([state.props.open, state.file.value, state.viewMode.value])
    }
    state.timers.shift()()
    await finished
    assert.equal(state.calls.length, 1)
    assert.equal(state.sourcePreview.value.loading, false)
    assert.equal(state.sourcePreview.value.message, '')
    if (event === 'unmount' || event === 'deactivate') return
    state.props.open = true
    state.viewMode.value = 'source'
    await state.loadSourcePreview()
    assert.equal(state.sourcePreview.value.url, 'blob:new')
    assert.equal(state.calls.length, 2)
  })
}

test('关闭后的迟到 PDF 不覆盖弹窗状态并释放对象 URL', async () => {
  let complete
  const state = setup([new Promise((resolve) => { complete = resolve })])
  const finished = state.loadSourcePreview()
  state.props.open = false
  await state.hooks.viewChanged([false, state.file.value, 'source'])
  complete({ status: 'ready', previewUrl: 'blob:old' })
  await finished
  assert.equal(state.sourcePreview.value.url, '')
  assert.deepEqual(state.revoked, ['blob:old'])
})

test('缓存页面关闭直接隐藏弹窗，父 prop 迟到回传也不残留遮罩', () => {
  const state = setup([])
  assert.equal(state.visible.value, true)
  state.hooks.deactivated()
  assert.equal(state.props.open, true, '保留尚未回传的父组件 open prop')
  assert.equal(state.visible.value, false, '本地激活状态必须立即关闭 Teleport 弹窗')
  assert.deepEqual(state.emitted, [['update:open', false]])
  state.props.open = false
  state.hooks.activated()
  assert.equal(state.visible.value, false, '返回页面保持关闭，直到用户重新打开')
  state.props.open = true
  assert.equal(state.visible.value, true)
})
