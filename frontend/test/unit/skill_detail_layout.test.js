import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function readSource(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), 'utf8')
}

test('完整内容与权限配置有独立保存边界，切换文件和页签保留内容草稿', () => {
  const source = readSource('../../src/modules/extensions/ui/SkillDetailView.vue')
  const saveStart = source.indexOf('const saveContent = async')
  const save = source.slice(saveStart, source.indexOf('const confirmDeleteSkill', saveStart))
  assert.match(save, /expected_revision: contentRevision\.value/)
  assert.match(save, /collectSkillChanges/)
  assert.doesNotMatch(save, /fetchSkillDetail\(\)/)
  assert.match(source, /onBeforeRouteLeave/)
})

test('无预览 header 的 HTML 文件在编辑态隐藏模式控件', () => {
  const source = readSource('../../src/modules/session/ui/workspace/AgentFilePreview.vue')
  const controlsStart = source.indexOf('showInlineHtmlControls &&')
  const controls = source.slice(
    controlsStart,
    source.indexOf('class="preview-mode-switch', controlsStart)
  )

  assert.ok(controlsStart >= 0)
  assert.match(controls, /!\(canEdit && editMode === 'edit'\)/)
})
