import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { createSSRApp, h, onUnmounted, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { compileScript, parse } from 'vue/compiler-sfc'
import { Clock, Hourglass, CircleHelp, Database, setLucideProps } from '@lucide/vue'

const source = readFileSync(new URL('../../src/app/App.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const executable = compileScript(descriptor, { id: 'icon-defaults' }).content
  .replace(/^import[^\n]*\n/gm, '')
  .replace('export default', 'return')

test('根组件让未指定尺寸的状态、帮助和按钮图标随字号缩放，保留显式尺寸', async () => {
  const component = new Function('useThemeStore', 'setLucideProps', 'useRouter', 'ref', 'onUnmounted', executable)(
    () => ({ currentTheme: {} }),
    setLucideProps,
    () => ({ currentRoute: { value: { matched: [{}] } }, beforeEach: () => () => {}, onError: () => () => {}, afterEach: () => () => {} }),
    ref, onUnmounted
  )
  component.render = () => h('div', [
    h(Clock), h(Hourglass), h(CircleHelp), h(Database),
    h(Clock, { size: 16 }), h(CircleHelp, { size: 32 }),
    h(Database, { style: { width: '48px', height: '48px' } })
  ])
  const html = await renderToString(createSSRApp(component))
  const icons = [...html.matchAll(/<svg\b([^>]*)>/g)].map((match) => match[1])
  assert.equal(icons.length, 7)
  for (const attrs of icons.slice(0, 4)) {
    assert.match(attrs, /width="1em"/)
    assert.match(attrs, /height="1em"/)
  }
  assert.match(icons[4], /width="16" height="16"/)
  assert.match(icons[5], /width="32" height="32"/)
  assert.match(icons[6], /style="width:48px;height:48px;"/)
})
