// 已登录开发页面运行；列表和迟到失败使用明确合成响应，不写入真实业务数据。
// playwright-cli -s=<session> --raw run-code --filename=frontend/test/browser/feedbackSimplification.js
// prettier-ignore
async page => {
  const check = (value, message) => { if (!value) throw new Error(message) }
  const origin = await page.evaluate(() => location.origin)
  const savedMode = await page.evaluate(() => localStorage.getItem('theme'))
  const viewport = page.viewportSize()
  const reason = '这是合成验收的改进线索，用于检查完整正文、详情布局和焦点。'.repeat(100)
  const items = ['first', 'second'].map(name => ({
    id: `feedback-display-${name}`, run_id: `run-display-${name}`, source: 'agent', rating: null, reason,
    created_at: '2026-10-11T00:00:00Z', updated_at: '2026-10-11T00:00:00Z',
    agent_id: 'display-fixture', agent_name: `合成验收 ${name}`, session_id: `thread-display-${name}`,
    turn_id: `turn-display-${name}`, run_status: 'completed'
  }))
  const sessionUrl = '**/api/v1/agents/sessions/thread-display-first'
  const listUrl = '**/api/system/agent-feedback?*'
  const details = page.getByRole('dialog', { name: '反馈详情' })
  const setMode = mode => page.evaluate(async mode => {
    const { useThemeStore } = await import('/src/shared/model/theme.js')
    useThemeStore().setTheme(mode)
  }, mode)
  let release
  try {
    await page.route(listUrl, route => route.fulfill({ json: { items, has_more: false, last_id: items[1].id } }))
    await page.goto(`${origin}/dashboard?tab=feedback`)
    await page.reload()
    await page.locator('.record-details').first().waitFor()
    await page.locator('.record-details').first().click()
    await details.waitFor()
    check((await details.locator('.detail-reason').textContent()).trim() === reason, '完整说明被截断')
    for (const label of ['智能体 ID', '会话 ID', '轮次 ID', '执行 ID', '记录 ID', '执行状态']) {
      check(await details.getByText(label, { exact: true }).count() === 0, `仍存在冗余字段：${label}`)
    }
    check(await details.getByText('记录时间', { exact: true }).isVisible(), '记录时间丢失')
    for (const [mode, width] of [['light', 1440], ['dark', 1440], ['light', 375]]) {
      await setMode(mode)
      await page.setViewportSize({ width, height: 900 })
      await page.waitForFunction(() => {
        const box = document.querySelector('.ant-modal-content')?.getBoundingClientRect()
        return box && box.left >= 0 && box.right <= innerWidth + 1
      })
      await page.locator('.ant-modal-content').screenshot({ path: `/tmp/yuxi-feedback-simple-${mode}-${width}.png`, animations: 'disabled' })
    }
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.route(sessionUrl, async route => {
      await new Promise(resolve => { release = resolve })
      await route.fulfill({ status: 503, json: { detail: '旧详情请求失败' } })
    })
    const requested = page.waitForRequest(request => request.url().endsWith('/thread-display-first'))
    await details.getByRole('button', { name: '查看原会话', exact: true }).click()
    await requested
    await details.locator('.ant-modal-close').click()
    await details.waitFor({ state: 'hidden' })
    await page.locator('.record-details').nth(1).click()
    await details.waitFor()
    const responded = page.waitForResponse(response => response.url().endsWith('/thread-display-first'))
    release()
    await responded
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    check(await details.getByRole('alert').count() === 0, '旧详情失败污染新详情')
    check(await details.getByText('合成验收 second', { exact: true }).isVisible(), '新详情被旧请求替换')
    await details.locator('.ant-modal-close').click()
    await details.waitFor({ state: 'hidden' })
    return { fullReason: true, internalMetadataRemoved: true, widths: [1440, 375], modes: ['light', 'dark'], staleErrorIgnored: true }
  } finally {
    release?.()
    await page.unroute(listUrl)
    await page.unroute(sessionUrl)
    await page.setViewportSize(viewport)
    await setMode(savedMode ?? 'light')
    if (savedMode === null) await page.evaluate(() => localStorage.removeItem('theme'))
  }
}
