// 已登录开发页面后运行：playwright-cli -s=modelcheck run-code --filename=frontend/test/browser/modelCheckButton.js
async (page) => {
  const check = (value, message) => { if (!value) throw new Error(message) }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.locator('.user-info-dropdown').click()
  await page.getByRole('menuitem', { name: '设置', exact: true }).click()
  await page.locator('.settings-sider').getByText('基本设置', { exact: true }).click()
  const row = page.locator('.setting-row').filter({ has: page.getByText('默认对话模型', { exact: true }) })
  const button = row.locator('.status-check-button')
  const initialWidth = (await button.boundingBox()).width
  check((await button.textContent()).trim().replace(/\s/g, '') === '检查', '初始按钮显示检查')
  let release, gate, requests = 0, status
  const routePattern = '**/api/system/model-providers/models/status?*'
  await page.route(routePattern, async (route) => {
    requests += 1
    await gate
    await route.fulfill({ json: { success: true, data: { status, message: '测试结果详情' } } })
  })
  try {
    for (const nextStatus of ['available', 'unavailable', 'available']) {
      status = nextStatus
      gate = new Promise((resolve) => { release = resolve })
      const beforeRequests = requests
      await button.click()
      await button.locator('.yuxi-loading').waitFor()
      check(await button.getAttribute('aria-busy') === 'true', '检查中暴露 busy 状态')
      check(await button.isDisabled(), '检查中禁用重复点击')
      check((await button.textContent()).trim() === '', 'loading 替换文字，不出现检查中')
      check(await button.locator('.yuxi-loading > div').count() === 5, '使用 Yuxi 五竖线 loading')
      check(await row.locator('.model-status-indicator').count() === 0, '没有重复状态图标')
      check((await button.boundingBox()).width === initialWidth, 'loading 不改变按钮宽度')
      await button.evaluate((node) => node.click())
      check(requests === beforeRequests + 1, '等待期间重复点击不重复请求')
      if (nextStatus === 'available') await row.screenshot({ path: '/tmp/yuxi-model-check-loading.png' })
      release()
      const label = nextStatus === 'available' ? '通过' : '异常'
      await button.getByText(label, { exact: true }).waitFor()
      check(await button.isEnabled(), '结果按钮允许再次测试')
      check((await button.boundingBox()).width === initialWidth, '结果文字不改变按钮宽度')
      check((await button.getAttribute('title')).includes('测试结果详情；点击重新检查'), '保留详情和重试提示')
      const token = nextStatus === 'available' ? '--color-success-700' : '--color-error-700'
      const expected = await button.evaluate((node, token) => {
        if (!getComputedStyle(node).getPropertyValue(token).trim()) throw new Error('状态色 token 必须存在')
        const probe = document.createElement('span')
        probe.style.color = `var(${token})`
        node.appendChild(probe)
        const color = getComputedStyle(probe).color
        probe.remove()
        return color
      }, token)
      // 等待已有的颜色过渡完成，避免把动画中间值当成最终状态色。
      await page.waitForFunction((expected) => {
        const node = document.querySelector('.status-check-button')
        return node && getComputedStyle(node).color === expected
      }, expected)
      if (nextStatus === 'unavailable') await row.screenshot({ path: '/tmp/yuxi-model-check-error.png' })
    }
    await row.screenshot({ path: '/tmp/yuxi-model-check-passed.png' })
    await page.evaluate(async () => {
      const { useThemeStore } = await import('/src/shared/model/theme.js')
      window.modelCheckOriginalTheme = useThemeStore().themeMode
      useThemeStore().setTheme('dark')
    })
    await page.setViewportSize({ width: 768, height: 1000 })
    check(await button.isEnabled(), '深色窄屏结果仍可再次测试')
    await row.screenshot({ path: '/tmp/yuxi-model-check-dark-768.png' })
    return { requests, states: ['检查', 'loading', '通过', '异常', '通过'], width: initialWidth, retryable: true }
  } finally {
    release?.()
    await page.unrouteAll({ behavior: 'wait' })
    await page.evaluate(async () => {
      const { useThemeStore } = await import('/src/shared/model/theme.js')
      useThemeStore().setTheme(window.modelCheckOriginalTheme || 'light')
      delete window.modelCheckOriginalTheme
    })
    await page.setViewportSize({ width: 1440, height: 1000 })
  }
}
