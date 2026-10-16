// 在真实 Vite 页面验证飞书搜索、实时阅读、分页与错误恢复。
async page => {
  const check = (condition, message) => { if (!condition) throw new Error(message) }
  let rejectRead = false
  let singlePage = false
  const routeHandler = async route => {
    const path = route.request().url().split('?')[0]
    let body = {}
    if (path.endsWith('/query-test')) body = [{ content: '飞书测试文章', metadata: { file_id: 'Wiki123', source: '飞书测试文章', result_type: 'document' } }]
    else if (path.endsWith('/query-params')) body = { params: { options: [] } }
    else if (path.endsWith('/sample-questions')) body = { questions: [] }
    else if (path.endsWith('/open_kb_document')) {
      if (rejectRead) return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'feishu_request_failed', message: '用户凭证已过期，请更换 Token' } }) })
      const { offset } = route.request().postDataJSON()
      body = singlePage
        ? { content: '     1\t  首行缩进\n     2\t第二行\n     3\t\n     4\t最后一行', start_line: 1, end_line: 4, total_lines: 4, offset: 0, window_size: 200, has_more_before: false, has_more_after: false, next_offset: null }
        : { content: offset ? '   201\t第二页正文' : '     1\t<script>unsafe()</script>飞书正文', start_line: offset ? 201 : 1, end_line: offset ? 201 : 200, total_lines: 201, offset, window_size: 200, has_more_before: offset > 0, has_more_after: offset === 0, next_offset: offset ? null : 200 }
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  }
  await page.route('**/api/**', routeHandler)
  await page.evaluate(async () => {
    const main = await (await fetch('/src/app/main.js')).text()
    const { createApp, h } = await import(main.match(/from "([^"]*\/vue\.js[^"']*)"/)[1])
    const { createPinia } = await import(main.match(/from "([^"]*\/pinia\.js[^"']*)"/)[1])
    const { default: Query } = await import('/src/modules/knowledge/ui/QuerySection.vue')
    const { useKnowledgeBaseStore } = await import('/src/modules/knowledge/model/knowledgeBase.js')
    const { useThemeStore } = await import('/src/shared/model/theme.js')
    const { configureApiAuth } = await import('/src/apis/auth_context.js')
    configureApiAuth({ getToken: () => 'fixture-only', isAdmin: () => true })
    const pinia = createPinia()
    useKnowledgeBaseStore(pinia).knowledgeBase = { kb_id: 'feishu-fixture', kb_type: 'feishu', can_manage: false }
    const theme = useThemeStore(pinia)
    const root = document.querySelector('#app').__vue_app__
    const host = document.createElement('div')
    host.id = 'feishu-reading-check'
    Object.assign(host.style, { position: 'fixed', inset: '16px', zIndex: 1000, padding: '16px', overflow: 'auto', background: 'var(--gray-0)' })
    document.body.append(host)
    const app = createApp({ render: () => h(root._context.components.AConfigProvider, { theme: theme.currentTheme }, () => h(Query)) })
    app.use(pinia)
    Object.assign(app._context.components, root._context.components)
    app.mount(host)
    window.feishuReadingFixture = { app, host, theme }
  })
  const host = page.locator('#feishu-reading-check')
  try {
    await host.locator('textarea').fill('测试')
    await host.getByRole('button', { name: '检索知识库', exact: true }).click()
    await host.locator('.result-open').waitFor()
    check((await host.locator('.result-summary').textContent()).includes('相关文档'), '搜索结果没有标为文档')
    await host.locator('.result-open').focus()
    await page.keyboard.press('Enter')
    const reader = host.getByRole('region', { name: '飞书文档正文' })
    await reader.locator('pre').waitFor()
    check((await reader.locator('pre').textContent()).includes('<script>unsafe()</script>'), '正文未按纯文本显示')
    check(await reader.locator('script').count() === 0, '正文执行了 HTML')
    check(await reader.locator('.reader-line-number').first().textContent() === '1', '行号保留了多余的补齐空白')
    check(await host.locator('.query-results').evaluate(el => getComputedStyle(el).backgroundColor === 'rgba(0, 0, 0, 0)'), '结果区域仍有额外背景色')
    check(await reader.getByRole('button', { name: '上一页', exact: true }).isDisabled(), '第一页可以向前翻页')
    await reader.getByRole('button', { name: '下一页', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('#feishu-reading-check pre')?.textContent.includes('第二页正文'))
    check(await reader.getByRole('button', { name: '下一页', exact: true }).isDisabled(), '末页可以继续翻页')
    await reader.screenshot({ path: '/tmp/yuxi-feishu-pagination.png' })
    await reader.getByRole('button', { name: '关闭文档', exact: true }).click()
    singlePage = true
    await host.locator('.result-open').click()
    await reader.locator('pre').waitFor()
    check(await reader.getByRole('navigation', { name: '文档分页' }).count() === 0, '只有一页时仍显示分页按钮')
    check(await reader.locator('.reader-line-text').first().textContent() === '  首行缩进', '正文原有缩进丢失')
    check(await reader.locator('.reader-line').count() === 4, '正文空行丢失')
    for (const mode of ['light', 'dark']) {
      await page.evaluate(mode => window.feishuReadingFixture.theme.setTheme(mode), mode)
      for (const width of [1440, 768]) {
        await page.setViewportSize({ width, height: 1000 })
        check(await reader.isVisible(), '阅读面板不可见')
        check(await reader.evaluate(el => el.scrollWidth <= el.clientWidth + 1), '阅读面板横向溢出')
        await page.screenshot({ path: `/tmp/yuxi-feishu-reader-${mode}-${width}.png` })
      }
    }
    await reader.getByRole('button', { name: '关闭文档', exact: true }).click()
    check(await reader.count() === 0, '关闭后仍显示正文')
    rejectRead = true
    await host.locator('.result-open').click()
    await reader.getByRole('alert').waitFor()
    check((await reader.getByRole('alert').textContent()).includes('凭证已过期'), '读取错误没有可见原因')
    rejectRead = false
    await reader.getByRole('button', { name: '重新读取', exact: true }).click()
    await reader.locator('pre').waitFor()
    return { search: true, read: true, pagination: true, plainText: true, keyboard: true, retry: true, singlePageControlsHidden: true, compactLineNumbers: true, transparentResults: true, layouts: 4 }
  } finally {
    await page.evaluate(() => { window.feishuReadingFixture.app.unmount(); window.feishuReadingFixture.host.remove(); delete window.feishuReadingFixture })
    await page.unroute('**/api/**', routeHandler)
  }
}
