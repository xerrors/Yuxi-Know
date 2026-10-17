import { presets } from './avatar/presets.js'

const extensionIconPalette = Object.fromEntries(
  ['light', 'dark'].map((mode) => [
    mode,
    presets.studio[mode].body.map((color) => `#${color}`)
  ])
)

/** 按扩展身份稳定选择图标颜色，并随主题切换到对应色卡。 */
export function getExtensionIconColor(extensionId, dark = false) {
  const id = String(extensionId || '')
  if (!id) return ''

  let hash = 2166136261
  for (const character of id) {
    hash = Math.imul(hash ^ character.codePointAt(0), 16777619)
  }

  const palette = extensionIconPalette[dark ? 'dark' : 'light']
  return palette[(hash >>> 0) % palette.length]
}
