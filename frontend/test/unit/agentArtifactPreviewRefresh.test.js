import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, effectScope, nextTick, reactive, ref, toRaw, watch } from 'vue'
import * as polling from '../../src/modules/session/model/agentPanelFilesystemPolling.js'
import { normalizePreviewResponse } from '../../src/shared/lib/file_preview.js'
import { upsertAgentPanelSection } from '../../src/modules/session/model/agentPanelSections.js'

const source = readFileSync(
  new URL('../../src/modules/session/ui/workspace/AgentPanel.vue', import.meta.url),
  'utf8'
)
const compiled = compileScript(parse(source).descriptor, { id: 'artifact-preview-refresh' })
const executable = compiled.content
  .replace(/^import[\s\S]*?from '[^']+'\n/gm, '')
  .replace('export default', 'return')
const artifactPath = '/home/user/workspace/projects/demo/方案.html'

/** 执行真实面板 setup，以文件响应和终态通知驱动缓存生命周期。 */
async function setupPanel(t) {
  const hooks = {}
  let content = '<h1>预算20万元</h1>'
  const requests = []
  const props = reactive({
    threadId: 'thread-a',
    visible: true,
    viewMode: 'preview',
    activeSectionKey: `file:${artifactPath}`,
    sections: [{ key: `file:${artifactPath}`, type: 'file' }],
    activePreviewPath: artifactPath,
    previewTabs: [{ path: artifactPath, name: '方案.html', workdir: false }],
    previewCache: new Map(),
    filesystemVisible: false,
    filesystemPollingActive: false,
    filesystemRefreshVersion: 0
  })
  const deps = Object.fromEntries(
    compiled.scriptSetupAst
      .filter((node) => node.type === 'ImportDeclaration')
      .flatMap((node) => node.specifiers.map((specifier) => [specifier.local.name, null]))
  )
  Object.assign(deps, polling, {
    computed,
    ref,
    toRaw,
    watch,
    nextTick,
    normalizePreviewResponse,
    window: { URL: { revokeObjectURL() {} } },
    document: { body: { style: {} } },
    onMounted: (fn) => {
      hooks.mounted = fn
    },
    onActivated: (fn) => {
      hooks.activated = fn
    },
    onDeactivated: (fn) => {
      hooks.deactivated = fn
    },
    onUnmounted: (fn) => {
      hooks.unmounted = fn
    },
    threadApi: {
      getThreadArtifactUrl: () => '/artifact',
      previewThreadArtifact: async (threadId, path) => {
        requests.push({ threadId, path })
        return new Response(JSON.stringify({ content, preview_type: 'html', supported: true }), {
          headers: { 'content-type': 'application/json' }
        })
      }
    },
    getWorkspaceTree: async () => ({ entries: [] }),
    getWorkspaceFileContent: async () =>
      new Response(JSON.stringify({ content: '个人文件', preview_type: 'text', supported: true }), {
        headers: { 'content-type': 'application/json' }
      })
  })
  const component = new Function(...Object.keys(deps), executable)(...Object.values(deps))
  const scope = effectScope()
  const view = scope.run(() => component.setup(props, { expose() {}, emit() {} }))
  const settle = async () => {
    await nextTick()
    await Promise.all(
      [...props.previewCache.values()]
        .filter((entry) => entry.status === 'loading')
        .map((entry) => entry.promise)
    )
    await nextTick()
  }
  t.after(() => scope.stop())
  await settle()
  return {
    props,
    view,
    hooks,
    requests,
    settle,
    update: (value) => {
      content = value
    }
  }
}

test('同名交付物在终态通知后更新，默认个人空间树不阻断活动产物刷新', async (t) => {
  const panel = await setupPanel(t)
  assert.match(panel.view.currentFile.value.content, /20万元/)
  assert.equal(panel.requests.length, 1, '同时触发的首次预览应共享同一次读取')
  panel.props.previewCache.set('thread-b:/other', { status: 'ready', file: { content: 'other' } })
  panel.props.previewCache.set('thread-a:/inactive', { status: 'ready', file: { content: 'old' } })
  panel.update('<h1>预算08万元</h1>')
  panel.props.filesystemRefreshVersion++
  await panel.settle()
  assert.match(panel.view.currentFile.value.content, /08万元/)
  assert.equal(panel.props.previewCache.has('thread-a:/inactive'), false)
  assert.equal(panel.props.previewCache.has('thread-b:/other'), true)
})

