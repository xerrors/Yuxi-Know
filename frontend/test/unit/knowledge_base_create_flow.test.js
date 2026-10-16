import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildKnowledgeBaseRequest,
  createEmptyKnowledgeBaseForm,
  selectKnowledgeBaseType,
  validateKnowledgeBaseConfig
} from '../../src/modules/knowledge/model/knowledgeBaseCreateForm.js'
import { getKbTypeLabel, isReadOnlyKnowledgeBase } from '../../src/modules/knowledge/model/kb_utils.js'

const difyType = {
  create_params: {
    options: [
      { key: 'url', label: '地址', required: true },
      { key: 'token', label: 'Token', type: 'password', required: true }
    ]
  }
}

test('切换知识库类型保留通用字段并重置类型参数', () => {
  const form = { ...createEmptyKnowledgeBaseForm('embed/model'), name: '产品资料', description: '说明' }
  const selected = selectKnowledgeBaseType(form, 'dify', difyType)
  assert.equal(selected.name, '产品资料')
  assert.equal(selected.description, '说明')
  assert.deepEqual(selected.additional_params, { url: '', token: '' })
})

test('配置校验拒绝空名称和必填动态字段', () => {
  const empty = selectKnowledgeBaseType(createEmptyKnowledgeBaseForm(), 'dify', difyType)
  assert.equal(validateKnowledgeBaseConfig(empty, difyType), '请输入知识库名称')
  empty.name = '资料'
  assert.equal(validateKnowledgeBaseConfig(empty, difyType), '请填写地址')
})

test('只为需要嵌入模型的类型构建模型和分块参数', () => {
  const form = {
    ...createEmptyKnowledgeBaseForm('embed/model'),
    name: '资料',
    kb_type: 'milvus',
    chunk_preset_id: 'general'
  }
  const request = buildKnowledgeBaseRequest(
    form,
    { requires_embedding_model: true, create_params: { options: [] } },
    { version: 2 },
    'fallback/model'
  )
  assert.equal(request.embedding_model_spec, 'embed/model')
  assert.equal(request.additional_params.chunk_preset_id, 'general')

  const connectorRequest = buildKnowledgeBaseRequest(
    { ...form, kb_type: 'dify' },
    difyType,
    { version: 2 },
    'fallback/model'
  )
  assert.equal('embedding_model_spec' in connectorRequest, false)
  assert.equal('chunk_preset_id' in connectorRequest.additional_params, false)
})

test('知识库类型标签映射将 milvus 解析为 Yuxi', () => {
  assert.equal(getKbTypeLabel('milvus'), 'Yuxi')
  assert.equal(getKbTypeLabel('Milvus'), 'Yuxi')
  assert.equal(getKbTypeLabel('dify'), 'Dify')
  assert.equal(getKbTypeLabel('notion'), 'Notion')
  assert.equal(getKbTypeLabel('unknown'), 'unknown')
})


test('飞书连接只提交用户凭证和空间配置，不要求嵌入模型或分块', () => {
  const type = { requires_embedding_model: false, create_params: { options: [
    { key: 'feishu_user_token', label: '用户 Token', type: 'password', required: true },
    { key: 'feishu_space_id', label: '知识空间', required: true }
  ] } }
  const form = selectKnowledgeBaseType(createEmptyKnowledgeBaseForm(), 'feishu', type)
  form.name = '飞书资料'
  assert.equal(validateKnowledgeBaseConfig(form, type), '请填写用户 Token')
  form.additional_params = { feishu_user_token: 'fixture-only', feishu_space_id: '123' }
  assert.equal(validateKnowledgeBaseConfig(form, type), '')
  const request = buildKnowledgeBaseRequest(form, type, { version: 2 })
  assert.deepEqual(request.additional_params, form.additional_params)
  assert.equal('embedding_model_spec' in request, false)
  assert.equal(isReadOnlyKnowledgeBase('feishu'), true)
  assert.equal(getKbTypeLabel('feishu'), '飞书')
})
