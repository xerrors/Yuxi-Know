// 独立 Vite 会话：playwright-cli -s=<session> --raw run-code --filename=frontend/test/browser/dashboardOverview.js
// 固定 API fixture 验证真实页面，不接触业务数据；后端实时计数与授权由 HTTP integration 验证。
// prettier-ignore
async page => {
  const check = (condition, message) => { if (!condition) throw new Error(message) }
  await page.waitForLoadState('networkidle')
  const origin = await page.evaluate(() => location.origin)
  const pageErrors = []
  const onError = error => pageErrors.push(error.message)
  page.on('pageerror', onError)
  const callQueries = []
  const agentStatsRequests = []
  const distributionQueries = []
  let distributionFailure = false
  let distributionEmpty = false
  let holdDistribution7 = false
  let releaseDistribution7
  const distribution7Pending = new Promise(resolve => { releaseDistribution7 = resolve })
  let distribution7Responded = false
  let callFailure = false
  let callEmpty = false
  let holdModels = false
  let releaseModels
  const modelsPending = new Promise(resolve => { releaseModels = resolve })
  let modelResponded = false
  let vmFailure = false
  let vmEmpty = false
  let releaseVm
  let releaseInitialDistribution
  const vmPending = new Promise(resolve => { releaseVm = resolve })
  const initialDistributionPending = new Promise(resolve => { releaseInitialDistribution = resolve })
  let holdVm = true
  let holdInitialDistribution = true
  const auditRequests = []
  const threadQueries = []
  const basic = { total_sessions: 320, active_sessions: 85, total_messages: 3840, total_users: 24 }
  const dates = Array.from({ length: 120 }, (_, i) => new Date(Date.UTC(2026, 5, 20 + i)).toISOString().slice(0, 10))
  const names = ['智能助手', '深度研究', '代码助手', '团队知识检索与资料整理助手', '写作助手']
  const agentNames = Object.fromEntries(names.map((name, i) => [`agent-${i}`, name]))
  const counts = [118, 86, 62, 34, 20]
  const threads = {
    summary: { total_threads: 320, active_threads: 124, total_messages: 3840, avg_messages_per_thread: 12 },
    daily_trends: dates.slice(-30).map((date, i) => ({ date, new_threads: i % 5, active_threads: 20 + i % 10 })),
    depth_distribution: { '0 条': 12, '1-2 条': 64, '3-5 条': 80, '6-10 条': 70, '11-20 条': 54, '20+ 条': 40 },
    agent_distribution: names.map((agent_name, i) => ({ agent_id: `agent-${i}`, agent_name, thread_count: counts[i], avg_messages: 12 })),
    top_users: Array.from({ length: 10 }, (_, i) => ({ uid: `fixture-user-${i}`, username: i === 1 ? '名字很长的团队知识库管理员示例' : `示例用户 ${String(i + 1).padStart(2, '0')}`, thread_count: 64 - i * 6, message_count: (64 - i * 6) * 12 }))
  }
  await page.route('**/api/**', async route => {
    const url = route.request().url()
    const path = url.split('?')[0]
    let json = {}
    if (path.endsWith('/api/projects')) json = []
    if (path.endsWith('/api/agent')) json = { agents: [] }
    if (path.endsWith('/system/agent-feedback')) json = { items: [], has_more: false, last_id: null }
    if (path.endsWith('/api/v1/agents/sessions')) json = { data: [], has_more: false }
    if (path.endsWith('/system/info')) json = { success: true, data: { branding: { name: '语析', logo: '/favicon.svg' } } }
    if (path.includes('/dashboard/sessions')) auditRequests.push(path)
    if (path.endsWith('/auth/me')) json = { id: 1, uid: 'dashboard-fixture', username: '布局测试', role: 'superadmin' }
    if (path.endsWith('/check-first-run')) json = { first_run: false }
    if (path.endsWith('/dashboard/stats')) json = basic
    if (path.endsWith('/stats/threads')) threadQueries.push(url)
    if (path.endsWith('/stats/users')) json = { total_users: 24, active_users_24h: 6, active_users_30d: 18, daily_active_users: dates.map((date, i) => ({ date, active_users: i % 7 === 0 ? 0 : i % 12 })) }
    if (path.endsWith('/stats/agents/sessions')) {
      const range = url.split('time_range=')[1]
      distributionQueries.push(range)
      if (holdInitialDistribution) await initialDistributionPending
      if (holdDistribution7 && range === '7days') await distribution7Pending
      if (distributionFailure) return route.fulfill({status:502, json:{detail:'统计不可用'}})
      const count = { all:320, '7days':60, '30days':180, '3months':250 }[range]
      const average = { all:12, '7days':5, '30days':8.5, '3months':10 }[range]
      const distribution = range === 'all' ? threads.agent_distribution : threads.agent_distribution.slice(0,2).map((row,i)=>({...row,thread_count:i===0?Math.floor(count*2/3):count-Math.floor(count*2/3),avg_messages:average}))
      await route.fulfill({json: distributionEmpty ? { total_threads:0,agent_count:0,avg_messages_per_thread:0,agent_distribution:[] } : { total_threads:count,agent_count:distribution.length,avg_messages_per_thread:average,agent_distribution:distribution }})
      if (holdDistribution7 && range === '7days') distribution7Responded = true
      return
    }
    if (path.endsWith('/stats/agents')) agentStatsRequests.push(url)
    if (path.endsWith('/stats/tools')) json = { total_calls: 1280, failed_calls: 12, success_rate: 99.1, most_used_tools: [{ tool_name: 'web_search', count: 560 }, { tool_name: 'knowledge_search', count: 420 }, { tool_name: 'execute_code', count: 300 }], tool_error_distribution: { web_search: 8, execute_code: 4 } }
    if (path.endsWith('/stats/knowledge')) json = { total_knowledge_bases: 6, total_files: 128, total_storage_size: 387973120, file_type_distribution: { PDF: 80, Markdown: 32, DOCX: 16 } }
    if (path.endsWith('/stats/calls/timeseries')) {
      callQueries.push(url.split('?')[1])
      const isModels = url.includes('type=models')
      if (holdModels && isModels) await modelsPending
      if (callFailure) return route.fulfill({ status: 502, json: { detail: '调用统计暂不可用' } })
      json = { total_count: 99999, average_count: 999, data: dates.slice(-14).map((date, i) => ({ date: url.includes('14hours') ? `${date} ${String(i).padStart(2, '0')}:00` : url.includes('14weeks') ? `2026-${i + 27}` : date, data: { 'agent-0': callEmpty ? 0 : isModels ? 999 : i + 5, 'agent-1': callEmpty ? 0 : i % 4 + 3 } })), categories: ['agent-0', 'agent-1'], agent_names: agentNames }
      if (url.includes('type=sessions')) {
        json.categories = ['new_threads', 'active_threads']
        json.data = json.data.map((row, i) => ({ date: row.date, data: { new_threads: callEmpty ? 0 : i % 5, active_threads: callEmpty ? 0 : 20 + i % 10 } }))
      }
      await route.fulfill({ json })
      if (isModels) modelResponded = true
      return
    }
    if (path.endsWith('/stats/vms')) {
      if (holdVm) await vmPending
      if (vmFailure) return route.fulfill({ status: 502, json: { detail: 'VM 统计暂不可用，请重试' } })
      json = vmEmpty ? { active_vms: 0, total_vms: 0 } : { active_vms: 2, total_vms: 7 }
    }
    return route.fulfill({ json })
  })
  await page.evaluate(async () => {
    const { useUserStore } = await import('/src/modules/identity/model/user.js')
    useUserStore().applySession({ access_token: 'dashboard-layout-fixture', username: '布局测试', uid: 'dashboard-fixture', role: 'superadmin' })
  })
  const metric = label => page.locator('.stats-overview-container .dashboard-metric-card').filter({ has: page.getByText(label, { exact: true }) })
  const refresh = () => page.locator('.stats-refresh')
  const waitReady = () => page.waitForFunction(() => document.querySelector('.stats-refresh')?.disabled === false)
  const values = () => page.locator('.call-stats .dashboard-metric-value').allTextContents()
  const graph = () => page.evaluate(async () => {
    const moduleSource = await (await fetch('/src/modules/dashboard/model/dashboardCharts.js')).text()
    const coreUrl = moduleSource.match(/from "([^"\n]*echarts_core[^"\n]*)"/)[1]
    const { getInstanceByDom } = await import(coreUrl)
    const option = getInstanceByDom(document.querySelector('.call-chart')).getOption()
    return { series: option.series.map(s => ({ name: s.name, type: s.type, stack: s.stack, data: s.data })), dates: option.xAxis[0].data }
  })
  try {
    await page.setViewportSize({ width: 1440, height: 1100 })
    await page.goto(`${origin}/dashboard?tab=threads`)
    await page.locator('.call-chart canvas').waitFor()
    check(await page.locator('.dashboard-grid > :first-child').evaluate(el => el.classList.contains('call-stats')), '调用统计未占据主位')
    check(await page.locator('.call-views button[aria-pressed=true]').innerText() === '智能体', '默认调用视图错误')
    check((await values()).join() === '222,15.86,22', '调用周期摘要误用累计接口字段')
    check(await metric('VM 总数').locator('.dashboard-metric-value').innerText() === '…', 'VM 加载中误显示零')
    holdVm = false
    holdInitialDistribution = false
    releaseVm()
    releaseInitialDistribution()
    check(await page.getByText('高频用户', {exact:true}).count() === 0, '高频用户仍存在')
    check(await page.getByText('工具错误分析', {exact:true}).count() === 0, '工具错误分析仍存在')
    check(await page.locator('.error-analysis').count() === 0, '工具错误表格仍存在')
    check(await page.getByText('会话深度', {exact:true}).count() === 0, '会话深度仍存在')
    await page.locator('.conversation-agents li').first().waitFor()
    check((await page.locator('.conversation-agents .dashboard-metric-value').allTextContents()).join() === '5,320,12', '平均消息数未移入分布卡')
    const selectDistributionRange = async label => {
      await page.locator('.conversation-agents .ant-select-selector').click()
      await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({hasText:label}).click()
    }
    const waitDistribution = () => page.waitForFunction(() => document.querySelector('.distribution-refresh')?.disabled === false)
    for (const [label,range,expected] of [['近7天','7days','2,60,5'], ['近30天','30days','2,180,8.5'], ['近3个月','3months','2,250,10'], ['累计','all','5,320,12']]) {
      await selectDistributionRange(label)
      await waitDistribution()
      check(distributionQueries.at(-1) === range, '分布范围请求错误')
      check((await page.locator('.conversation-agents .dashboard-metric-value').allTextContents()).join() === expected, '分布范围摘要未更新')
    }
    holdDistribution7 = true
    await selectDistributionRange('近7天')
    check(await page.locator('.distribution-refresh').isDisabled(), '范围切换加载状态缺失')
    check(await page.locator('.conversation-agents .dashboard-metric-value').count() === 0, '范围切换显示旧摘要')
    check(await page.locator('.conversation-agents li').count() === 0, '范围切换显示旧排行')
    await selectDistributionRange('近30天')
    await waitDistribution()
    releaseDistribution7()
    for (let i=0;!distribution7Responded && i<100;i+=1) await page.waitForTimeout(50)
    check(distribution7Responded, '迟到范围响应未完成')
    await page.waitForTimeout(100)
    check((await page.locator('.conversation-agents .dashboard-metric-value').allTextContents()).join() === '2,180,8.5', '迟到范围响应覆盖新选择')
    await selectDistributionRange('累计')
    await waitDistribution()
    check((await page.locator('.call-views button').allTextContents()).map(text => text.trim()).join() === '智能体,工具,Token,会话,模型', '统计类型未采用简短名称')
    check(await page.locator('.call-views').evaluate(el => !!el.closest('.ant-card-head')), '统计类型未恢复到原头部工具区')
    check(await page.getByText('AI智能体分析', { exact: true }).count() === 0, '重复智能体分析仍存在')
    check(await page.locator('.call-stats .ant-select, .conversation-chart').count() === 0, '旧下拉或独立会话图表仍存在')
    check((await page.locator('.time-ranges button').allTextContents()).map(s => s.trim()).join() === '14小时,14天,14周', '原范围按钮组未恢复')
    await page.getByRole('button', { name: '会话', exact: true }).click()
    await waitReady()
    check((await values()).join() === '26,1.86,4', '新增摘要错误或与活跃会话重复相加')
    for (const [label, range, axisPattern] of [['14小时', '14hours', /^\d{2}:00$/], ['14天', '14days', /^\d{2}-\d{2}$/], ['14周', '14weeks', /^第\d+周$/]]) {
      await page.getByRole('button', { name: label, exact: true }).click()
      await waitReady()
      check(callQueries.at(-1) === `type=sessions&time_range=${range}`, '会话范围未请求对应粒度')
      const chart = await graph()
      check(chart.dates.length === 14 && chart.dates.every(date => axisPattern.test(date)), '会话时间桶标签错误')
      check(chart.series.length === 2 && chart.series.every(s => s.type === 'bar' && !s.stack), '会话没有使用独立分组柱状图')
      check(chart.series.map(s => s.name).join() === '新增会话,活跃会话', '会话序列错误')
      check(chart.series[0].data.join() === Array.from({length:14},(_,i)=>i%5).join(), '图表没有读取真实序列')
    }
    await page.getByRole('button', { name: '智能体', exact: true }).click()
    await waitReady()
    check(callQueries.at(-1) === 'type=agents&time_range=14weeks', 'Tab 切换未沿用公共范围')
    await page.getByRole('button', { name: '14天', exact: true }).click()
    await waitReady()
    holdModels = true
    await page.getByRole('button', { name: '模型', exact: true }).click()
    check(await refresh().isDisabled(), '加载中刷新未禁用')
    await page.getByRole('button', { name: '会话', exact: true }).click()
    await waitReady()
    releaseModels()
    for (let i = 0; !modelResponded && i < 100; i += 1) await page.waitForTimeout(50)
    check(modelResponded, '延迟响应未完成')
    await page.waitForTimeout(100)
    check((await values()).join() === '26,1.86,4', '旧模型数据覆盖会话视图')
    await page.getByRole('button', { name: '智能体反馈', exact: true }).click()
    await page.getByRole('button', { name: '系统概览', exact: true }).click()
    await page.locator('.call-chart canvas').waitFor()
    check(await page.locator('.call-views button[aria-pressed=true]').innerText() === '会话', '概览往返丢失统计 Tab')
    for (const theme of ['light', 'dark']) {
      await page.evaluate(async value => (await import('/src/shared/model/theme.js')).useThemeStore().setTheme(value), theme)
      for (const width of [768,1024,1440,1920]) {
        await page.setViewportSize({ width, height: 1100 })
        await page.waitForTimeout(350)
        check(await page.locator('.dashboard-grid').evaluate(el => el.scrollWidth <= el.clientWidth + 1), `网格溢出 ${theme} ${width}`)
        check(await page.locator('.conversation-agents').evaluate(el => el.scrollWidth <= el.clientWidth + 1), '分布卡溢出')
        check(await page.locator('.conversation-agents .dashboard-metric-label').evaluateAll(labels => labels.every(el => el.scrollWidth <= el.clientWidth + 1)), '分布指标标签被截断')
        check(await page.locator('.call-stats .ant-card-head-title').evaluate(el => el.scrollWidth <= el.clientWidth + 1), '调用统计标题被截断')
        check(await page.locator('.call-stats').evaluate(el => el.scrollWidth <= el.clientWidth + 1), `主卡溢出 ${theme} ${width}`)
        check(await page.locator('.call-chart').evaluate(el => Math.abs(el.clientWidth - parseFloat(el.querySelector('canvas').style.width)) < 2), '图表尺寸未跟随容器')
        if (width >= 1440) {
          const [call, user] = await Promise.all([page.locator('.call-stats').boundingBox(), page.locator('.user-stats').boundingBox()])
          check(Math.abs(call.y - user.y) < 1 && call.width > user.width * 1.5, '用户活跃度未与调用统计保持第一行')
          const cards = await Promise.all(['.conversation-agents', '.tool-stats', '.knowledge-stats'].map(selector => page.locator(selector).boundingBox()))
          check(cards.every(card => Math.abs(card.y - cards[0].y) < 1 && Math.abs(card.width - cards[0].width) < 1), '下方统计卡未一行三列')
        }
        if (width === 1440 || width === 768) {
          await page.locator('.stats-overview-container').scrollIntoViewIfNeeded()
          await page.waitForTimeout(1000)
          await page.screenshot({ path: `/tmp/yuxi-agent-range-${theme}-${width}.png` })
          await page.locator('.conversation-agents').screenshot({path:`/tmp/yuxi-agent-distribution-${theme}-${width}.png`})
        }
      }
    }
    for (const name of ['折叠侧边栏','展开侧边栏']) {
      await page.getByRole('button', { name, exact:true }).click()
      await page.waitForTimeout(400)
      check(await page.locator('.call-chart').evaluate(el => Math.abs(el.clientWidth - parseFloat(el.querySelector('canvas').style.width)) < 2), '侧栏切换未缩放图表')
    }
    for (const [view, label] of [['会话','会话'],['工具','调用']]) {
      await page.getByRole('button', { name: view, exact:true }).click()
      await waitReady()
      callFailure = true
      await refresh().click()
      await page.getByText(`${label}统计暂不可用，请重试`, { exact:true }).waitFor()
      check((await values()).length === 0, '失败显示过期摘要')
      callFailure = false
      callEmpty = true
      await refresh().click()
      await page.getByText(`暂无${label}数据`, { exact:true }).waitFor()
      check((await values()).join() === '0,0,0', '全零桶空态摘要错误')
      callEmpty = false
      await refresh().click()
      await page.locator('.call-chart canvas').waitFor()
    }
    await page.getByRole('button', { name:'会话', exact:true }).click()
    await waitReady()
    distributionFailure = true
    await page.locator('.distribution-refresh').click()
    await page.getByText('智能体会话分布暂不可用，请重试', {exact:true}).waitFor()
    check(await page.locator('.conversation-agents li').count() === 0, '分布失败显示旧排行')
    check(await page.locator('.call-chart canvas').count() === 1, '分布失败影响主图表')
    distributionFailure = false
    distributionEmpty = true
    await page.getByRole('button', {name:'重试智能体会话分布',exact:true}).click()
    await page.locator('.conversation-agents').getByText('暂无会话数据', {exact:true}).waitFor()
    check((await page.locator('.conversation-agents .dashboard-metric-value').allTextContents()).join() === '0,0,0', '分布空态摘要错误')
    distributionEmpty = false
    await page.locator('.distribution-refresh').click()
    await page.locator('.conversation-agents li').first().waitFor()
    vmFailure = true
    await page.getByRole('button', {name:'刷新 VM 统计',exact:true}).click()
    await page.getByText('VM 统计暂不可用，请重试', {exact:true}).waitFor()
    check(await metric('当前活跃 VM').locator('.dashboard-metric-value').innerText() === '—', 'VM 失败显示零')
    vmFailure = false
    vmEmpty = true
    await page.getByRole('button', {name:'重试 VM 统计',exact:true}).click()
    await metric('VM 总数').getByText('0', {exact:true}).waitFor()
    check(auditRequests.length === 0 && agentStatsRequests.length === 0, '仍请求已删除统计')
    check(threadQueries.length === 0, '仍请求已删除高频用户或深度聚合')
    check(pageErrors.length === 0, `浏览器错误：${pageErrors}`)
    return { ranges: ['14hours','14days','14weeks'], distributionRanges:distributionQueries, groupedSessionBars:true, sharedChart:true, themes:2, widths:[768,1024,1440,1920], staleResponseRejected:true, errorEmptyRetry:true, pageErrors }
  } finally {
    releaseDistribution7()
    releaseModels()
    releaseVm()
    releaseInitialDistribution()
    page.off('pageerror', onError)
    await page.unrouteAll({behavior:'wait'})
    await page.evaluate(() => localStorage.removeItem('user_token'))
  }
}
