// 真实 Vite 页面运行：playwright-cli -s=<session> --raw run-code --filename=frontend/test/browser/avatarThemeColors.js
// prettier-ignore
async page => {
  const check = (value, message) => { if (!value) throw new Error(message) }
  await page.evaluate(async () => {
    const main = await (await fetch('/src/app/main.js')).text()
    const vueUrl = main.match(/from "([^"]*\/vue\.js[^"']*)"/)[1]
    const { createApp, h } = await import(vueUrl)
    const { default: FallbackAvatar } = await import('/src/shared/ui/FallbackAvatar.vue')
    const host = document.createElement('div')
    host.id = 'avatar-theme-colors'
    Object.assign(host.style, { position: 'fixed', inset: '20px', zIndex: '10000', overflow: 'auto', padding: '20px', background: 'var(--gray-0)' })
    document.body.append(host)
    const styles = ['glyphs', 'clay', 'shape-grid', 'gaze']
    const presets = ['default', 'studio', 'heritage', 'soft']
    const app = createApp({ render: () => h('div', { style: 'display:grid;grid-template-columns:repeat(4,1fr);gap:12px' }, styles.flatMap(style => presets.map(preset =>
      h('div', { 'data-style': style, 'data-preset': preset, style: 'border:1px solid var(--gray-200);padding:12px' }, [
        h('div', { style: 'margin-bottom:8px;color:var(--gray-900)' }, `${style} / ${preset}`),
        ...['off', 'on'].map(dark => h('span', { style: `display:inline-flex;flex-direction:column;gap:4px;padding:8px;color:${dark === 'off' ? '#292d38' : '#ffffff'};background:${dark === 'off' ? '#ffffff' : '#222633'}` }, [
          h('span', dark === 'off' ? 'light' : 'dark'),
          h(FallbackAvatar, { style, preset, dark, seed: 'theme-color-fixture', size: 72, shape: 'square', decorative: true })
        ]))
      ])
    ))) })
    app.use(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia)
    app.mount(host)
    window.__avatarThemeColors = { app, host }
  })
  try {
    await page.locator('#avatar-theme-colors img').evaluateAll(images => Promise.all(images.map(image => image.decode())))
    const pairs = await page.evaluate(async () => {
      const { presets } = await import('/src/shared/lib/avatar/presets.js')
      const source = await (await fetch('/src/shared/lib/avatar/generator.js')).text()
      const nativeColors = {}
      for (const [style, variable, channel] of [['glyphs', 'glyphs', 'glyph'], ['clay', 'clay', 'body'], ['shape-grid', 'shapeGrid', 'background'], ['gaze', 'gaze', 'body']]) {
        const url = source.match(new RegExp(`import ${variable} from "([^"]+)"`))[1]
        const native = (await import(url)).default
        nativeColors[style] = native.colors[channel].values
      }
      return [...document.querySelectorAll('#avatar-theme-colors [data-style]')].map(row => {
        const svgs = [...row.querySelectorAll('img')].map(image => decodeURIComponent(image.src.split(',').slice(1).join(',')))
        const colors = svgs.map(svg => {
          const body = row.dataset.preset === 'default' ? nativeColors[row.dataset.style] : presets[row.dataset.preset].light.body.map(color => `#${color}`)
          return [...svg.matchAll(/fill="([^"]+)"/g)].map(match => match[1]).filter(color => body.includes(color))
        })
        return { style: row.dataset.style, preset: row.dataset.preset, colors }
      })
    })
    for (const { style, preset, colors } of pairs) {
      check(colors[0].length > 0, `${style}/${preset} 未读取到实际主体填色`)
      check(JSON.stringify(colors[0]) === JSON.stringify(colors[1]), `${style}/${preset} 实际主体填色不一致`)
    }
    check(await page.locator('#avatar-theme-colors [data-avatar-state=fallback]').count() === 0, '头像进入失败占位')
    await page.locator('#avatar-theme-colors').evaluate(host => { host.style.inset = '20px 20px auto'; host.style.overflow = 'visible' })
    await page.locator('#avatar-theme-colors').screenshot({ path: '/tmp/yuxi-avatar-theme-colors.png', animations: 'disabled' })
    return { pairs: pairs.length, decodedImages: pairs.length * 2, bodyColorsStable: true }
  } finally {
    await page.evaluate(() => { window.__avatarThemeColors.app.unmount(); window.__avatarThemeColors.host.remove(); delete window.__avatarThemeColors })
  }
}
