import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { computed, reactive, ref, watch } from 'vue'
import { compileScript, parse } from 'vue/compiler-sfc'
import { parseMcpManifest } from '../../src/modules/extensions/model/mcpManifest.js'

const source = readFileSync(
  new URL('../../src/modules/extensions/ui/McpFormModal.vue', import.meta.url), 'utf8'
)
const { descriptor } = parse(source)
const executable = compileScript(descriptor, { id: 'mcp-submit-test' }).content
  .replace(/^import .* from '[^']+'\n/gm, '')
  .replace('export default', 'return')

for (const editMode of [false, true]) {
  for (const headersText of ['false', '0', 'null', '[]']) {
    test(`${editMode ? '编辑' : '创建'}表单拒绝显式非法 headers ${headersText}`, async () => {
      const errors = []
      const writes = []
      const events = []
      const deps = {
        computed, reactive, ref, watch, parseMcpManifest,
        CollapseTransition: {}, ChevronRight: {}, Plug: {},
        message: { error: (value) => errors.push(value) },
        mcpApi: {
          createMcpServer: (data) => writes.push(data),
          updateMcpServer: (slug, data) => writes.push({ slug, ...data })
        }
      }
      const component = new Function(...Object.keys(deps), executable)(...Object.values(deps))
      const form = component.setup({ open: true, editMode, editData: null }, {
        expose() {}, emit: (...args) => events.push(args)
      })
      Object.assign(form.form, {
        slug: 'example', name: 'Example', url: 'https://example.com/mcp', headersText
      })
      await form.handleFormSubmit()
      assert.match(errors[0], /headers 必须是字符串键值对象/)
      assert.deepEqual(writes, [])
      assert.deepEqual(events, [])
      assert.equal(form.formLoading.value, false)
    })
  }
}


test('编辑共享认证并清空请求头时，显式提交空 headers 以允许切换 OAuth', async () => {
  const writes = []
  const deps = {
    computed, reactive, ref, watch, parseMcpManifest,
    CollapseTransition: {}, ChevronRight: {}, Plug: {},
    message: { error: (value) => { throw new Error(value) }, success() {} },
    mcpApi: { updateMcpServer: async (slug, data) => { writes.push({ slug, ...data }); return { success: true, data } } }
  }
  const component = new Function(...Object.keys(deps), executable)(...Object.values(deps))
  const form = component.setup({ open: true, editMode: true, editData: { slug: 'existing', name: 'Existing', url: 'https://mcp.example/mcp', headers: { Authorization: 'Bearer shared' } } }, { expose() {}, emit() {} })
  Object.assign(form.form, { headersText: '', auth_mode: 'oauth', issuer_url: 'https://sso.example', client_id: 'client' })
  await form.handleFormSubmit()
  assert.deepEqual(writes[0].headers, {})
  assert.equal(writes[0].auth_mode, 'oauth')
  assert.equal(writes[0].oauth_config.client_id, 'client')
  assert.equal(Object.hasOwn(writes[0].oauth_config, 'require_same_identity'), false)
})


for (const [label, clearSecret, clientSecret, expectedSecret] of [
  ['保留已有值', false, '', undefined],
  ['显式清除', true, '', ''],
  ['替换已有值', false, 'replacement-secret', 'replacement-secret'],
  ['清除优先于新输入', true, 'replacement-secret', '']
]) {
  test(`编辑 OAuth Client Secret：${label}`, async () => {
    const writes = []
    const deps = {
      computed, reactive, ref, watch, parseMcpManifest,
      CollapseTransition: {}, ChevronRight: {}, Plug: {},
      message: { error: (value) => { throw new Error(value) }, success() {} },
      mcpApi: { updateMcpServer: async (slug, data) => { writes.push(data); return { success: true, data } } }
    }
    const component = new Function(...Object.keys(deps), executable)(...Object.values(deps))
    const form = component.setup({ open: true, editMode: true, editData: {
      slug: 'oauth', name: 'OAuth', url: 'https://mcp.example/mcp', auth_mode: 'oauth',
      oauth_client_secret_set: true, oauth_config: { issuer_url: 'https://sso.example', client_id: 'client' }
    } }, { expose() {}, emit() {} })
    form.form.clear_client_secret = clearSecret
    form.form.client_secret = clientSecret
    await form.handleFormSubmit()
    assert.equal(Object.hasOwn(writes[0].oauth_config, 'client_secret'), expectedSecret !== undefined)
    assert.equal(writes[0].oauth_config.client_secret, expectedSecret)
  })
}
