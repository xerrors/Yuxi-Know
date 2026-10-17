import assert from 'node:assert/strict'
import test from 'node:test'
import { getExtensionIconColor } from '../../src/shared/lib/extensionIconColor.js'
import { presets } from '../../src/shared/lib/avatar/presets.js'

test('图标按稳定身份选择预设颜色，重排和主题切换保留身份色', () => {
  const ids = ['mysql-reporter', 'chat-widgets', 'kb-fixture-1', 'kb-fixture-2']
  const colors = ids.map((id) => getExtensionIconColor(id))
  const palette = presets.studio.light.body.map((color) => `#${color}`)
  assert.ok(colors.every((color) => palette.includes(color)))
  assert.ok(new Set(colors).size > 1)
  assert.notEqual(colors[0], colors[1])
  assert.deepEqual([...ids].reverse().map((id) => getExtensionIconColor(id)), [...colors].reverse())
  assert.deepEqual(ids.map((id) => getExtensionIconColor(id, true)), colors)
  assert.equal(getExtensionIconColor(''), '')
  assert.equal(getExtensionIconColor(undefined), '')
})
