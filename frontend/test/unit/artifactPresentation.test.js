import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, effectScope, reactive, ref } from 'vue'
import { normalizeArtifacts } from '../../src/modules/session/model/artifacts.js'

const source = readFileSync(
  new URL('../../src/modules/session/ui/AgentArtifactsCard.vue', import.meta.url),
  'utf8'
)
const { descriptor } = parse(source)
const executable = compileScript(descriptor, { id: 'artifact-presentation' })
  .content.replace(/^import .+ from '[^']+'\n/gm, '')
  .replace('export default', 'return')

/** 执行实际文件卡片 setup，核对字符串产物构建折叠文件列表。 */
function setupCard(t, artifacts) {
  const scope = effectScope()
  const props = reactive({ artifacts, threadId: 'thread-a' })
  const component = new Function('deps', `const { computed, ref, normalizeArtifacts, threadApi,
    message, ChevronDown, Download, LoaderCircle, Save, FileTypeIcon, WorkspacePathPicker, parseDownloadFilename } = deps;
    ${executable}`)({ computed, ref, normalizeArtifacts, threadApi: {} })
  const view = scope.run(() => component.setup(props, { expose() {}, emit() {} }))
  t.after(() => scope.stop())
  return view
}

test('交付物字符串路径保序去重', () => {
  assert.deepEqual(normalizeArtifacts([' /a.png ', '/a.png', '/b.png', '']), ['/a.png', '/b.png'])
})

test('不兼容旧交付物对象', () => {
  assert.throws(() => normalizeArtifacts([{ path: '/a.png', type: 'image' }]), TypeError)
})

test('字符串交付物构建统一折叠文件列表', (t) => {
  const view = setupCard(t, ['/image.png', '/a.md', '/b.md', '/c.md'])
  assert.equal(view.normalizedArtifacts.value.length, 4)
  assert.equal(view.visibleArtifacts.value.length, 3)
  view.expanded.value = true
  assert.equal(view.visibleArtifacts.value.length, 4)
  assert.equal(view.imagePreviews, undefined)
  assert.ok(view.normalizedArtifacts.value.every(file => !('type' in file)))
})
