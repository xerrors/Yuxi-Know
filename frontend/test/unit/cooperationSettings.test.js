import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { computed, h } from 'vue'
import { compileScript, parse } from 'vue/compiler-sfc'

test('协作深度只提交完整的非负整数，清空或非法输入保留原配置', () => {
  const writes = []
  const deps = {
    computed, h,
    useConfigStore: () => ({ config: { max_cooperation_depth: 2 }, setConfigValue: (...args) => writes.push(args) }),
    useUserStore: () => ({ isSuperAdmin: true }),
    Globe: {}, ModelSelectorComponent: {}, EmbeddingModelSelector: {}, RerankModelSelector: {}, SkillSettingsSection: {}
  }
  const { descriptor } = parse(readFileSync(new URL('../../src/modules/settings/ui/BasicSettingsSection.vue', import.meta.url), 'utf8'))
  const code = compileScript(descriptor, { id: 'cooperation-settings' }).content
    .replace(/^import[\s\S]*?from '[^']+'\n/gm, '').replace('export default', 'return')
  const form = new Function(...Object.keys(deps), code)(...Object.values(deps)).setup({}, { expose() {} })
  for (const input of [null, undefined, '', '2', -1, 1.5, 0, 2]) form.handleCooperationDepthChange(input)
  assert.deepEqual(writes, [['max_cooperation_depth', 0], ['max_cooperation_depth', 2]])
})
