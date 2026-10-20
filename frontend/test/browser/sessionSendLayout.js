// 使用 playwright-cli run-code 调用；先进入已登录的新建页并选择可用的真实模型。
// eslint-disable-next-line no-unused-vars -- 浏览器探针入口。
async function verifySessionSendLayout(page, {
  enforce = true,
  prompt = '请用中文写一段约200字的自然风景描写，直接输出正文，不调用任何工具。'
} = {}) {
  await page.getByRole('textbox').fill(prompt)
  await page.evaluate(() => {
    const editor = document.querySelector('main [contenteditable]')
    window.__sendLayoutEditor = editor
    const state = { start: 0, frames: [], presentationFrames: [], violations: [], firstHuman: null, firstOutput: null, outputLengths: [] }
    window.__sendLayoutProbe = state
    let bottomPosition = null
    const sample = () => {
      if (state.start) {
        const t = Math.round(performance.now() - state.start)
        const stage = document.querySelector('main .message-input-stage')
        const currentEditor = document.querySelector('main [contenteditable]')
        const human = document.querySelector('main .message-box.human')
        const answer = document.querySelector('main .assistant-message .message-md')
        const pageLoading = Boolean(document.querySelector('main .session-loading'))
        const replyLoading = Boolean(document.querySelector('main .generating-status'))
        const replyText = document.querySelector('main .generating-text')?.textContent.trim() || ''
        const duplicateQueue = [...document.querySelectorAll('main .queued-request-content')].some(
          (input) => input.textContent.trim() === human?.querySelector('.message-text')?.textContent.trim()
        )
        if (duplicateQueue) state.violations.push({ t, reason: '同一输入同时显示在消息区和底部队列' })
        if (pageLoading && replyLoading) state.violations.push({ t, reason: '页面和回复同时显示加载提示' })
        if (human && pageLoading) state.violations.push({ t, reason: '消息出现后仍显示页面 Loading' })
        if (human && replyText.includes('排队中')) state.violations.push({ t, reason: '首条消息显示短暂排队中间态' })
        const presentation = { pageLoading, replyLoading, duplicateQueue, replyText }
        if (JSON.stringify(presentation) !== JSON.stringify(state.lastPresentation)) {
          state.presentationFrames.push({ t, ...presentation })
          state.lastPresentation = presentation
        }
        const rect = stage?.getBoundingClientRect()
        if (currentEditor !== editor) state.violations.push({ t, reason: '编辑器被卸载或替换' })
        if (human && state.firstHuman === null) state.firstHuman = t
        if (!human && state.firstHuman !== null) state.violations.push({ t, reason: '用户消息出现后消失' })
        if (rect && !document.querySelector('main .bottom.start-screen')) {
          const position = [rect.x, rect.y, rect.width, rect.height].map(Math.round)
          bottomPosition ||= position
          if (position.some((value, i) => Math.abs(value - bottomPosition[i]) > 1)) {
            state.violations.push({ t, reason: '移到底部后输入框继续改变位置或尺寸', position })
          }
          if (JSON.stringify(position) !== JSON.stringify(state.frames.at(-1)?.position)) {
            state.frames.push({ t, position })
          }
        }
        const length = answer?.textContent.length || 0
        if (length && length !== state.outputLengths.at(-1)?.length) {
          state.firstOutput ??= t
          state.outputLengths.push({ t, length })
        }
      }
      state.raf = requestAnimationFrame(sample)
    }
    document.addEventListener('click', (event) => {
      if (event.target.closest('button[aria-label="发送消息"]')) state.start = performance.now()
    }, { capture: true, once: true })
    sample()
  })

  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await page.waitForFunction(() => /\/agent\/.+/.test(location.pathname))
  const sessionPath = new URL(page.url()).pathname.replace('/agent/', '/api/v1/agents/sessions/')
  for (let attempt = 0; attempt < 300; attempt += 1) {
    const status = await page.evaluate(async (path) => {
      const response = await fetch(path, { headers: { Authorization: `Bearer ${localStorage.getItem('user_token')}` } })
      const session = await response.json()
      return session.yuxi?.current_turn?.status
    }, sessionPath)
    if (['completed', 'failed', 'cancelled'].includes(status)) break
    await page.waitForTimeout(200)
  }
  await page.waitForTimeout(300)

  const result = await page.evaluate(async (path) => {
    const state = window.__sendLayoutProbe
    cancelAnimationFrame(state.raf)
    const headers = { Authorization: `Bearer ${localStorage.getItem('user_token')}` }
    const session = await (await fetch(path, { headers })).json()
    const turn = await (await fetch(`${path}/turns/${session.yuxi.current_turn.id}`, { headers })).json()
    const items = await (await fetch(`${path}/turns/${turn.id}/items`, { headers })).json()
    const run = turn.yuxi.runs.find((run) => run.id === turn.yuxi.result_run_id)
    const output = items.data.filter((item) => item.role === 'assistant' && item.yuxi?.run_id === run?.id)
    return {
      frames: state.frames, presentationFrames: state.presentationFrames,
      violations: state.violations, firstHuman: state.firstHuman,
      firstOutput: state.firstOutput, outputLengths: state.outputLengths,
      sessionPath: path, status: session.status, resultRunId: run?.id,
      firstOutputAt: run?.first_output_at,
      finalText: output.flatMap((item) => item.content || []).map((part) => part.text || '').join(''),
      humanCount: document.querySelectorAll('main .message-box.human').length,
      outputCount: document.querySelectorAll('main .assistant-message .message-md').length
    }
  }, sessionPath)

  if (enforce) {
    if (result.violations.length) throw new Error(JSON.stringify(result))
    if (result.status !== 'completed' || !result.resultRunId || !result.firstOutputAt || !result.finalText) {
      throw new Error(`真实 Run 未完成并持久化最终输出：${JSON.stringify(result)}`)
    }
    if (result.outputLengths.length < 3 || result.humanCount !== 1 || result.outputCount !== 1) {
      throw new Error(`未观察到连续流式输出或消息重复：${JSON.stringify(result)}`)
    }
    const editor = page.getByRole('textbox')
    await editor.fill('正式会话的未发送草稿')
    await page.getByRole('link', { name: '新建对话', exact: true }).click()
    await page.locator('.bottom.start-screen').waitFor()
    if (await page.getByRole('textbox').innerText()) throw new Error('新建页继承了正式会话草稿')
    await page.goBack()
    await page.waitForFunction(() => document.querySelector('main [contenteditable]')?.textContent === '正式会话的未发送草稿')
    if (!await page.evaluate(() => document.querySelector('main [contenteditable]') === window.__sendLayoutEditor)) {
      throw new Error('返回正式会话没有恢复原编辑器实例')
    }
    await page.reload()
    await page.waitForFunction(() => document.querySelector('main [contenteditable]')?.textContent === '正式会话的未发送草稿')
  }
  return result
}
