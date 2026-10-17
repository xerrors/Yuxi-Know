// 使用 Playwright page 执行；原生选图测试需要不拦截 filechooser 的运行器。
// prettier-ignore
async page => {
  const check = (value, message) => { if (!value) throw new Error(message) }
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.evaluate(async () => {
    const main = await (await fetch('/src/app/main.js')).text()
    const { createApp, h, ref } = await import(main.match(/from "([^"]*\/vue\.js[^"']*)"/)[1])
    const { default: Composer } = await import('/src/modules/session/ui/AgentInputArea.vue')
    const draft = ref('保留正文 ')
    const disabled = ref(false)
    const loading = ref(false)
    const events = []
    const host = document.createElement('div')
    host.id = 'composer-add-check'
    host.style = 'position:fixed;inset:24px;z-index:99999;background:var(--gray-0);display:flex;align-items:flex-end;padding:24px'
    document.body.append(host)
    const app = createApp({ render: () => h(Composer, {
      modelValue: draft.value, disabled: disabled.value, isLoading: loading.value,
      'onUpdate:modelValue': value => { draft.value = value },
      onUploadAttachment: files => events.push({ type: 'attachment', count: files.length }),
      onSend: () => events.push({ type: 'send' }),
      mention: { skills: [{ slug: 'mysql-reporter', name: 'Mysql Reporter', description: '生成 MySQL 查询报表。' }] }
    }) })
    const root = document.querySelector('#app').__vue_app__
    app.use(root.config.globalProperties.$pinia)
    Object.assign(app._context.components, root._context.components)
    app.mount(host)
    window.__composerAddCheck = { app, host, draft, events, disabled, loading }
  })
  try {
    const host = page.locator('#composer-add-check')
    const editor = host.locator('.mention-editor')
    const plus = host.getByRole('button', { name: '添加内容', exact: true })
    const popup = host.locator('.mention-popup')
    const draft = () => page.evaluate(() => window.__composerAddCheck.draft.value)
    await editor.click()
    await editor.press('End')
    await plus.click()
    check(await draft() === '保留正文 ', '加号改写了草稿')
    const plusItems = await popup.locator('.mention-item').allTextContents()
    await editor.press('Escape')
    check(await popup.count() === 0 && await draft() === '保留正文 ', '关闭加号菜单破坏草稿')
    await editor.fill('保留正文 @')
    check(JSON.stringify(await popup.locator('.mention-item').allTextContents()) === JSON.stringify(plusItems), '加号和 @ 的添加项不一致')
    await popup.getByRole('button', { name: '上传附件' }).click()
    check(await draft() === '保留正文 ', '附件动作没有只移除 @ 查询')
    check(await page.evaluate(() => window.__composerAddCheck.events.filter(event => event.type === 'attachment').length) === 1, '附件没有派发到既有入口')
    await plus.click()
    await popup.getByText('Mysql Reporter', { exact: true }).click()
    check((await draft()).includes('保留正文 @skill:mysql-reporter'), '加号资源没有插入正文')
    await editor.fill('前文 中段 后文')
    await editor.evaluate(node => {
      const range = document.createRange()
      range.setStart(node.firstChild, 3)
      range.setEnd(node.firstChild, 5)
      const selection = getSelection()
      selection.removeAllRanges()
      selection.addRange(range)
    })
    await plus.click()
    await popup.getByText('Mysql Reporter', { exact: true }).click()
    check(await draft() === '前文 @skill:mysql-reporter  后文', '加号没有在原选择区替换正文')
    await editor.fill('保留正文 @')
    const [chooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      popup.getByRole('button', { name: '添加图片' }).click()
    ])
    check(chooser.isMultiple(), '图片入口丢失多选能力')
    await chooser.setFiles([])
    check(await draft() === '保留正文 ', '取消选图破坏正文')
    check(await host.locator('.image-preview-wrapper').count() === 0, '取消选图产生图片')
    await page.evaluate(async () => {
      const { configureApiAuth, getApiToken } = await import('/src/apis/auth_context.js')
      const token = getApiToken()
      window.__composerAddCheck.restoreAuth = () => configureApiAuth({ getToken: () => token })
      configureApiAuth({ getToken: () => 'browser-fixture' })
    })
    await page.route('**/api/agent/images', route => route.fulfill({ json: {
      image_url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aE0sAAAAASUVORK5CYII=',
      thumbnail_url: '', width: 1, height: 1, format: 'png', mime_type: 'image/png', size_bytes: 68
    } }))
    await plus.click()
    const [imageChooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      popup.getByRole('button', { name: '添加图片' }).click()
    ])
    await imageChooser.setFiles('frontend/test/browser/fixtures/imgA.png')
    await host.locator('.image-preview-list img').waitFor()
    check(await draft() === '保留正文 ', '图片上传改写正文')
    check(await host.locator('.attachment-file-card').count() === 0, '图片进入了附件通道')
    await host.locator('.image-preview-list button').click()
    await editor.fill('保留正文 @')
    await editor.press('Enter')
    check(await page.evaluate(() => window.__composerAddCheck.events.filter(event => event.type === 'attachment').length) === 2, '键盘未选择附件动作')
    check(await page.evaluate(() => window.__composerAddCheck.events.every(event => event.type !== 'send')), '添加动作错误地发送了消息')
    await plus.click()
    await editor.press('ArrowDown')
    await editor.press('ArrowDown')
    await editor.press('Enter')
    check((await draft()).includes('@skill:mysql-reporter'), '加号键盘选择资源失败')
    await editor.fill('保留正文 @')
    for (const dark of [false, true]) {
      await page.evaluate(value => document.documentElement.classList.toggle('dark', value), dark)
      for (const width of [1440, 768]) {
        await page.setViewportSize({ width, height: 900 })
        check(!await popup.evaluate(node => node.scrollWidth > node.clientWidth), '添加菜单横向溢出')
        await host.screenshot({ path: `/tmp/yuxi-composer-add-${dark ? 'dark' : 'light'}-${width}.png` })
      }
    }
    await editor.fill('保留正文 @不存在的查询')
    await popup.locator('.mention-empty').waitFor()
    await editor.press('Escape')
    check(await popup.count() === 0, '无结果时 Escape 无法关闭菜单')
    await page.evaluate(() => { window.__composerAddCheck.disabled.value = true })
    check(await plus.isDisabled(), '禁用输入仍能打开添加菜单')
    await page.evaluate(() => {
      window.__composerAddCheck.disabled.value = false
      window.__composerAddCheck.loading.value = true
    })
    await plus.click()
    check(await popup.getByRole('button', { name: '上传附件' }).count() === 1, '运行中丢失追加附件入口')
    check(await popup.getByRole('button', { name: '添加图片' }).count() === 1, '运行中丢失追加图片入口')
    const [runningChooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      popup.getByRole('button', { name: '添加图片' }).click()
    ])
    await runningChooser.setFiles('frontend/test/browser/fixtures/imgA.png')
    await host.locator('.image-preview-list img').waitFor()
    check(await host.locator('.image-preview-list img').count() === 1, '运行中选图未回填图片预览')
    return { sharedItems: plusItems, draft: await draft(), events: await page.evaluate(() => window.__composerAddCheck.events) }
  } finally {
    await page.unroute('**/api/agent/images')
    await page.evaluate(() => {
      window.__composerAddCheck.restoreAuth?.()
      window.__composerAddCheck.app.unmount()
      window.__composerAddCheck.host.remove()
      document.documentElement.classList.remove('dark')
      delete window.__composerAddCheck
    })
  }
}