test('产物预览中的手动刷新读取当前产物，不只刷新个人空间树', async (t) => {
  const panel = await setupPanel(t)
  panel.update('<h1>手动修订</h1>')
  await panel.view.emitRefresh()
  await panel.settle()
  assert.match(panel.view.currentFile.value.content, /手动修订/)
})

test('再次点击同名交付卡片使未知元数据缓存失效并触发面板重读', async (t) => {
  const panel = await setupPanel(t)
  panel.update('<h1>最新卡片</h1>')
  const workspace = readFileSync(
    new URL('../../src/modules/session/ui/SessionWorkspace.vue', import.meta.url),
    'utf8'
  )
  const dependencies = {
    currentChatId: ref('thread-a'),
    agentPanelPreviewCache: panel.props.previewCache,
    window: { URL: { revokeObjectURL() {} } },
    getPanelFileName: (file) => file.name,
    agentPanelPreviewTabs: ref(panel.props.previewTabs),
    agentPanelActivePreviewPath: ref(artifactPath),
    agentPanelSections: ref(panel.props.sections),
    agentPanelActiveSectionKey: ref(`file:${artifactPath}`),
    FILE_TREE_SECTION: { key: 'file-tree' },
    upsertAgentPanelSection,
    showFilePanel() {}
  }
  const release = workspace.slice(
    workspace.indexOf('const previewCacheKey ='),
    workspace.indexOf('const invalidatePreviewCachePath =')
  )
  const open = workspace.slice(
    workspace.indexOf('const openPanelPreview ='),
    workspace.indexOf('const closePanelPreviewTab =')
  )
  const openPreview = new Function(
    ...Object.keys(dependencies),
    `${release}; ${open}; return openPanelPreview`
  )(...Object.values(dependencies))
  openPreview({ path: artifactPath, name: '方案.html' })
  panel.props.previewTabs = dependencies.agentPanelPreviewTabs.value
  await panel.settle()
  assert.match(panel.view.currentFile.value.content, /最新卡片/)
})

test('KeepAlive 停用时不读取文件，返回页面时活动产物重新读取', async (t) => {
  const panel = await setupPanel(t)
  panel.hooks.deactivated()
  panel.update('<h1>后台修订</h1>')
  panel.props.filesystemRefreshVersion++
  await panel.settle()
  assert.equal(panel.requests.length, 1)
  panel.hooks.activated()
  await panel.settle()
  assert.match(panel.view.currentFile.value.content, /后台修订/)
})

test('关闭面板期间完成的同名修改在重开时可见，无需 KeepAlive 激活', async (t) => {
  const panel = await setupPanel(t)
  panel.props.visible = false
  await panel.settle()
  panel.update('<h1>关闭期间修订</h1>')
  panel.props.filesystemRefreshVersion++
  await panel.settle()
  assert.equal(panel.requests.length, 1)
  panel.props.visible = true
  await panel.settle()
  assert.match(panel.view.currentFile.value.content, /关闭期间修订/)
})

test('查看协作成员期间完成的修改在切回产物标签时可见', async (t) => {
  const panel = await setupPanel(t)
  panel.props.sections.push({ key: 'session:child', type: 'session' })
  panel.props.activeSectionKey = 'session:child'
  await panel.settle()
  panel.update('<h1>协作期间修订</h1>')
  panel.props.filesystemRefreshVersion++
  await panel.settle()
  panel.props.activeSectionKey = `file:${artifactPath}`
  await panel.settle()
  assert.match(panel.view.currentFile.value.content, /协作期间修订/)
})

test('终态在个人文件标签发生时也使当前线程的非活动产物失效', async (t) => {
  const panel = await setupPanel(t)
  panel.props.sections.push({ key: 'file:/personal.md', type: 'file' })
  panel.props.previewTabs.push({ path: '/personal.md', name: 'personal.md', workspace: true })
  panel.props.activeSectionKey = 'file:/personal.md'
  panel.props.activePreviewPath = '/personal.md'
  await panel.settle()
  panel.update('<h1>其它标签期间修订</h1>')
  panel.props.filesystemRefreshVersion++
  await panel.settle()
  panel.props.activeSectionKey = `file:${artifactPath}`
  panel.props.activePreviewPath = artifactPath
  await panel.settle()
  assert.match(panel.view.currentFile.value.content, /其它标签期间修订/)
})
