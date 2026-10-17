// Vite 页面执行：playwright-cli -s=<session> run-code --filename=frontend/test/browser/mentionResourceAvatars.js
// prettier-ignore
async page => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.evaluate(async () => {
    const main = await (await fetch('/src/app/main.js')).text()
    const { createApp, h, ref } = await import(main.match(/from "([^"]*\/vue\.js[^"']*)"/)[1])
    const { default: Input } = await import('/src/modules/session/ui/MessageInputComponent.vue')
    const draft = ref('')
    const host = document.createElement('div')
    host.id = 'mention-avatar-check'
    host.style = 'position:fixed;inset:24px;z-index:99999;background:var(--gray-0);display:flex;align-items:flex-end;padding:24px'
    document.body.append(host)
    const app = createApp({ render: () => h(Input, {
      modelValue: draft.value,
      'onUpdate:modelValue': value => { draft.value = value },
      mention: {
        knowledgeBases: [{ kb_id: 'kb-fixture-1', name: 'Production deployment check', description: 'Synthetic deployment verification' }],
        skills: [
          { slug: 'mysql-reporter', name: 'Mysql Reporter', description: '生成 MySQL 查询报表。当用户需要查询 MySQL 数据库并以报表形式展示结果时使用此技能。' },
          { slug: 'chat-widgets', name: 'Chat Widgets', description: '在普通聊天中直接展示图片、图文卡片和数值图表，或用简短表单收集用户回答。' }
        ],
        agents: [{ agent_id: 'research-fixture', name: '研究助手' }]
      }
    }) })
    const root = document.querySelector('#app').__vue_app__
    app.use(root.config.globalProperties.$pinia)
    Object.assign(app._context.components, root._context.components)
    app.mount(host)
    window.__mentionAvatarCheck = { app, host, draft }
  })
  try {
    const editor = page.locator('#mention-avatar-check .mention-editor')
    await editor.fill('@')
    await page.locator('#mention-avatar-check .mention-popup').waitFor()
    const rows = page.locator('#mention-avatar-check .resource-item')
    if (await rows.count() !== 4) throw new Error('候选资源未完整显示')
    const colors = await page.evaluate(async () => {
      const { getExtensionIconColor } = await import('/src/shared/lib/extensionIconColor.js')
      return ['kb-fixture-1', 'mysql-reporter', 'chat-widgets'].map(id => getExtensionIconColor(id))
    })
    for (let index = 0; index < 3; index++) {
      const row = rows.nth(index)
      const color = await row.locator('.resource-avatar').evaluate(node => node.style.getPropertyValue('--resource-color'))
      if (color !== colors[index]) throw new Error('候选头像与资源卡片颜色不一致')
      if (await row.locator('svg').count() !== 1) throw new Error('资源图标缺失')
    }
    if (await rows.nth(0).locator('.lucide-database-zap').count() !== 1) throw new Error('知识库没有使用目录图标')
    if (await rows.nth(3).locator('.fallback-avatar').count() !== 1) throw new Error('智能体头像缺失')
    for (const dark of [false, true]) {
      await page.evaluate(value => document.documentElement.classList.toggle('dark', value), dark)
      for (const width of [1440, 768]) {
        await page.setViewportSize({ width, height: 900 })
        const overflow = await page.locator('#mention-avatar-check .mention-popup').evaluate(node => node.scrollWidth > node.clientWidth)
        if (overflow) throw new Error('候选弹窗横向溢出')
        await page.locator('#mention-avatar-check').screenshot({ path: `/tmp/yuxi-mention-avatars-${dark ? 'dark' : 'light'}-${width}.png` })
      }
    }
    await editor.press('ArrowDown')
    await editor.press('Enter')
    const value = await page.evaluate(() => window.__mentionAvatarCheck.draft.value)
    if (!value.includes('@skill:mysql-reporter')) throw new Error('头像改动破坏键盘插入')
    return { colors, keyboardInsertion: value, screenshots: '/tmp/yuxi-mention-avatars-*.png' }
  } finally {
    await page.evaluate(() => {
      window.__mentionAvatarCheck.app.unmount()
      window.__mentionAvatarCheck.host.remove()
      document.documentElement.classList.remove('dark')
      delete window.__mentionAvatarCheck
    })
  }
}
