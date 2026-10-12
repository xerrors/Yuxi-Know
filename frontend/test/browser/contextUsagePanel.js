// 在已登录并完成一次对话的 Vite 页面运行；先验证真实工作区，再挂载组件边界夹具。
// prettier-ignore
async (page) => {
  const check = (value, message) => { if (!value) throw new Error(message) }
  const realPanel = page.getByRole('region', { name: '上下文使用情况' })
  if (!await realPanel.isVisible()) await page.getByRole('button', { name: '上下文使用情况', exact: true }).click()
  await realPanel.waitFor({ state: 'visible' })
  if (await realPanel.locator('.token-usage-context-card').getAttribute('aria-expanded') === 'false') await realPanel.locator('.token-usage-context-card').click()
  await realPanel.getByRole('button', { name: '压缩上下文', exact: true }).waitFor({ state: 'visible' })
  check(await realPanel.locator('.token-usage-model-item').count() > 0, '真实回复缺少累计模型用量')
  await page.screenshot({ path: '/tmp/yuxi-session-context-panel.png', animations: 'disabled' })

  await page.evaluate(async () => {
    const mainSource = await (await fetch('/src/app/main.js')).text()
    const vueUrl = mainSource.match(/from "([^"]*\/vue\.js[^"]*)"/)[1]
    const { createApp, h, reactive } = await import(vueUrl)
    const { default: Panel } = await import('/src/modules/session/ui/ContextUsagePanel.vue')
    const state = reactive({
      usage: { next_llm_input_tokens: 90, llm_input_tokens: 60, summary_trigger_tokens: 100,
        system_tokens: 10, tools_tokens: 20, llm_messages_tokens: 30,
        thread: { total: { total_tokens: 2048 }, models: { model: {
          model: { configured_model_spec: 'fixture/model' }, model_call_count: 2,
          usage: { input_tokens: 1024, output_tokens: 1024 },
          cache_observed_call_count: 2, cache_observed_input_tokens: 100, cache_read_input_tokens: 50,
          cache_hit_ratio: 0.5
        } } } },
      compressing: false, compressionDisabled: false
    })
    const host = document.createElement('div')
    host.id = 'context-panel-fixture'
    Object.assign(host.style, { position: 'fixed', inset: '0', zIndex: '99999', padding: '24px', background: 'var(--gray-0)' })
    document.body.append(host)
    const app = createApp({ render: () => h(Panel, { ...state, onCompress: () => { window.__contextFixture.emitted++ } }) })
    window.__contextFixture = { state, app, host, emitted: 0 }
    app.mount(host)
  })
  const fixture = page.locator('#context-panel-fixture')
  const card = fixture.locator('.token-usage-context-card')
  check(await card.getAttribute('aria-expanded') === 'false', '初始状态应折叠')
  await card.click()
  check(await fixture.getByRole('progressbar').getAttribute('aria-valuenow') === '90', '未使用下一轮压力')
  const metrics = fixture.locator('.token-usage-card-metrics > span')
  check(await metrics.filter({ hasText: '累计模型用量' }).locator('strong').innerText() === '2K', '1024 Token 展示单位改变')
  check(await metrics.filter({ hasText: '累计缓存命中率' }).locator('strong').innerText() === '50%', '累计缓存命中率错误')
  await page.evaluate(() => { window.__contextFixture.state.usage.thread.total.total_tokens = 0 })
  check(await fixture.getByText('累计模型用量', { exact: true }).count() === 0, '零累计用量不应显示为已采集指标')
  await page.evaluate(() => { window.__contextFixture.state.usage.thread.total.total_tokens = 2048 })
  check((await fixture.locator('.token-usage-model-stats .is-cache strong').textContent()).trim() === '50 · 50%', '模型缓存统计错误')
  const compress = fixture.getByRole('button', { name: '压缩上下文', exact: true })
  await page.evaluate(() => { window.__contextFixture.state.compressionDisabled = true })
  check(await compress.isDisabled(), '有队列时按钮仍可用')
  await page.evaluate(() => { window.__contextFixture.state.compressionDisabled = false; window.__contextFixture.state.compressing = true })
  check(await fixture.getByRole('button', { name: '正在压缩…', exact: true }).isDisabled(), '压缩中按钮仍可用')
  await page.evaluate(() => { window.__contextFixture.state.compressing = false })
  await compress.click()
  check(await page.evaluate(() => window.__contextFixture.emitted) === 1, '压缩事件未发出或重复')
  await page.evaluate(() => { window.__contextFixture.saved = window.__contextFixture.state.usage; window.__contextFixture.state.usage = null })
  check(await fixture.locator('section').count() === 0, '无遥测时应隐藏面板')
  await page.evaluate(() => { window.__contextFixture.state.usage = window.__contextFixture.saved })
  check(await card.getAttribute('aria-expanded') === 'true', '无遥测切换重置了展开状态')
  await page.evaluate(() => { window.__contextFixture.state.usage = { system_tokens: 10, llm_messages_tokens: 20 } })
  check(await fixture.locator('.token-usage-card-percent').innerText() === '--', '缺失上限不应显示虚假占比')
  check(await fixture.locator('.token-usage-card-metrics').count() === 0, '缺失累计用量不应显示零值指标')
  await page.evaluate(() => { window.__contextFixture.app.unmount(); window.__contextFixture.host.remove(); delete window.__contextFixture })
  return { workspace: 'real reply usage visible', fixture: 'projection, disabled, loading, emit, missing telemetry and expansion preserved' }
}
