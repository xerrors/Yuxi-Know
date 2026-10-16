import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { isReadOnlyKnowledgeBase, supportsKnowledgeBaseDetail } from '../../src/modules/knowledge/model/kb_utils.js'

function readSource(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), 'utf8')
}

test('知识库详情提供面板插槽并校验深链接 Tab', () => {
  const source = readSource('../../src/pages/KnowledgeBaseInfoView.vue')

  assert.match(source, /<ExtensionDetailLayout/)
  assert.match(source, /<template #breadcrumb>/)
  assert.match(source, /<template #actions>/)
  assert.match(source, /<template #panel-filetable>/)
  assert.match(source, /<template #panel-query>/)
  assert.match(source, /<template #panel-graph>/)
  assert.match(source, /<template #panel-evaluation>/)
  assert.match(source, /availableTabs\.some\(\(tab\) => tab\.key === requestedTab\)/)
  assert.match(
    source,
    /loaded && requestedTab && requestedTab !== activeTab\.value[\s\S]*?section: activeTab\.value/
  )
})

test('详情按在线阅读能力开放，配置入口仍要求管理权限', () => {
  const feishu = { kb_type: 'feishu', supports_documents: false }
  assert.equal(supportsKnowledgeBaseDetail(feishu), true)
  assert.equal(isReadOnlyKnowledgeBase(feishu), true)
  assert.equal(supportsKnowledgeBaseDetail({ kb_type: 'milvus' }), true)
  assert.equal(supportsKnowledgeBaseDetail({ kb_type: 'dify' }), false)
  assert.equal(supportsKnowledgeBaseDetail({ kb_type: 'notion' }), false)

  const listSource = readSource('../../src/modules/knowledge/ui/KnowledgeCatalog.vue')
  const detailSource = readSource('../../src/pages/KnowledgeBaseInfoView.vue')
  assert.match(listSource, /<a-menu-item v-if="knowledgeBase\.can_manage" key="edit">/)
  assert.match(
    detailSource,
    /action !== 'edit' \|\| loading \|\| !loaded \|\| !canManageKnowledgeBase\.value/
  )
})

test('检索面板强制挂载以保留上传后的示例问题生成', () => {
  const detailSource = readSource('../../src/pages/KnowledgeBaseInfoView.vue')

  assert.match(detailSource, /key: 'query', label: '检索测试', icon: Search, forceRender: true/)
})
