import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { Avatar, Style } from '@dicebear/core'
import {
  defaultStyles,
  generate,
  resolveDark,
  resolvePreset
} from '../../src/shared/lib/avatar/generator.js'
import { presets } from '../../src/shared/lib/avatar/presets.js'

/** 独立比较路径与变换，填色和外层裁切不参与几何判断。 */
function geometry(svg) {
  return [...svg.matchAll(/<(path|ellipse|circle|rect|polygon|polyline|g)\b[^>]*>/g)].flatMap(
    ([tag]) => {
      const attrs = Object.fromEntries(
        [...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map((a) => [a[1], a[2]])
      )
      if (
        tag.startsWith('<rect') &&
        attrs.width === attrs.height &&
        ['100', '72'].includes(attrs.width)
      )
        return []
      return [
        Object.fromEntries(
          ['d', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'width', 'height', 'points', 'transform']
            .filter((key) => key in attrs)
            .map((key) => [key, attrs[key]])
        )
      ]
    }
  )
}

test('四种风格默认输出保留原作，色卡与夜间只改变颜色', () => {
  for (const style of ['glyphs', 'clay', 'shape-grid', 'gaze']) {
    const definition = JSON.parse(
      readFileSync(
        new URL(`../../node_modules/@dicebear/styles/src/${style}.json`, import.meta.url)
      )
    )
    for (const shape of ['circle', 'square', 'rounded']) {
      const borderRadius = { circle: 50, square: 0, rounded: 18 }[shape]
      const native = new Avatar(new Style(definition), {
        seed: 'user:42',
        size: 256,
        borderRadius,
        idRandomization: false
      }).toString()
      assert.equal(generate({ style, seed: 'user:42', shape, dark: 'off' }), native)
      for (const seed of ['user:001', 'agent:research', 'mcp:filesystem']) {
        const expected = geometry(generate({ style, seed, shape }))
        for (const preset of Object.keys(presets))
          for (const dark of ['on', 'off']) {
            assert.deepEqual(
              geometry(generate({ style, preset, seed, shape, dark })),
              expected,
              `${style}/${preset}/${dark}`
            )
            assert.ok(
              Object.keys(resolvePreset(style, preset, dark === 'on')).every((key) =>
                key.endsWith('Color')
              )
            )
          }
      }
    }
  }
})

test('身份稳定、支持自动主题、未知参数明确拒绝、配置返回值独立', () => {
  assert.deepEqual(defaultStyles, { user: 'glyphs', agent: 'clay' })
  assert.equal(
    generate({ style: 'gaze', seed: 'agent:42' }),
    generate({ style: 'gaze', seed: 'agent:42' })
  )
  assert.notEqual(
    generate({ style: 'gaze', seed: 'agent:42' }),
    generate({ style: 'gaze', seed: 'agent:43' })
  )
  assert.equal(
    generate({ style: 'gaze', dark: 'auto' }, true),
    generate({ style: 'gaze', dark: 'on' })
  )
  assert.equal(
    generate({ style: 'gaze', dark: 'auto' }, false),
    generate({ style: 'gaze', dark: 'off' })
  )
  assert.equal(resolveDark('off', true), false)
  assert.equal(resolveDark('on', false), true)
  assert.throws(() => generate({ style: 'unknown' }), /style/)
  assert.throws(() => generate({ style: 'gaze', preset: '__proto__' }), /preset/)
  assert.throws(() => generate({ style: 'gaze', preset: 'missing' }), /preset/)
  assert.throws(() => generate({ style: 'gaze', shape: 'triangle' }), /shape/)
  assert.throws(() => generate({ style: 'gaze', dark: 'missing' }), /dark/)
  assert.throws(() => generate({ style: 'gaze', seed: ' ' }), /seed/)
  const options = resolvePreset('glyphs', 'studio')
  options.glyphColor[0] = 'ffffff'
  assert.equal(resolvePreset('glyphs', 'studio').glyphColor[0], '6489c7')
})

test('Gaze 不配置背景，恶意身份不进入 SVG 内容，Glyphs 保留署名许可', () => {
  for (const preset of Object.keys(presets))
    for (const dark of [true, false]) {
      assert.equal(resolvePreset('gaze', preset, dark).backgroundColor, undefined)
    }
  const svg = generate({ style: 'gaze', seed: '<script>alert(1)</script>' })
  assert.doesNotMatch(svg, /<script|alert\(1\)/)
  const glyph = generate({ style: 'glyphs', dark: 'on' })
  assert.match(glyph, /Matt Houser/)
  assert.match(glyph, /https:\/\/creativecommons.org\/licenses\/by\/4.0\//)
})

test('深浅色保留同一身份的主体填色，官方原色使用各风格上游色板', () => {
  for (const [name, preset] of Object.entries(presets)) {
    assert.deepEqual(preset.dark.body, preset.light.body, `${name} 主体色板`)
  }
  for (const style of ['glyphs', 'clay', 'shape-grid', 'gaze']) {
    const native = JSON.parse(readFileSync(
      new URL(`../../node_modules/@dicebear/styles/src/${style}.json`, import.meta.url)
    ))
    const channel = { glyphs: 'glyph', clay: 'body', 'shape-grid': 'background', gaze: 'body' }[style]
    for (const preset of Object.keys(presets)) {
      const body = preset === 'default' ? native.colors[channel].values : presets[preset].light.body.map(color => `#${color}`)
      for (const seed of ['user:42', 'agent:research', 'mcp:filesystem']) {
        const fills = dark => [...generate({ style, preset, seed, dark }).matchAll(/fill="([^"]+)"/g)]
          .map(match => match[1]).filter(color => body.includes(color))
        const light = fills('off')
        assert.ok(light.length > 0, `${style}/${preset} 缺少主体填色`)
        assert.deepEqual(fills('on'), light, `${style}/${preset}/${seed} 主体填色改变`)
      }
    }
  }
})
