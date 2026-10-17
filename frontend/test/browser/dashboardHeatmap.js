// 独立 Vite 浏览器会话：playwright-cli -s=<session> run-code --filename=frontend/test/browser/dashboardHeatmap.js
// 使用固定统计 fixture 验证真实 Dashboard 布局，不验证后端统计与鉴权。
// prettier-ignore
async (page) => {
  const check = (condition, message) => { if (!condition) throw new Error(message) }
  const origin = await page.evaluate(() => location.origin)
  const days = Array.from({ length: 120 }, (_, index) => ({
    date: new Date(Date.UTC(2026, 5, 19 + index)).toISOString().slice(0, 10),
    active_users: index % 5
  }))
  let empty = false
  await page.route('**/api/**', route => {
    const path = route.request().url().split('?')[0]
    let json = {}
    if (path.endsWith('/auth/me')) json = { id: 1, uid: 'heatmap-fixture', username: '布局测试', role: 'superadmin' }
    if (path.endsWith('/check-first-run')) json = { first_run: false }
    if (path.endsWith('/stats/users')) json = {
      total_users: 25, active_users_24h: 2, active_users_30d: 4,
      daily_active_users: empty ? [] : days
    }
    return route.fulfill({ json })
  })
  await page.evaluate(async () => {
    const { useUserStore } = await import('/src/modules/identity/model/user.js')
    useUserStore().applySession({ access_token: 'heatmap-layout-fixture', username: '布局测试', uid: 'heatmap-fixture', role: 'superadmin' })
  })
  const widths = [768, 1024, 1280, 1440, 1920]
  const results = []
  try {
    await page.goto(`${origin}/dashboard`)
    const heatmap = page.locator('.activity-heatmap')
    await heatmap.locator('[title]').last().waitFor()
    for (const theme of ['light', 'dark']) {
      await page.evaluate(async mode => {
        const { useThemeStore } = await import('/src/shared/model/theme.js')
        useThemeStore().setTheme(mode)
      }, theme)
      for (const width of widths) {
        await page.setViewportSize({ width, height: 1000 })
        await heatmap.scrollIntoViewIfNeeded()
        const bounds = await heatmap.evaluate(el => {
          const container = el.getBoundingClientRect()
          const grid = el.querySelector('.heatmap-grid')
          const content = grid.parentElement
          const cells = [...grid.querySelectorAll('[title]:not([title=""])')]
          const months = [...el.querySelectorAll('.heatmap-months span')]
          const inside = node => {
            const box = node.getBoundingClientRect()
            return box.left >= container.left - 1 && box.right <= container.right + 1 && box.width > 0
          }
          return {
            overflow: content.scrollWidth > content.clientWidth + 1,
            cellsInside: cells.every(inside), monthsInside: months.every(node => inside(node) && node.scrollWidth <= node.clientWidth + 1),
            count: cells.length, first: cells[0].title, last: cells.at(-1).title,
            cellWidth: cells[0].getBoundingClientRect().width
          }
        })
        check(!bounds.overflow, `热力图需要横向滚动：${theme} ${width}`)
        check(bounds.cellsInside, `日期格子被裁切：${theme} ${width}`)
        check(bounds.monthsInside, `月份标签被裁切：${theme} ${width}`)
        check(bounds.count === 120, '未展示完整 120 天')
        check(bounds.first === '2026-06-19：0 位活跃用户' && bounds.last === '2026-10-16：4 位活跃用户', '首尾日期或提示错误')
        check((await heatmap.locator('.heatmap-total').innerText()) === '240 次活跃记录', '活跃总数错误')
        results.push({ theme, width, cellWidth: bounds.cellWidth })
        if (width === 1280 || width === 1920) {
          await page.locator('.user-stats').screenshot({ path: `/tmp/yuxi-heatmap-${theme}-${width}.png` })
        }
      }
    }
    empty = true
    await page.reload()
    await page.getByText('暂无活跃记录', { exact: true }).waitFor()
    check(await heatmap.locator('.heatmap-grid').count() === 0, '空状态残留旧格子')
    return { results, days: 120, emptyState: true }
  } finally {
    await page.unrouteAll({ behavior: 'wait' })
    await page.evaluate(() => localStorage.removeItem('user_token'))
  }
}
