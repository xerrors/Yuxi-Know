// fixture 含前导空行、SVG、引用块/顶层相同的 html:preview；引用第 5/19 行，来源为带远端 file_id 的 Dify。
// 已登录并打开该持久会话后运行：playwright-cli run-code --filename=frontend/test/browser/turnReferenceBoundaries.js
// prettier-ignore
async (page) => {
  const check = (value, message) => { if (!value) throw new Error(message) }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.reload()
  const show = page.getByRole('button', { name: '显示标注', exact: true }).first()
  if (await show.isVisible()) await show.click()
  const badges = page.locator('.reference-citation')
  await badges.first().waitFor()
  check(await badges.count() === 2, '前导空行不能丢失引用')
  const blocks = page.locator('p.reference-answer-highlight')
  check(await blocks.nth(0).getAttribute('data-source-start') === '5', '知识引用必须对应原始第 5 行')
  check(await blocks.nth(1).getAttribute('data-source-start') === '19', '预览之后的网页引用必须对应原始第 19 行')
  check(await page.locator('.svg-inline-render svg').count() === 1, '标注不能将 SVG 变成代码块')
  const topCode = page.locator('.message-md > [data-source-start="15"]')
  check(await page.locator('.message-md iframe').count() === 0, '旧HTML围栏不能创建预览')
  check((await topCode.innerText()).includes('网页图示'), '旧HTML围栏源码应可读')
  check(await page.locator('blockquote pre code').count() === 1, '嵌套旧围栏也显示源码')
  await badges.nth(0).click()
  const dialog = page.getByRole('dialog')
  await dialog.waitFor()
  check(await dialog.getByText('知识库证据', { exact: true }).isVisible(), '远端文档必须显示证据片段')
  check(await dialog.getByText('此来源暂不支持原文行定位。', { exact: true }).isVisible(), '不能伪造远端文档行号')
  check(await dialog.getByText('文件加载失败', { exact: false }).count() === 0, '只读连接器不能进入本地文档读取错误')
  await page.screenshot({ path: '/tmp/yuxi-turn-refs-connector.png', fullPage: true })
  await dialog.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: '隐藏标注', exact: true }).first().click()
  await badges.first().waitFor({ state: 'detached' })
  check(await badges.count() === 0, '隐藏标注必须移除角标')
  check(await page.locator('.svg-inline-render svg').count() === 1, '隐藏标注仍保留 SVG')
  check(await page.locator('.message-md iframe').count() === 0, '隐藏标注仍不创建旧预览')
  await page.getByRole('button', { name: '显示标注', exact: true }).first().click()
  await badges.first().waitFor()
  check(await topCode.getAttribute('data-source-start') === '15', '旧围栏源码保留原始行映射')
  await page.screenshot({ path: '/tmp/yuxi-turn-refs-rich-answer.png', fullPage: true })
  return { rawLines: [5, 19], svg: true, legacyHtmlAsCode: true, mixedHierarchy: true, readonlyConnector: 'snippet' }
}
