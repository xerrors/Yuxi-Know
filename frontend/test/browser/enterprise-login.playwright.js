// 使用 playwright-cli run-code --filename 调用；fixture 只验证前端，真实 OIDC 另行联调。
// eslint-disable-next-line no-unused-vars -- playwright-cli 调用函数表达式。
async function verifyEnterpriseLoginAndWorkspace(page) {
  const origin = await page.evaluate(() => location.origin)
  let oidcEnabled = true
  await page.addInitScript(() => localStorage.removeItem('user_token'))
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const respond = (body) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
    if (url.includes('/system/health')) return respond({ status: 'ok' })
    if (url.includes('/check-first-run')) return respond({ first_run: false })
    if (url.includes('/oidc/'))
      return respond({ enabled: oidcEnabled, provider_name: '企业统一登录' })
    if (url.endsWith('/system/info'))
      return respond({
        success: true,
        data: { organization: { name: 'Yuxi', avatar: '/favicon.svg' } }
      })
    if (url.endsWith('/auth/me'))
      return respond({
        id: 1,
        uid: 'fixture',
        username: 'Fixture user',
        role: 'user',
        department_id: 1
      })
    if (url.includes('/api/v1/agents/sessions')) return respond({ data: [], has_more: false })
    if (url.includes('/workspace/tree')) return respond({ entries: [], path: '/' })
    if (url.includes('/knowledge')) return respond({ knowledge_bases: [] })
    return respond([])
  })
  await page.goto(origin + '/login')
  await page.getByRole('button', { name: '企业统一登录', exact: true }).waitFor()
  await page.locator('input[type="password"]').waitFor()
  await page.screenshot({ path: '/tmp/yuxi-enterprise-login.png', fullPage: true })
  oidcEnabled = false
  await page.reload()
  await page.locator('input[type="password"]').waitFor()
  await page.waitForLoadState('networkidle')
  if (await page.locator('.third-party-login').count())
    throw new Error('无 OIDC 时仍显示第三方区域')
  return {
    passed: [
      'OIDC and password entries',
      'optional SSO hidden'
    ]
  }
}
