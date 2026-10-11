// 使用已登录的合成会话 window.__feedbackFixture.targets[0]；仅修改该目标的评价。
// playwright-cli --raw -s=<session> run-code --filename=frontend/test/browser/feedbackPresets.js
// prettier-ignore
async page => {
  const check = (condition, message) => { if (!condition) throw new Error(message) }
  const target = await page.evaluate(() => window.__feedbackFixture.targets[0])
  const origin = await page.evaluate(() => location.origin)
  await page.unrouteAll({ behavior: 'wait' })
  await page.goto(`${origin}/agent/${target.session_id}`)
  const like = page.getByRole('button', { name: '点赞', exact: true })
  await like.waitFor()
  await page.waitForFunction(() => !document.querySelector('button.feedback-vote[aria-label="点赞"]')?.disabled)
  if (await like.getAttribute('aria-pressed') === 'true') {
    await like.click()
    await page.waitForFunction(() => document.querySelector('button.feedback-vote[aria-label="点赞"]')?.getAttribute('aria-pressed') === 'false')
  }
  await like.click()
  const modal = page.getByRole('dialog', { name: '补充反馈' })
  await modal.waitFor()
  await modal.getByRole('button', { name: '解决了我的问题', exact: true }).click()
  await modal.getByRole('button', { name: '快速高效', exact: true }).click()
  const textarea = modal.getByRole('textbox')
  await textarea.fill('测'.repeat(2000))
  await modal.getByRole('alert').filter({ hasText: '合计超过 2000 字' }).waitFor()
  check(await modal.getByRole('button', { name: '提交反馈', exact: true }).isDisabled(), '合计超过上限必须阻止提交')
  const persisted = () => page.evaluate(async target => {
    const response = await fetch(`/api/agent/threads/${target.session_id}/feedback?source=user&run_ids=${target.run_id}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('user_token')}` }
    })
    if (!response.ok) throw new Error('反馈回读失败')
    return (await response.json()).items[0]
  }, target)
  check((await persisted()).reason === null, '超长草稿不能写入已保存评价')
  const text = '预设原因和补充说明一起保存，管理员可以回看。'
  const reason = `解决了我的问题；快速高效\n\n${text}`
  await textarea.fill(text)
  await modal.getByRole('button', { name: '提交反馈', exact: true }).click()
  await modal.waitFor({ state: 'hidden' })
  const record = await persisted()
  check(record.reason === reason, '多选原因及文字应完整持久化')
  check(await page.getByRole('button', { name: /^(补充说明|编辑说明)$/ }).count() === 0, '不能留下二次补充入口')
  await page.goto(`${origin}/dashboard?tab=feedback`)
  const row = page.locator('.feedback-record').filter({ hasText: text })
  await row.getByRole('button', { name: /查看详情|详情/ }).click()
  const detail = page.getByRole('dialog', { name: '反馈详情' })
  await detail.waitFor()
  check((await detail.locator('.detail-reason').textContent()).trim() === reason, '管理员详情应展示全部预设与文字')
  await page.locator('.ant-modal-content').screenshot({ path: '/tmp/yuxi-feedback-presets-detail.png' })
  await page.keyboard.press('Escape')
  return { id: record.id, run_id: target.run_id, rating: record.rating, reason: record.reason, combinedLimit: true, adminDetails: true }
}
