// 用固定 HTTP 结果验证 OCR 风格编辑和一键 Search/Fetch 测试。
async page => {
  const check = (condition, message) => { if (!condition) throw new Error(message) }
  const origin = page.url().split('/').slice(0, 3).join('/')
  const names = { tavily: ['Tavily', 'TAVILY_API_KEY'], deepseek: ['DeepSeek', 'DEEPSEEK_API_KEY'], doubao: ['豆包 Custom', 'DOUBAO_SEARCH_API_KEY'] }
  const options = ['tavily', 'deepseek', 'doubao'].map(id => ({
    key: `${id}_search_opts`, name: names[id][0], params: { provider: { id, supports_fetch: id !== 'doubao', environment: names[id][1] } }, value: { api_key: '' },
    sensitive_state: { api_key: { configured: id !== 'doubao', source: id === 'tavily' ? 'environment' : id === 'deepseek' ? 'database' : 'none', preview: id === 'deepseek' ? 'de*******ey' : null } }
  }))
  const writes = []
  const tests = []
  let modes = { search: 'success', fetch: 'success' }
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = '/' + request.url().split('/').slice(3).join('/').split('?')[0]
    const respond = body => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
    if (path.endsWith('/config/options')) return respond({ options })
    if (path.endsWith('/config')) return respond({ web_search_provider: 'tavily', web_fetch_provider: 'deepseek' })
    if (path.includes('/config/options/')) {
      const data = request.postDataJSON()
      writes.push(data)
      const option = options.find(item => path.endsWith(item.key))
      option.sensitive_state.api_key = data.value.api_key
        ? { configured: true, source: 'database', preview: 'ne*******ey' }
        : { configured: true, source: 'environment' }
      return respond({ option })
    }
    if (path.includes('/web-tools/')) {
      const payload = request.postDataJSON()
      const operation = path.includes('/fetch/') ? 'fetch' : 'search'
      tests.push({ operation, ...payload })
      const mode = modes[operation]
      if (mode.startsWith('slow-')) await page.waitForTimeout(1000)
      if (mode.endsWith('error')) return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'web_provider_rejected', message: '供应商余额不足' } }) })
      if (operation === 'fetch') return respond({ content: '# Fixture body' })
      return respond({ results: modes[operation] === 'empty' ? [] : [{ title: 'Fixture article', url: 'https://example.com' }] })
    }
    return respond({})
  })
  await page.goto(`${origin}/test/browser/webSearchSettings.html`)
  const panel = page.locator('.web-settings')
  const cards = panel.locator('.settings-service-card')
  await cards.nth(0).locator('input').waitFor()
  check(await cards.count() === 3, '供应商卡片数量错误')
  check(await cards.locator('input:not([disabled])').count() === 0, '默认界面仍有可编辑测试表单')
  check(!/保存 Key|清除已保存|测试搜索|测试 Fetch/.test(await panel.innerText()), '旧操作仍存在')
  const tavily = cards.nth(0)
  const deepseek = cards.nth(1)
  const doubao = cards.nth(2)
  await tavily.hover()
  check((await tavily.locator('input').inputValue()).includes('TAVILY_API_KEY'), '没有使用 OCR 风格的环境变量显示')
  await tavily.getByRole('button', { name: /测\s*试$/ }).click()
  await tavily.getByText('搜索通过', { exact: true }).waitFor()
  await tavily.getByText('Fetch通过', { exact: true }).waitFor()
  check(writes.length === 0 && tests.length === 2, '一键测试写了配置或未检查两个能力')
  check(tests.find(item => item.operation === 'search').query === 'Python 官方文档', '未使用固定搜索词')
  check(tests.find(item => item.operation === 'fetch').url === 'https://docs.python.org/3/tutorial/index.html', '未使用固定文档')
  check(!(await panel.innerText()).includes('Fixture article') && !(await panel.innerText()).includes('Fixture body'), '测试返回内容仍在界面展示')

  await tavily.getByRole('button', { name: /^编\s*辑$/ }).click()
  check(await tavily.getByRole('button', { name: /测\s*试$/ }).isDisabled(), '空编辑草稿使用旧 Key 冒充测试')
  await tavily.locator('input[type=password]').fill('draft-key')
  modes = { search: 'slow-success', fetch: 'slow-error' }
  await tavily.getByRole('button', { name: /测\s*试$/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('.test-state.running').length === 2)
  check(await tavily.getByRole('button', { name: /测\s*试$/ }).isDisabled(), '测试期间允许重复点击')
  check(await tavily.getByRole('button', { name: /^保\s*存$/ }).isDisabled(), '测试期间允许修改配置')
  await tavily.getByText('搜索通过', { exact: true }).waitFor()
  await tavily.getByText('Fetch失败：供应商余额不足', { exact: true }).waitFor()
  check(tests.slice(-2).every(item => item.api_key === 'draft-key'), '测试没有使用编辑中的 Key')
  check(writes.length === 0, '草稿测试自动保存了 Key')
  await tavily.getByRole('button', { name: /^保\s*存$/ }).click()
  await tavily.getByRole('button', { name: /^编\s*辑$/ }).waitFor()
  check(writes[0].value.api_key === 'draft-key', '编辑保存失败')
  check(await tavily.locator('input').inputValue() === 'ne*******ey', '保存后没有恢复脱敏查看状态')
  await tavily.getByRole('button', { name: /^编\s*辑$/ }).click()
  await tavily.getByRole('button', { name: /^保\s*存$/ }).click()
  check(writes[1].value.api_key === '', '空白保存没有遵循 OCR 的清除规则')
  await tavily.getByRole('button', { name: /^编\s*辑$/ }).waitFor()
  check((await tavily.locator('input').inputValue()).includes('TAVILY_API_KEY'), '清除后没有恢复环境配置')

  await deepseek.hover()
  await deepseek.getByRole('button', { name: /^编\s*辑$/ }).click()
  await deepseek.locator('input[type=password]').fill('cancelled-key')
  await deepseek.getByRole('button', { name: /^取\s*消$/ }).click()
  check(writes.length === 2 && await deepseek.locator('input').inputValue() === 'de*******ey', '取消编辑修改了配置')
  await doubao.hover()
  check(await doubao.getByRole('button', { name: /测\s*试$/ }).isDisabled(), '无 Key 仍允许测试')
  await doubao.getByRole('button', { name: /^编\s*辑$/ }).click()
  await doubao.locator('input[type=password]').fill('doubao-draft')
  modes = { search: 'success', fetch: 'success' }
  const before = tests.length
  await doubao.getByRole('button', { name: /测\s*试$/ }).click()
  await doubao.getByText('搜索通过', { exact: true }).waitFor()
  check(tests.length === before + 1 && tests.at(-1).operation === 'search', '豆包意外调用 Fetch')
  await doubao.getByRole('button', { name: /^取\s*消$/ }).click()
  check(await doubao.locator('.test-summary').count() === 0, '取消后仍展示已丢弃草稿的测试结果')
  modes.search = 'empty'
  await tavily.hover()
  await tavily.getByRole('button', { name: /测\s*试$/ }).click()
  await tavily.getByText('搜索失败：未返回搜索结果', { exact: true }).waitFor()
  await tavily.getByText('Fetch通过', { exact: true }).waitFor()
  modes.search = 'success'
  await tavily.getByRole('button', { name: /测\s*试$/ }).click()
  await tavily.getByText('搜索通过', { exact: true }).waitFor()
  await page.setViewportSize({ width: 1200, height: 1000 })
  await page.evaluate(() => {
    document.activeElement?.blur()
    document.querySelectorAll('.ant-modal-wrap, .ant-modal-body, .settings-content-wrapper, .settings-content').forEach(el => { el.scrollTop = 0 })
  })
  await page.waitForFunction(() => document.querySelectorAll('.ant-message-notice').length === 0)
  await tavily.hover()
  await page.screenshot({ path: '/tmp/yuxi-web-search-simple-light.png', fullPage: true, animations: 'disabled' })
  await page.evaluate(() => window.webSettingsTheme.setTheme('dark'))
  await page.waitForFunction(() => getComputedStyle(document.querySelector('.ant-select-selector')).backgroundColor === 'rgb(3, 3, 3)')
  await page.screenshot({ path: '/tmp/yuxi-web-search-simple-dark.png', fullPage: true, animations: 'disabled' })
  await page.setViewportSize({ width: 768, height: 1000 })
  check(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1), '窄屏出现横向溢出')
  await panel.evaluate(el => { el.style.maxWidth = '500px' })
  await page.waitForFunction(() => {
    const actions = [...document.querySelectorAll('.settings-service-actions')]
    return actions.length === 3 && actions.every(el => getComputedStyle(el).opacity === '1')
  })
  await panel.evaluate(el => el.style.removeProperty('max-width'))
  await page.screenshot({ path: '/tmp/yuxi-web-search-simple-narrow.png', fullPage: true, animations: 'disabled' })
  await page.unroute('**/api/**')
  return { configurationWrites: writes.length, requests: tests.length, screenshots: 3 }
}
