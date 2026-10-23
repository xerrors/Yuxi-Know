import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function readSource(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), 'utf8')
}

test('工作区上传菜单暴露展开状态和菜单语义', () => {
  const source = readSource('../../src/modules/workspace/ui/WorkspaceSidebar.vue')
  const trigger = source.slice(source.indexOf('<button'), source.indexOf('</button>'))
  const menu = source.slice(source.indexOf('<Transition name="file-action-menu">'), source.indexOf('</Transition>'))

  assert.match(trigger, /aria-haspopup="menu"/)
  assert.match(trigger, /:aria-expanded="uploadActionMenuOpen"/)
  assert.match(menu, /class="file-action-menu" role="menu"/)
  assert.equal((menu.match(/role="menuitem"/g) || []).length, 3)
  assert.match(menu, /上传文件夹/)
  assert.match(menu, /onUploadFolderAction/)
})

test('项目创建目录选择器包含尚未绑定的项目目录', () => {
  const source = readSource('../../src/modules/projects/ui/ProjectSelectionSection.vue')
  const pickerStart = source.indexOf('<WorkspacePathPicker')
  const picker = source.slice(pickerStart, source.indexOf('/>', pickerStart) + 2)

  assert.match(picker, /include-unbound-project-dirs/)
})

test('交付物保存使用工作区路径选择器并传递目标目录', () => {
  const component = readSource('../../src/modules/session/ui/AgentArtifactsCard.vue')
  const api = readSource('../../src/apis/agent_api.js')

  assert.match(component, /<WorkspacePathPicker/)
  assert.match(component, /selectedDestination = ref\('\/saved_artifacts'\)/)
  assert.match(component, /v-model="selectedDestination"/)
  assert.match(api, /destination_path: destinationPath/)
})
