// 在已登录开发页面运行：playwright-cli -s=<session> run-code --filename=frontend/test/browser/widgetSandboxImages.js
// 使用真实上传、鉴权预览与会话回复组件；结束时删除本次文件并归档测试 Thread。
async (originalPage) => {
  const context = await originalPage.context().browser().newContext({ storageState: await originalPage.context().storageState() })
  const page = await context.newPage()
  await page.goto(await originalPage.evaluate(() => location.origin))
  const check = (value, message) => { if (!value) throw new Error(message) }
  const originalViewport = page.viewportSize()
  const originalTheme = await page.evaluate(() => localStorage.getItem('theme'))
  try {
    await page.evaluate(async () => {
      const { getApiAuthHeaders } = await import('/src/apis/auth_context.js')
      const headers = getApiAuthHeaders()
      const agentResponse = await fetch('/api/agent/default', { headers })
      const agent = (await agentResponse.json()).agent
      const created = await fetch('/api/v1/agents/sessions', {
        method: 'POST', headers: { ...headers, 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ agent_id: agent.slug || agent.agent_id || agent.id, title: `widget-image-browser-${crypto.randomUUID()}` })
      })
      if (created.status !== 201) throw new Error('测试会话创建失败')
      const threadId = (await created.json()).id
      window.widgetImageProbe = { threadId, headers, stage: 'setup' }
      const sources = []
      const filePaths = []
      window.widgetImageProbe.filePaths = filePaths
      for (const [index, [width, height]] of [[640, 360], [320, 320], [360, 640]].entries()) {
        const canvas = document.createElement('canvas')
        canvas.width = width; canvas.height = height
        const ctx = canvas.getContext('2d')
        ctx.fillStyle = ['#24687a', '#52644e', '#71566c'][index]; ctx.fillRect(0, 0, width, height)
        ctx.fillStyle = '#f5d58a'; ctx.fillRect(width * 0.3, height * 0.2, width * 0.4, height * 0.6)
        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'))
        const data = new FormData()
        data.append('thread_id', threadId); data.append('parent_path', '/')
        data.append('files', blob, `图片 #${index + 1}.png`)
        const uploaded = await fetch('/api/viewer/filesystem/upload', { method: 'POST', headers, body: data })
        if (!uploaded.ok) throw new Error('测试图片上传失败')
        const [entry] = (await uploaded.json()).entries
        filePaths.push(entry.path)
        sources.push('/' + decodeURIComponent(entry.artifact_url.split('/artifacts/')[1]))
      }
      const source = sources[0]
      const module = await (await fetch('/src/shared/model/theme.js')).text()
      const dependency = name => module.match(new RegExp(`from "([^"]*/${name}\\.js[^"]*)"`))[1]
      const { createApp, h, reactive } = await import(dependency('vue'))
      const { createPinia } = await import(dependency('pinia'))
      const antUrl = module.match(/from "([^"]*ant-design-vue\.js[^"]*)"/)[1]
      const { default: AntDesign } = await import(antUrl)
      const { default: Answer } = await import('/src/modules/session/ui/ReferenceAnnotatedAnswer.vue')
      const { default: Artifacts } = await import('/src/modules/session/ui/AgentArtifactsCard.vue')
      const { useThemeStore } = await import('/src/shared/model/theme.js')
      const fence = node => '```widget\n' + JSON.stringify(node, null, 2) + '\n```'
      const widget = (path, caption) => fence({ type: 'Image', path, alt: '蓝色底与黄色方块', ...(caption ? { caption } : {}) })
      const gallery = () => fence({ type: 'ImageGroup', children: Array.from({ length: 7 }, (_, index) => ({
        type: 'Image', path: sources[index % sources.length], alt: `第 ${index + 1} 张图片`, ...(index === 1 ? { caption: '方形方案' } : {})
      })) })
      const state = reactive({ source, threadId, content: widget(source), visible: true, artifacts: true })
      const host = document.createElement('div')
      host.id = 'widget-sandbox-probe'
      host.style.cssText = 'position:fixed;inset:0;z-index:900;background:var(--gray-0);color:var(--gray-900);padding:16px;overflow:auto;box-sizing:border-box'
      document.body.append(host)
      const pinia = createPinia()
      const app = createApp({ render: () => h('div', [
        state.visible ? h(Answer, { content: state.content, threadId: state.threadId, message: {} }) : null,
        state.artifacts ? h(Artifacts, { threadId, artifacts: [{ path: source, type: 'image' }] }) : null
      ]) })
      app.use(pinia); app.use(AntDesign); app.mount(host)
      Object.assign(window.widgetImageProbe, { app, host, state, widget, gallery, sources, theme: useThemeStore(pinia) })
    })
    await page.evaluate(() => { window.widgetImageProbe.stage = 'single image' })
    const image = page.locator('#widget-sandbox-probe .widget-image img')
    await image.waitFor()
    await page.waitForFunction(() => {
      const img = document.querySelector('#widget-sandbox-probe .widget-image img')
      return img?.complete && img.naturalWidth === 640
    })
    check(await image.evaluate(img => img.src.startsWith('blob:')), '沙盒图片没有经 Blob 展示')
    check(await page.locator('#widget-sandbox-probe .artifact-card .image-preview').count() === 0, '旧交付物仍展示专用图片')
    check(await page.locator('#widget-sandbox-probe .widget-card').count() === 0, '图片仍被强制套在卡片中')
    check(await page.locator('#widget-sandbox-probe figcaption').count() === 0, '无短语图片出现多余标签')
    await page.evaluate(() => { window.widgetImageProbe.state.artifacts = false })
    const src = await image.getAttribute('src')
    // 回复组件卸载后以同一内容重建，模拟历史回读。
    await page.evaluate(() => { window.widgetImageProbe.state.visible = false })
    const revoked = await page.evaluate(async url => { try { await fetch(url); return false } catch { return true } }, src)
    check(revoked, '卸载后 Blob 未释放')
    await page.evaluate(() => { window.widgetImageProbe.state.visible = true })
    await image.waitFor()
    await page.waitForFunction(() => document.querySelector('#widget-sandbox-probe .widget-image img')?.naturalWidth === 640)
    const measurements = []
    for (const dark of [false, true]) {
      await page.evaluate(value => window.widgetImageProbe.theme.setTheme(value), dark ? 'dark' : 'light')
      for (const width of [1440, 1024, 768, 375]) {
        await page.setViewportSize({ width, height: 900 })
        await image.waitFor()
        await page.waitForFunction(() => { const img = document.querySelector('#widget-sandbox-probe .widget-image img'); return img?.complete && img.naturalWidth === 640 && img.getBoundingClientRect().height > 0 })
        const dimensions = await image.evaluate(img => { const rect = img.getBoundingClientRect(); return { natural: [img.naturalWidth, img.naturalHeight], width: rect.width, height: rect.height, fit: getComputedStyle(img).objectFit, pageWidth: innerWidth, overflow: document.querySelector('#widget-sandbox-probe').scrollWidth > innerWidth } })
        check(!dimensions.overflow && dimensions.width <= width && dimensions.fit === 'contain' && Math.abs(dimensions.height - Math.min(dimensions.width * 360 / 640, 400)) < 1, `图片溢出：${JSON.stringify(dimensions)}`)
        measurements.push({ dark, width, ...dimensions })
      }
      await image.waitFor()
      await page.locator('#widget-sandbox-probe').screenshot({ path: `/tmp/yuxi-widget-image-${dark ? 'dark' : 'light'}-mobile.png` })
      await page.setViewportSize({ width: 1024, height: 900 })
      await image.waitFor()
      await page.locator('#widget-sandbox-probe').screenshot({ path: `/tmp/yuxi-widget-image-${dark ? 'dark' : 'light'}.png` })
    }
    await page.evaluate(() => { const p = window.widgetImageProbe; p.state.content = p.widget(p.state.source, '蓝色与黄色') })
    const caption = page.locator('#widget-sandbox-probe figcaption')
    await caption.waitFor()
    const overlay = await caption.evaluate(el => {
      const rect = el.getBoundingClientRect(), image = el.parentElement.getBoundingClientRect()
      return { left: rect.left - image.left, bottom: image.bottom - rect.bottom, align: getComputedStyle(el).textAlign }
    })
    check(overlay.left === 10 && overlay.bottom === 10 && overlay.align === 'left', `短语没有叠放在左下角：${JSON.stringify(overlay)}`)
    await page.locator('#widget-sandbox-probe .widget-image').screenshot({ path: '/tmp/yuxi-widget-image-caption.png' })
    await page.evaluate(() => { window.widgetImageProbe.stage = 'gallery' })
    const galleryMeasurements = []
    await page.evaluate(() => { const p = window.widgetImageProbe; p.state.content = p.gallery() })
    const strip = page.locator('#widget-sandbox-probe .widget-imagegroup')
    for (const theme of ['light', 'dark']) {
      await page.evaluate(value => window.widgetImageProbe.theme.setTheme(value), theme)
      for (const width of [1024, 768, 375]) {
        await page.setViewportSize({ width, height: 900 })
        await page.waitForFunction(() => {
          const images = [...document.querySelectorAll('#widget-sandbox-probe .widget-imagegroup img')]
          return images.length === 7 && images.every(img => img.complete && img.naturalWidth && img.getBoundingClientRect().height > 0)
        })
        const group = await strip.evaluate(el => ({
          scrollable: el.scrollWidth > el.clientWidth,
          pageOverflow: document.querySelector('#widget-sandbox-probe').scrollWidth > innerWidth,
          images: [...el.querySelectorAll('img')].map(img => { const rect = img.getBoundingClientRect(); return { top: rect.top, width: rect.width, height: rect.height, fit: getComputedStyle(img).objectFit } })
        }))
        check(group.scrollable && !group.pageOverflow, '图片组应内部横向滚动，正文不能溢出')
        check(group.images.every(img => Math.abs(img.width / img.height - 5 / 4) < 0.01 && img.fit === 'cover' && Math.abs(img.top - group.images[0].top) < 1), '图片组缩略图没有保持同高同排5:4')
        if (width === 375) check(group.images[0].width < (width - 32) / 2, '窄屏应保留至少两张完整缩略图和后续图片提示')
        check(await strip.locator('.widget-image-count').count() === 0, '图片组仍显示数量角标')
        check(await strip.evaluate(el => getComputedStyle(el).scrollbarWidth === 'none'), '图片组仍显示滚动条')
        galleryMeasurements.push({ theme, width, ...group })
      }
      await strip.screenshot({ path: `/tmp/yuxi-widget-gallery-${theme}-mobile.png` })
      await page.setViewportSize({ width: 1024, height: 900 })
      await strip.screenshot({ path: `/tmp/yuxi-widget-gallery-${theme}.png` })
    }
    await strip.evaluate(el => { el.scrollLeft = el.scrollWidth })
    check(await strip.evaluate(el => el.scrollLeft > 0), '横向滚动无法浏览后续图片')
    await strip.evaluate(el => { el.scrollLeft = 0 })
    await page.evaluate(() => { window.widgetImageProbe.stage = 'open preview' })
    const third = strip.locator('.widget-image').nth(2)
    await third.focus()
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: '图片预览', exact: true })
    await dialog.waitFor()
    await page.waitForFunction(() => document.querySelector('.widget-image-preview img')?.naturalHeight === 640)
    check(await dialog.locator('.widget-image-preview img').getAttribute('alt') === '第 3 张图片', '预览没有打开选择的图片')
    const bounds = await dialog.boundingBox()
    check(bounds.x === 0 && bounds.y === 0 && bounds.width === 1024 && bounds.height === 900, '预览没有铺满视口')
    await page.evaluate(() => { window.widgetImageProbe.stage = 'next image' })
    await dialog.getByRole('button', { name: '下一张', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('.widget-image-preview img')?.naturalWidth === 640 && document.querySelector('.widget-image-preview img')?.naturalHeight === 360)
    await page.evaluate(() => { window.widgetImageProbe.stage = 'keyboard previous image' })
    await page.keyboard.press('ArrowLeft')
    await page.waitForFunction(() => document.querySelector('.widget-image-preview img')?.naturalHeight === 640)
    await dialog.screenshot({ path: '/tmp/yuxi-widget-image-preview-dark.png' })
    await page.evaluate(() => window.widgetImageProbe.theme.setTheme('light'))
    await dialog.screenshot({ path: '/tmp/yuxi-widget-image-preview.png' })
    await page.setViewportSize({ width: 375, height: 812 })
    await dialog.screenshot({ path: '/tmp/yuxi-widget-image-preview-mobile.png' })
    await page.setViewportSize({ width: 1024, height: 900 })
    await dialog.getByRole('button', { name: '关闭图片预览', exact: true }).click()
    await dialog.waitFor({ state: 'hidden' })
    await page.waitForFunction(() => document.querySelectorAll('#widget-sandbox-probe .widget-imagegroup .widget-image')[2] === document.activeElement)
    await page.keyboard.press('Enter')
    await dialog.waitFor()
    await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'hidden' })
    await page.waitForFunction(() => document.querySelectorAll('#widget-sandbox-probe .widget-imagegroup .widget-image')[2] === document.activeElement)
    await page.evaluate(() => { window.widgetImageProbe.stage = 'protected src' })
    // 受保护src只通过鉴权读取能力请求，缩略图和预览都不发送未鉴权图片请求。
    const protectedSrc = '/api/v1/agents/sessions/widget-src-probe/artifacts/image.png'
    const realImageUrl = await page.evaluate(async () => {
      const { threadApi } = await import('/src/apis/agent_api.js')
      const p = window.widgetImageProbe
      return threadApi.getThreadArtifactUrl(p.threadId, p.state.source) + '?preview=true'
    })
    let releaseAuthorized
    let authorizedGate = new Promise(resolve => { releaseAuthorized = resolve })
    const protectedRequests = { image: 0, fetch: 0 }
    await page.route('**' + protectedSrc, async route => {
      if (route.request().resourceType() === 'image') {
        protectedRequests.image++
        await route.fulfill({ status: 401, body: 'Unauthorized' })
      } else {
        protectedRequests.fetch++
        check(Boolean(route.request().headers().authorization), '同源图片补载未带鉴权')
        await authorizedGate
        const origin = await page.evaluate(() => location.origin)
        const response = await route.fetch({ url: origin + realImageUrl })
        await route.fulfill({ response })
      }
    })
    await page.evaluate(src => { window.widgetImageProbe.state.content = '```widget\n' + JSON.stringify({ type: 'Image', src, alt: '鉴权图片' }) + '\n```' }, protectedSrc)
    try {
      await page.locator('#widget-sandbox-probe .widget-image [role="status"]').waitFor()
    } finally {
      releaseAuthorized()
    }
    await page.waitForFunction(() => {
      const img = document.querySelector('#widget-sandbox-probe .widget-image img')
      return img?.complete && img.naturalWidth === 640 && !document.querySelector('#widget-sandbox-probe .widget-image [role="alert"]')
    }, undefined, { timeout: 5000 })
    check(protectedRequests.image === 0 && protectedRequests.fetch === 1, `同源鉴权补载请求不符：${JSON.stringify(protectedRequests)}`)
    await image.click()
    await dialog.waitFor()
    await page.waitForFunction(() => document.querySelector('.widget-image-preview img')?.naturalWidth === 640)
    check(protectedRequests.image === 0 && protectedRequests.fetch === 2, '预览没有通过同源鉴权读取能力重新加载')
    await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'hidden' })
    await page.evaluate(() => { window.widgetImageProbe.stage = 'pending protected group preview' })
    let releasePending
    authorizedGate = new Promise(resolve => { releasePending = resolve })
    await page.evaluate(src => {
      const p = window.widgetImageProbe
      p.state.content = '```widget\n' + JSON.stringify({ type: 'ImageGroup', children: [
        { type: 'Image', path: p.state.source, alt: '已就绪图片' },
        { type: 'Image', src, alt: '鉴权请求未完成的图片' }
      ] }) + '\n```'
    }, protectedSrc)
    const firstPending = strip.locator('.widget-image').first()
    await page.waitForFunction(() => document.querySelector('#widget-sandbox-probe .widget-imagegroup img')?.naturalWidth === 640)
    await firstPending.click()
    await dialog.waitFor()
    await dialog.getByRole('button', { name: '下一张', exact: true }).click()
    try {
      await dialog.locator('.widget-image [role="status"]').waitFor()
      await page.setViewportSize({ width: 375, height: 900 })
      const heights = await strip.locator('.widget-image').evaluateAll(images => images.map(img => img.getBoundingClientRect().height))
      check(Math.abs(heights[0] - heights[1]) < 1, `未就绪缩略图破坏图片带高度：${JSON.stringify(heights)}`)
    } finally {
      releasePending()
    }
    await page.waitForFunction(() => document.querySelector('.widget-image-preview img')?.naturalWidth === 640)
    check(protectedRequests.image === 0 && protectedRequests.fetch === 4, '未就绪的受保护图片预览没有独立鉴权加载')
    await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'hidden' })
    await page.unroute('**' + protectedSrc)
    await page.evaluate(() => { const p = window.widgetImageProbe; p.state.content = p.widget(p.state.source + '.missing') })
    await page.locator('#widget-sandbox-probe .widget-image [role="alert"]').waitFor()
    await page.locator('#widget-sandbox-probe').screenshot({ path: '/tmp/yuxi-widget-image-error.png' })
    await page.evaluate(() => { const p = window.widgetImageProbe; p.state.content = p.widget(p.state.source) })
    await page.waitForFunction(() => document.querySelector('#widget-sandbox-probe .widget-image img')?.naturalWidth === 640)
    await image.click()
    await dialog.waitFor()
    await page.evaluate(() => { window.widgetImageProbe.state.threadId = crypto.randomUUID() })
    await dialog.waitFor({ state: 'hidden' })
    await page.locator('#widget-sandbox-probe .widget-image [role="alert"]').waitFor()
    check(await image.count() === 0, '会话切换失败后仍保留旧图片')
    return { result: 'passed', measurements, historyRemount: true, blobReleased: true, missingFile: true, invalidThread: true, legacyArtifactFileCard: true, captionOverlay: overlay, galleryPreview: true, keyboardNavigation: true, pendingSourcePreview: true, threadSwitchClosesPreview: true, gallery: galleryMeasurements, protectedSrcRequests: protectedRequests }
  } catch (error) {
    const state = await page.evaluate(() => ({ stage: window.widgetImageProbe?.stage, pathname: location.pathname, probe: Boolean(window.widgetImageProbe), host: Boolean(document.querySelector('#widget-sandbox-probe')), images: document.querySelectorAll('#widget-sandbox-probe img').length }))
    throw new Error(`${JSON.stringify(state)}: ${error.message}`, { cause: error })
  } finally {
    await page.evaluate(async ({ originalTheme }) => {
      const p = window.widgetImageProbe
      if (!p) return
      p.app?.unmount(); p.host?.remove()
      for (const path of p.filePaths || []) {
        const deleted = await fetch('/api/viewer/filesystem/file?' + new URLSearchParams({ thread_id: p.threadId, path }), { method: 'DELETE', headers: p.headers })
        if (!deleted.ok) throw new Error('测试图片清理失败')
      }
      const archived = await fetch(`/api/v1/agents/sessions/${p.threadId}/archive`, { method: 'POST', headers: p.headers })
      if (!archived.ok) throw new Error('测试会话归档失败')
      p.theme?.setTheme(originalTheme || 'light')
      delete window.widgetImageProbe
    }, { originalTheme })
    await page.setViewportSize(originalViewport)
    await context.close()
  }
}
