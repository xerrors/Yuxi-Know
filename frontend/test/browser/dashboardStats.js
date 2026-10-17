// 已登录开发环境：playwright-cli -s=<session> run-code --filename=frontend/test/browser/dashboardStats.js
// prettier-ignore
async (page) => {
  const check = (condition, message) => { if (!condition) throw new Error(message) }
  const distribution = { '文本文件': 3000, 'PDF文档': 590, 'Word文档': 33, 'HTML网页': 15, 'CSV表格': 4, 'JSON数据': 3, 'Markdown': 2, 'Excel表格': 1 }
  let empty = false
  await page.route('**/api/dashboard/stats/knowledge', (route) => route.fulfill({ json: {
    total_knowledge_bases: 2, total_files: 3648, total_storage_size: 4096,
    file_type_distribution: empty ? {} : distribution
  }}))
  await page.route('**/api/dashboard/stats/tools', (route) => route.fulfill({ json: {
    total_calls: 20, failed_calls: 8, success_rate: 60,
    most_used_tools: [{tool_name:'read_file', count:12}, {tool_name:'ask_user_question', count:8}],
    tool_error_distribution: empty ? {} : { read_file: 3, glob: 2, ask_user_question: 1, edit_file: 1, ls: 1 }
  }}))
  await page.goto('http://localhost:5173/dashboard')
  await page.locator('.file-type-legend li').first().waitFor()
  if (await page.locator('html').evaluate((el) => el.classList.contains('dark'))) {
    await page.getByRole('button', { name: '切换主题', exact: true }).click()
  }
  for (const width of [1440, 1024, 768, 375]) {
    await page.setViewportSize({width, height:1000})
    await page.locator('.file-distribution').scrollIntoViewIfNeeded()
    await page.waitForTimeout(250)
    const bounds = await page.locator('.file-distribution').evaluate((el) => {
      const chart = el.querySelector('.donut-wrap').getBoundingClientRect()
      const legend = el.querySelector('.file-type-legend').getBoundingClientRect()
      return { chartBottom: chart.bottom, legendTop: legend.top, overflow:el.scrollWidth > el.clientWidth }
    })
    check(bounds.legendTop >= bounds.chartBottom, `图例与圆环重叠 ${width}`)
    check(!bounds.overflow, `文件类型溢出 ${width}`)
    check(await page.locator('.file-type-legend li').count() === 8, '文件明细缺失')
    check(await page.locator('.error-analysis').count() === 0, '工具错误分析仍存在')
  }
  await page.setViewportSize({width:1440,height:1000})
  await page.locator('.tool-stats').screenshot({path:'/tmp/dashboard-tools-final.png'})
  await page.locator('.knowledge-stats').screenshot({path:'/tmp/dashboard-files-final.png'})
  await page.getByRole('button', { name: '切换主题', exact: true }).click()
  await page.locator('.knowledge-stats').screenshot({path:'/tmp/dashboard-files-dark.png'})
  await page.getByRole('button', { name: '切换主题', exact: true }).click()
  empty = true
  await page.reload()
  await page.getByText('暂无文件类型数据', {exact:true}).waitFor()
  check(await page.locator('.file-type-chart').count() === 0, '空状态保留旧圆环')
  check(await page.locator('.error-analysis').count() === 0, '空状态保留旧错误数据')
  await page.unrouteAll({behavior:'wait'})
  await page.goto('http://localhost:5173/dashboard?tab=threads')
  await page.getByRole('button', {name:'会话',exact:true}).waitFor()
  check(await page.locator('.explorer-card').count() === 0, '已删除的会话明细表格仍存在')
  check(await page.getByRole('button', {name:'会话分析',exact:true}).count() === 0, '旧 Tab 仍存在')
  return { widths: [1440,1024,768,375], fileTypes: 8, emptyState: true, sessionStatsInOverview: true }
}
