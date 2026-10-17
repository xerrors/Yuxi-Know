// 独立 Vite 会话：playwright-cli -s=<session> --raw run-code --filename=frontend/test/browser/feedbackTable.js
// 固定协议 fixture 验证布局与交互；不写入真实反馈或验证后端授权。
// prettier-ignore
async page => {
  const check = (condition, message) => { if (!condition) throw new Error(message) }
  await page.waitForLoadState('networkidle')
  const origin = await page.evaluate(() => location.origin)
  const longReason = '检索结果缺少关键证据，建议先核对版本与原始文档，再给出可验证的步骤。'.repeat(90)
  const reasons = [longReason, '回答解决了问题。', '解决了我的问题\n\n\n补充：给出了清晰的操作步骤。', null, 'https://example.test/' + 'long-path'.repeat(60)]
  const records = Array.from({ length: 12 }, (_, index) => ({
    id: index + 1, source: index % 3 === 0 ? 'agent' : 'user', rating: index % 2 ? 'like' : 'dislike',
    reason: reasons[index % reasons.length], agent_id: index % 2 ? 'research' : 'assistant',
    agent_name: index % 2 ? '研究助手' : '智能助手', created_at: '2026-10-16T06:26:00Z', updated_at: '2026-10-16T06:26:00Z'
  }))
  let mode = 'normal'
  let failMore = true
  let hold = true
  let release
  const pending = new Promise(resolve => { release = resolve })
  const cursors = []
  await page.route('**/api/**', async route => {
    const url = route.request().url()
    const path = url.split('?')[0]
    const param = key => decodeURIComponent(url.match(new RegExp('[?&]' + key + '=([^&]*)'))?.[1] || '')
    let json = {}
    if (path.endsWith('/auth/me')) json = { id: 1, uid: 'feedback-fixture', username: '布局测试', role: 'superadmin' }
    if (path.endsWith('/api/projects')) json = []
    if (path.endsWith('/api/v1/agents/sessions')) json = { data: [], has_more: false }
    if (path.endsWith('/system/info')) json = { success: true, data: { branding: { name: 'Yuxi', logo: '/favicon.svg' } } }
    if (path.endsWith('/check-first-run')) json = { first_run: false }
    if (path.endsWith('/api/agent')) json = { agents: [{ agent_id: 'assistant', name: '智能助手' }, { agent_id: 'research', name: '研究助手' }] }
    if (path.endsWith('/system/agent-feedback')) {
      if (hold) await pending
      const after = param('after')
      cursors.push(after)
      if (mode === 'error' || (mode === 'pages' && after && failMore)) {
        failMore = false
        return route.fulfill({ status: 503, json: { detail: '服务暂不可用' } })
      }
      let items = mode === 'empty' ? [] : records.filter(item =>
        (!param('source') || item.source === param('source')) &&
        (!param('rating') || item.rating === param('rating')) &&
        (!param('agent_id') || item.agent_id === param('agent_id')))
      if (mode === 'pages') items = [records[after ? 1 : 0]]
      json = { items, has_more: mode === 'pages' && !after, last_id: items.at(-1)?.id ?? null }
    }
    return route.fulfill({ json })
  })
  await page.evaluate(async () => {
    const { useUserStore } = await import('/src/modules/identity/model/user.js')
    useUserStore().applySession({ access_token: 'feedback-layout-fixture', username: '布局测试', uid: 'feedback-fixture', role: 'superadmin' })
  })
  const rows = page.locator('.feedback-record')
  const refresh = page.locator('.feedback-toolbar').getByRole('button', { name: '刷新', exact: true })
  const settle = () => page.waitForFunction(() => document.querySelector('.feedback-records')?.getAttribute('aria-busy') === 'false')
  const reload = async () => { await refresh.click(); await settle() }
  try {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.goto(`${origin}/dashboard?tab=feedback`)
    await page.getByLabel('正在加载反馈', { exact: true }).waitFor()
    hold = false
    release()
    await rows.first().waitFor()
    check(await page.locator('.feedback-heading').count() === 0, '重复标题和副标题仍占用空间')
    check(await page.locator('table.feedback-records').count() === 1, '未使用普通表格')
    check(await page.locator('.feedback-list .ant-segmented').count() === 0, '来源仍使用分段滑块')
    check(await page.locator('.source-field .ant-select-selection-item').innerText() === '全部来源', '下拉默认来源错误')
    check(await page.locator('.source-field input[type=radio]').count() === 0, '反馈来源仍使用单选')
    const layouts = []
    for (const theme of ['light', 'dark']) {
      await page.evaluate(async value => {
        const { useThemeStore } = await import('/src/shared/model/theme.js')
        useThemeStore().setTheme(value)
      }, theme)
      await page.waitForTimeout(250)
      for (const width of [768, 1024, 1440, 1920]) {
        await page.setViewportSize({ width, height: 1000 })
        const layout = await page.locator('.feedback-list').evaluate(el => {
          const rows = [...el.querySelectorAll('.feedback-record')]
          const heights = rows.map(row => row.getBoundingClientRect().height)
          const table = el.querySelector('table')
          const toolbar = el.querySelector('.feedback-toolbar').getBoundingClientRect()
          return { heights, visibleRows: rows.filter(row => row.getBoundingClientRect().bottom <= innerHeight).length,
            overflow: el.scrollWidth > el.clientWidth + 1, tableTop: table.getBoundingClientRect().top, toolbarHeight: toolbar.height,
            summariesFit: rows.every(row => row.querySelector('.record-reason').getBoundingClientRect().height <= 40.5),
            horizontalScroll: table.parentElement.scrollWidth > table.parentElement.clientWidth }
        })
        check(!layout.overflow, `工具栏或页面溢出 ${theme} ${width}`)
        check(layout.heights.every(height => Math.abs(height - 64) <= 1), `行高不统一 ${theme} ${width}: ${layout.heights}`)
        check(layout.summariesFit, '摘要超出两行')
        if (width >= 1440) {
          check(layout.tableTop < 150 && layout.toolbarHeight <= 65, '工具栏仍占用过多首屏空间')
          check(layout.visibleRows >= 10, '首屏展示记录过少')
          await page.locator('.feedback-list').screenshot({ path: `/tmp/yuxi-feedback-source-${theme}-${width}.png` })
        }
        layouts.push({ theme, width, visibleRows: layout.visibleRows, horizontalScroll: layout.horizontalScroll })
      }
    }
    await page.setViewportSize({ width: 1440, height: 1000 })
    await rows.first().locator('.record-details').click()
    const dialog = page.getByRole('dialog', { name: '反馈详情' })
    await dialog.waitFor()
    check(await dialog.locator('.detail-reason').textContent() === longReason, '详情丢失完整正文')
    await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'hidden' })
    await page.waitForFunction(() => document.activeElement?.classList.contains('record-details'))
    await page.locator('.source-field .ant-select-selector').click()
  await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({ hasText: '用户评价' }).click()
    await settle()
    check(await rows.count() === 8, '用户来源筛选错误')
    await page.locator('.rating-field .ant-select-selector').click()
    await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({ hasText: '正向评价' }).click()
    await settle()
    check(await rows.count() === 4, '正向评价筛选错误')
    await page.locator('.source-field .ant-select-selector').click()
  await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({ hasText: '智能体标记' }).click()
    await settle()
    check(await rows.count() === 4 && await page.locator('.rating-field').count() === 0, '切换来源未清空评价筛选')
    await page.locator('.agent-field .ant-select-selector').click()
    await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({ hasText: '研究助手' }).click()
    await settle()
    check(await rows.count() === 2, '智能体筛选错误')
    await page.getByRole('button', { name: '重置筛选', exact: true }).click()
    await settle()
    check(await rows.count() === 12, '重置未恢复全部记录')
    mode = 'pages'
    await reload()
    await page.getByRole('button', { name: '加载更多', exact: true }).click()
    await page.locator('.page-error').waitFor()
    check(await rows.count() === 1, '后页失败清除了已有记录')
    await page.locator('.page-error').getByRole('button', { name: '重新加载', exact: true }).click()
    await settle()
    check(await rows.count() === 2 && cursors.at(-1) === cursors.at(-2) && cursors.at(-1) !== '', '后页重试未沿用游标追加')
    mode = 'empty'
    await refresh.click()
    await page.getByText('暂无反馈记录', { exact: true }).waitFor()
    mode = 'error'
    await refresh.click()
    await page.getByText('反馈加载失败', { exact: true }).waitFor()
    mode = 'normal'
    await page.getByRole('button', { name: '重新加载', exact: true }).click()
    await settle()
    check(await rows.count() === 12, '故障重试未恢复记录')
    return { layouts, rows: 12, fullDetails: true, filters: true, paginationRetry: true, emptyAndError: true }
  } finally {
    release()
    await page.unrouteAll({ behavior: 'wait' })
    await page.evaluate(() => localStorage.removeItem('user_token'))
  }
}
