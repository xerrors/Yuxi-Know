// 真实 Vite 页面执行：playwright-cli -s=<session> run-code --filename=frontend/test/browser/mentionRendering.js
// prettier-ignore
async page => {
  const check = (value, message) => { if (!value) throw new Error(message) }
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.evaluate(async () => {
    const main = await (await fetch('/src/app/main.js')).text()
    const vueUrl = main.match(/from "([^"]*\/vue\.js[^"']*)"/)[1]
    const { createApp, h, ref } = await import(vueUrl)
    const { default: Input } = await import('/src/modules/session/ui/MessageInputComponent.vue')
    const { default: Message } = await import('/src/modules/session/ui/AgentMessageComponent.vue')
    const { useThemeStore } = await import('/src/shared/model/theme.js')
    const raw = '@agent:research-fixture 生成一下天气的报告'
    const content = ref(raw)
    const draft = ref(raw)
    const mention = ref({ agents: [{ agent_id: 'research-fixture', name: '深度研究' }] })
    const host = document.createElement('div')
    host.id = 'mention-rendering-check'
    Object.assign(host.style, { position: 'fixed', inset: '40px', zIndex: 10000, padding: '24px', overflow: 'auto', background: 'var(--gray-0)' })
    document.body.append(host)
    const app = createApp({ render: () => h('div', [
      h('div', { class: 'history', style: 'margin-bottom:32px' }, [h(Message, { message: { type: 'human', content: content.value }, mention: mention.value })]),
      h(Input, { modelValue: draft.value, mention: mention.value, 'onUpdate:modelValue': value => { draft.value = value } })
    ]) })
    const root = document.querySelector('#app').__vue_app__
    app.use(root.config.globalProperties.$pinia)
    const theme = useThemeStore(root.config.globalProperties.$pinia)
    const themeMode = theme.themeMode
    const savedTheme = localStorage.getItem('theme')
    Object.assign(app._context.components, root._context.components)
    const listeners = new Set()
    const addListener = window.addEventListener
    const removeListener = window.removeEventListener
    window.addEventListener = function (type, listener, options) {
      if (type === 'online') listeners.add(listener)
      return addListener.call(this, type, listener, options)
    }
    window.removeEventListener = function (type, listener, options) {
      if (type === 'online') listeners.delete(listener)
      return removeListener.call(this, type, listener, options)
    }
    app.mount(host)
    window.__mentionRendering = { app, host, content, draft, mention, raw, listeners, addListener, removeListener, theme, themeMode, savedTheme }
  })
  try {
    await page.locator('#mention-rendering-check .mention-editor .mention-ref-token').waitFor()
    const compare = async () => {
      const result = await page.evaluate(async () => {
        const host = window.__mentionRendering.host
        await Promise.all([...host.querySelectorAll('img')].map(img => img.decode().catch(() => {})))
        return ['.history', '.mention-editor'].map(selector => {
          const token = host.querySelector(`${selector} .mention-ref-token`)
          const icon = token.querySelector('.mention-ref-icon')
          const style = getComputedStyle(token)
          return { label: token.querySelector('.mention-ref-label').textContent, image: icon.querySelector('img')?.src, avatar: !!icon.querySelector('.fallback-avatar'), size: [icon.getBoundingClientRect().width, icon.getBoundingClientRect().height], styles: [style.gap, style.alignItems, style.color, style.fontWeight] }
        })
      })
      check(result[0].avatar && result[1].avatar, '消息与输入框必须都渲染智能体头像')
      check(JSON.stringify(result[0]) === JSON.stringify(result[1]), `提及外观不一致：${JSON.stringify(result)}`)
      return result[0]
    }
    const generated = await compare()
    const customIcon = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"><circle cx="9" cy="9" r="8" fill="teal"/></svg>')
    await page.evaluate(icon => { window.__mentionRendering.mention.value = { agents: [{ agent_id: 'research-fixture', name: '研究助手', icon }] } }, customIcon)
    await page.waitForFunction(() => [...document.querySelectorAll('#mention-rendering-check .mention-ref-label')].every(label => label.textContent === '研究助手'))
    const custom = await compare()
    check(custom.image === customIcon, '目录头像未传入消息与输入框')
    await page.evaluate(() => { window.__mentionRendering.mention.value.agents[0].icon = 'data:image/svg+xml,invalid' })
    await page.waitForFunction(() => document.querySelectorAll('#mention-rendering-check [data-avatar-state="fallback"]').length === 2)
    await compare()
    await page.evaluate(() => { window.__mentionRendering.mention.value = { agents: [] } })
    await page.waitForFunction(() => [...document.querySelectorAll('#mention-rendering-check .mention-ref-label')].every(label => label.textContent === 'research-fixture'))
    await compare()
    await page.evaluate(() => { window.__mentionRendering.mention.value = { agents: [{ agent_id: 'research-fixture', name: '深度研究' }] } })
    await page.waitForFunction(() => [...document.querySelectorAll('#mention-rendering-check .mention-ref-label')].every(label => label.textContent === '深度研究'))
    const themeImages = {}
    for (const [theme, width] of [['light', 1440], ['dark', 1440], ['light', 768], ['dark', 768]]) {
      await page.setViewportSize({ width, height: 900 })
      await page.evaluate(mode => window.__mentionRendering.theme.setTheme(mode), theme)
      themeImages[theme] = (await compare()).image
      await page.locator('#mention-rendering-check').screenshot({ path: `/tmp/yuxi-mention-${theme}-${width}.png` })
    }
    check(themeImages.light !== themeImages.dark, '生成头像没有响应实际主题切换')
    await page.locator('#mention-rendering-check .mention-editor').evaluate(editor => {
      editor.dispatchEvent(new InputEvent('input', { bubbles: true }))
    })
    check(await page.evaluate(() => window.__mentionRendering.draft.value) === '@agent:research-fixture 生成一下天气的报告', '编辑器必须序列化原始提及 ID')
    await page.evaluate(() => {
      const editor = document.querySelector('#mention-rendering-check .mention-editor')
      editor.focus()
      const range = document.createRange()
      range.setStartAfter(editor.querySelector('[data-mention-raw]'))
      range.collapse(true)
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range)
    })
    await page.keyboard.press('Backspace')
    check(await page.evaluate(() => window.__mentionRendering.draft.value) === ' 生成一下天气的报告', 'Backspace 必须整体删除提及并保留后文')
    for (const [raw, label] of [
      ['@file:/reports/weather.txt', 'weather.txt'],
      ['@knowledge:天气资料', '天气资料'],
      ['@mcp:weather-service', 'weather-service'],
      ['@skill:research', 'research']
    ]) {
      await page.evaluate(raw => {
        window.__mentionRendering.content.value = raw
        window.__mentionRendering.draft.value = raw
      }, raw)
      await page.waitForFunction(label => [...document.querySelectorAll('#mention-rendering-check .mention-ref-label')].every(node => node.textContent === label), label)
      const icons = await page.locator('#mention-rendering-check .mention-ref-icon').evaluateAll(nodes => nodes.map(node => node.innerHTML))
      check(icons.length === 2 && icons[0] === icons[1], `其他资源提及图标不一致：${raw}`)
      await page.locator('#mention-rendering-check .mention-editor').evaluate(editor => editor.dispatchEvent(new InputEvent('input', { bubbles: true })))
      check(await page.evaluate(() => window.__mentionRendering.draft.value) === raw, `其他资源原始 token 丢失：${raw}`)
    }
    await page.evaluate(() => {
      const state = window.__mentionRendering
      state.content.value = state.raw
      state.draft.value = state.raw
    })
    await page.waitForFunction(() => window.__mentionRendering.listeners.size === 2)
    await page.locator('#mention-rendering-check .mention-editor').focus()
    await page.keyboard.press('ControlOrMeta+a')
    await page.keyboard.type('替换后的正文')
    check(await page.evaluate(() => window.__mentionRendering.draft.value) === '替换后的正文', '原生替换没有更新输入')
    check(await page.evaluate(() => window.__mentionRendering.listeners.size) === 1, '原生替换后输入头像实例未卸载')
    return { generatedAvatar: generated.avatar, customAvatar: true, failedImageFallback: true, asyncDirectory: true, themes: ['light', 'dark'], widths: [1440, 768], rawSerialization: true, atomicDeletion: true, otherTypes: ['file', 'knowledge', 'mcp', 'skill'], nativeReplacementCleanup: true }
  } finally {
    await page.evaluate(() => {
      const state = window.__mentionRendering
      state.app.unmount(); state.host.remove()
      window.addEventListener = state.addListener
      window.removeEventListener = state.removeListener
      if (state.listeners.size !== 0) throw new Error(`组件卸载后仍保留头像监听器：${state.listeners.size}；draft=${state.draft.value}`)
      state.theme.setTheme(state.themeMode)
      if (state.savedTheme === null) localStorage.removeItem('theme')
      else localStorage.setItem('theme', state.savedTheme)
      delete window.__mentionRendering
    })
  }
}
