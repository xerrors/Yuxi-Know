// 在已登录的真实页面验证连接器列表入口和详情阅读能力，HTTP 使用固定夹具。
async page => {
  const kb = {
    kb_id: 'feishu-navigation-fixture', name: '飞书导航回归资料', description: '固定测试夹具',
    kb_type: 'feishu', can_manage: true, supports_documents: false,
    additional_params: { feishu_space_id: '123' }, stats: {},
    share_config: { version: 2, read_scope: { access_level: 'global' }, manage_scope: null }
  }
  const originalUrl = page.url()
  const handler = async route => {
    const url = route.request().url().split('?')[0]
    let data
    if (url.endsWith('/knowledge-bases')) data = { knowledge_bases: [kb] }
    else if (url.endsWith('/feishu-navigation-fixture')) data = kb
    else if (url.endsWith('/query-params')) data = { params: { options: [] } }
    else if (url.includes('sample-questions')) data = { questions: [] }
    else return route.continue()
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) })
  }
  await page.route('**/api/knowledge/**', handler)
  try {
    await page.goto('http://localhost:5173/extensions?tab=knowledge', { waitUntil: 'domcontentloaded' })
    const card = page.locator('main .info-card').filter({ hasText: kb.name })
    await card.waitFor()
    if ((await card.getAttribute('class')).includes('info-card-disabled')) throw new Error('飞书详情入口被错误禁用')
    await card.getByText(kb.name, { exact: true }).click()
    await page.waitForURL('**/knowledge-bases/feishu-navigation-fixture**', { waitUntil: 'domcontentloaded', timeout: 5000 })
    await page.locator('main textarea').waitFor()
    if (await page.getByRole('button', { name: '上传', exact: true }).count()) throw new Error('在线阅读错误开放上传')
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.locator('main textarea').waitFor()
    if (!page.url().includes('/feishu-navigation-fixture')) throw new Error('直接访问连接详情被重定向')
    return { catalogNavigation: true, directNavigation: true, queryVisible: true, noUpload: true }
  } finally {
    await page.unroute('**/api/knowledge/**', handler)
    await page.goto(originalUrl, { waitUntil: 'domcontentloaded' })
  }
}
