import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import test from 'node:test'
import * as Vue from 'vue'
import { compileTemplate, parse } from 'vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'

test('Markdown 根节点继承调用方 scoped 标记并保留 class 和 style', async () => {
  const source = await fs.readFile(
    new URL('../../src/modules/workspace/ui/MarkdownPreview.vue', import.meta.url), 'utf8'
  )
  const { descriptor } = parse(source)
  const compiled = compileTemplate({ source: descriptor.template.content, filename: 'MarkdownPreview.vue', id: 'markdown-preview' })
  assert.deepEqual(compiled.errors, [])
  const executable = compiled.code
    .replace(/import \{([^}]+)\} from "vue"/, (_, names) => `const {${names.replaceAll(' as ', ': ')}} = Vue`)
    .replace('export function render', 'return function render')
  const MarkdownPreview = {
    inheritAttrs: false,
    render: new Function('Vue', executable)(Vue),
    components: { ReferenceSourcePopover: { render: () => Vue.h('aside') } },
    setup() {
      return {
        themeStore: { isDark: false }, compact: false, referencePreview: null,
        previewRef: Vue.ref(null), referencePopover: Vue.ref(null), referencePreviewId: 'preview',
        handleMarkdownAction() {}, handleReferenceEnter() {}, scheduleReferenceClose() {},
        handleReferenceKeydown() {}, cancelReferenceClose() {}, closeReferencePreview() {}, openReference() {}
      }
    }
  }
  const Parent = {
    __scopeId: 'data-v-caller',
    render: () => Vue.h('section', [Vue.h(MarkdownPreview, { class: 'caller-markdown', style: { color: 'red' } })])
  }
  const html = await renderToString(Vue.createSSRApp(Parent))
  assert.match(html, /<div(?=[^>]*data-v-caller)(?=[^>]*class="[^"]*caller-markdown)(?=[^>]*style="color:red;")[^>]*>/)
})
