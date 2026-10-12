async (page) => {
  const origin = await page.evaluate(() => location.origin)
  const browser = page.context().browser()
  const evidence = 'docs/vibe/gui-fixes-evidence'
  const check = (condition, message) => { if (!condition) throw new Error(message) }
  const contexts = []
  try {
    const slowContext = await browser.newContext({ viewport: { width: 1280, height: 800 } })
    contexts.push(slowContext)
    const slow = await slowContext.newPage()
    let release
    await slow.route('**/src/pages/EmptyView.vue*', async (route) => {
      if (route.request().url().includes('type=')) return route.continue()
      const response = await route.fetch()
      await new Promise((resolve) => { release = resolve })
      await route.fulfill({ response })
    })
    await slow.goto(`${origin}/route-loading-proof`, { waitUntil: 'domcontentloaded' })
    await slow.locator('.route-loading').waitFor({ state: 'visible' })
    check(await slow.locator('.ant-skeleton').count() === 0, '首屏仍显示通用正文骨架')
    const feedback = slow.getByRole('status').filter({ hasText: '正在打开页面' })
    await feedback.waitFor({ state: 'visible' })
    check(await feedback.evaluate((node) => getComputedStyle(node).animationDelay) === '0.15s', '快速首屏缺少短暂延迟')
    await slow.waitForFunction(() => getComputedStyle(document.querySelector('.route-feedback--loading')).opacity === '1')
    await slow.screenshot({ path: `${evidence}/route-loading-light.png` })
    await slow.evaluate(async () => {
      const { useThemeStore } = await import('/src/shared/model/theme.js')
      useThemeStore().setTheme('dark')
    })
    await slow.setViewportSize({ width: 375, height: 812 })
    await slow.screenshot({ path: `${evidence}/route-loading-dark-mobile.png` })
    await slow.getByText('加载时间较长，请检查网络连接后重试。').waitFor()
    check(await slow.getByText('页面加载失败', { exact: true }).count() === 0, '慢加载被伪装为失败')
    await slow.screenshot({ path: `${evidence}/route-loading-slow.png` })
    release()
    await slow.getByText('404 - 页面不存在', { exact: true }).waitFor()
    check(await slow.locator('.route-loading').count() === 0, '页面挂载后加载占位未移除')

    const initialErrorContext = await browser.newContext({ viewport: { width: 375, height: 812 } })
    contexts.push(initialErrorContext)
    const initialError = await initialErrorContext.newPage()
    await initialError.route('**/src/pages/EmptyView.vue*', (route) => route.abort('failed'))
    await initialError.goto(`${origin}/route-loading-proof`, { waitUntil: 'domcontentloaded' })
    await initialError.getByRole('alert').waitFor()
    check(await initialError.getByText('页面加载失败', { exact: true }).count() === 1, '首屏模块失败没有明确提示')
    check(await initialError.locator('.route-loading').count() === 0, '失败后仍显示加载动画')
    await initialError.screenshot({ path: `${evidence}/route-loading-error-mobile.png` })
    await initialError.unroute('**/src/pages/EmptyView.vue*')
    await initialError.getByRole('button', { name: '重新加载', exact: true }).click()
    await initialError.getByText('404 - 页面不存在', { exact: true }).waitFor()

    const navigationContext = await browser.newContext({ viewport: { width: 1280, height: 800 } })
    contexts.push(navigationContext)
    const navigation = await navigationContext.newPage()
    await navigation.goto(`${origin}/login`)
    await navigation.getByText('欢迎登录', { exact: true }).waitFor()
    check(await navigation.locator('.route-loading, .route-error').count() === 0, '快速导航结束后留下占位')
    let reject
    let markRequested
    const requested = new Promise((resolve) => { markRequested = resolve })
    await navigation.route('**/src/pages/EmptyView.vue*', async (route) => {
      await new Promise((resolve) => { reject = resolve; markRequested() })
      await route.abort('failed')
    })
    await navigation.evaluate(async () => {
      const router = document.querySelector('#app').__vue_app__.config.globalProperties.$router
      void router.push('/route-loading-proof').catch(() => {})
    })
    await requested
    check(await navigation.getByText('欢迎登录', { exact: true }).isVisible(), '导航等待期间原页面被替换')
    check(await navigation.locator('.route-loading').count() === 0, '切换页面重新显示全屏占位')
    reject()
    await navigation.getByRole('alert').waitFor()
    check(await navigation.getByText('欢迎登录', { exact: true }).isVisible(), '导航失败后原页面丢失')
    await navigation.screenshot({ path: `${evidence}/route-loading-navigation-error.png` })
    await navigation.unroute('**/src/pages/EmptyView.vue*')
    await navigation.getByRole('button', { name: '重新加载', exact: true }).click()
    await navigation.getByText('404 - 页面不存在', { exact: true }).waitFor()
    check(await navigation.evaluate(() => location.pathname) === '/route-loading-proof', '恢复按钮重新加载了旧页面而非失败目标')
    check(await navigation.locator('.route-error').count() === 0, '恢复后错误提示未消失')
    return 'PASS: initial delay, light/dark/mobile, long wait, module failure, preserved page and failed-target reload'
  } finally {
    await Promise.all(contexts.map((context) => context.close()))
  }
}
