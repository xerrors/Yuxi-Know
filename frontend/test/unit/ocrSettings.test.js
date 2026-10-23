import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, ref } from 'vue'

/** 编译真实设置逻辑，以隔离的 API 验证编辑与保存结果。 */
function createForm(deps) {
  const source = readFileSync(
    new URL('../../src/modules/settings/ui/OCRSettingsSection.vue', import.meta.url),
    'utf8'
  )
  const executable = compileScript(parse(source).descriptor, { id: 'ocr-settings' })
    .content.replace(/^import[\s\S]*?from '[^']+'\n/gm, '')
    .replace('export default', 'return')
  const component = new Function(...Object.keys(deps), executable)(...Object.values(deps))
  return component.setup({}, { expose() {} })
}

test('MinerU 旧配置显示默认值，保存选择并重载，取消与失败保留正确状态', async () => {
  const fields = [
    { key: 'server_url', environment: 'MINERU_API_URI' },
    { key: 'backend', default: 'hybrid-engine', choice_labels: { 'hybrid-engine': 'Hybrid（混合解析）', 'vlm-engine': 'VLM（视觉模型解析）' } },
    { key: 'effort', default: 'medium', choice_labels: { medium: '标准（medium）', high: '高精度（high）' } }
  ]
  let saved = { key: 'mineru_ocr_host_opts', params: { fields }, value: { server_url: '' } }
  let failSave = false
  const errors = []
  const deps = {
    computed, ref, onMounted() {}, OCRSelector: {},
    useConfigStore: () => ({ config: {} }),
    message: { success() {}, error: (value) => errors.push(value) },
    configOptionsApi: {
      getOptions: async () => ({ options: [structuredClone(saved)] }),
      updateOption: async (key, value) => {
        assert.equal(key, 'mineru_ocr_host_opts')
        if (failSave) throw new Error('保存失败')
        saved = { ...saved, value: { ...value } }
        return { option: structuredClone(saved) }
      }
    }
  }
  const form = createForm(deps)
  await form.loadConfigOptions()
  let option = form.configOptions.value[0]
  assert.equal(form.getFieldDisplay(option, fields[1]), 'Hybrid（混合解析）')
  assert.equal(form.getFieldDisplay(option, fields[2]), '标准（medium）')
  assert.equal(form.getFieldDisplay(option, fields[0]), '读取 MINERU_API_URI')
  form.startEditing(option)
  assert.deepEqual(form.draftValue.value, { server_url: '', backend: 'hybrid-engine', effort: 'medium' })
  form.draftValue.value.backend = 'vlm-engine'
  form.draftValue.value.effort = 'high'
  form.cancelEditing()
  assert.deepEqual(option.value, { server_url: '' })
  form.startEditing(option)
  form.draftValue.value.backend = 'vlm-engine'
  form.draftValue.value.effort = 'high'
  await form.saveOption(option)
  assert.equal(form.editingKey.value, '')
  await form.loadConfigOptions()
  option = form.configOptions.value[0]
  assert.equal(form.getFieldDisplay(option, fields[1]), 'VLM（视觉模型解析）')
  assert.equal(form.getFieldDisplay(option, fields[2]), '高精度（high）')
  form.startEditing(option)
  form.draftValue.value.effort = 'medium'
  failSave = true
  await form.saveOption(option)
  assert.equal(form.editingKey.value, option.key)
  assert.equal(form.draftValue.value.effort, 'medium')
  assert.equal(option.value.effort, 'high')
  assert.equal(form.savingOption.value, '')
  assert.deepEqual(errors, ['保存失败'])
})

test('Official 默认模型兼容旧记录，修改模型保留凭据，清除凭据必须显式选择', async () => {
  const model = { key: 'model_version', default: 'pipeline', choice_labels: { pipeline: 'Pipeline（传统解析）', vlm: 'VLM（视觉模型解析）' } }
  const option = {
    key: 'mineru_official_api_opts',
    params: { fields: [{ key: 'api_key', sensitive: true }, model] },
    value: { api_key: '' }, sensitive_state: { api_key: { source: 'database' } }
  }
  let secret = 'fixture-original-key'
  const writes = []
  const form = createForm({
    computed, ref, onMounted() {}, OCRSelector: {},
    useConfigStore: () => ({ config: {} }), message: { success() {}, error: assert.fail },
    configOptionsApi: {
      getOptions: async () => ({ options: [structuredClone(option)] }),
      updateOption: async (key, value) => {
        assert.equal(key, option.key)
        writes.push({ ...value })
        if (Object.hasOwn(value, 'api_key')) secret = value.api_key
        option.value.model_version = value.model_version
        return { option: structuredClone(option) }
      }
    }
  })
  await form.loadConfigOptions()
  let current = form.configOptions.value[0]
  assert.equal(form.getFieldDisplay(current, model), 'Pipeline（传统解析）')
  form.startEditing(current)
  assert.equal(form.draftValue.value.model_version, 'pipeline')
  form.draftValue.value.model_version = 'vlm'
  await form.saveOption(current)
  assert.deepEqual(writes[0], { model_version: 'vlm' })
  assert.equal(secret, 'fixture-original-key')
  await form.loadConfigOptions()
  current = form.configOptions.value[0]
  assert.equal(form.getFieldDisplay(current, model), 'VLM（视觉模型解析）')
  form.startEditing(current)
  form.draftValue.value.api_key = '   '
  await form.saveOption(current)
  assert.deepEqual(writes[1], { model_version: 'vlm' })
  assert.equal(secret, 'fixture-original-key')
  form.startEditing(current)
  form.clearedFields.value.api_key = true
  await form.saveOption(current)
  assert.deepEqual(writes[2], { api_key: '', model_version: 'vlm' })
  assert.equal(secret, '')
  form.startEditing(current)
  assert.deepEqual(form.clearedFields.value, {})
  form.draftValue.value.api_key = 'fixture-new-key'
  await form.saveOption(current)
  assert.equal(secret, 'fixture-new-key')
})
