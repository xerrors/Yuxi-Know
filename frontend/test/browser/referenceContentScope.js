// 在已登录的开发页面运行：playwright-cli -s=references run-code --filename=frontend/test/browser/referenceContentScope.js
async (page) => {
  const check = (value, message) => { if (!value) throw new Error(message) }
  await page.getByRole('button', { name: '关闭设置', exact: true }).click()
  await page.evaluate(async () => {
    const { h, render } = await import('/node_modules/.vite/deps/vue.js')
    const { default: MarkdownPreview } = await import('/src/modules/workspace/ui/MarkdownPreview.vue')
    const { useThemeStore } = await import('/src/shared/model/theme.js')
    const theme = useThemeStore()
    const originalTheme = theme.themeMode
    theme.setTheme('light')
    const content = [
      '# 标题', '', '文字结论含 `code` 与 $x$。', '', '- [x] 列表文字', '',
      '![图片](data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==)', '',
      '| 项目 | 结果 |', '| --- | --- |', '| A | B |', '',
      '```python', 'print(1)', '```', '', '$$', 'x^2', '$$', '',
      '```widget', '{"type":"Card","children":[{"type":"Text","value":"组件文字不标注"}]}', '```', '', '后续结论。', '',
      '<div data-reference-start="3" data-reference-end="3">HTML 预览不标注</div>'
    ].join('\n')
    const citations = [[3, 3], [5, 5], [7, 7], [9, 11], [25, 25], [14, 14], [18, 18], [22, 22], [3, 25]].map(
      ([start, end]) => ({
        answer_start_line: start, answer_end_line: end, source_id: 's1', quote: '测试证据',
        source: { kind: 'web', title: '测试来源', url: 'https://example.org/reference' }
      })
    )
    const host = document.createElement('div')
    host.id = 'reference-scope-probe'
    host.style.cssText = 'position:fixed;inset:0;z-index:9999;overflow:auto;padding:24px;background:var(--gray-0);color:var(--color-text)'
    document.body.appendChild(host)
    const vnode = h(MarkdownPreview, { content, references: citations, widgets: true, codeCopy: true })
    vnode.appContext = document.querySelector('#app').__vue_app__._context
    render(vnode, host)
    window.setReferenceProbeTheme = (mode) => theme.setTheme(mode)
    window.cleanupReferenceProbe = () => { render(null, host); host.remove(); theme.setTheme(originalTheme) }
  })
  try {
    const root = page.locator('#reference-scope-probe')
    await root.locator('.reference-citation').first().waitFor()
    await root.getByText('组件文字不标注', { exact: true }).waitFor()
    check(await root.locator('.reference-citation').count() === 5, '仅正文、列表、图片、表格和后续正文有标注')
    check(await root.locator('[data-reference-excluded] .reference-citation').count() === 0, '代码、公式和组件没有标注')
    check(await root.locator('.widget-preview-render .reference-citation').count() === 0, '组件内部文字不参与标注')
    check(await root.getByText('HTML 预览不标注', { exact: true }).locator('.reference-citation').count() === 0, 'HTML 内部自带范围也不能参与标注')
    check(await root.locator('tr .reference-citation').count() === 1, '表格引用落在对应末行')
    check(await root.locator('.task-list-item .reference-citation').count() === 1, '任务列表文字保持标注')
    check(await root.locator('[data-reference-start="25"] .reference-citation').count() === 1, '过滤不改变后续原始行号')
    await root.screenshot({ path: '/tmp/yuxi-reference-content-scope-light.png' })
    await page.evaluate(() => window.setReferenceProbeTheme('dark'))
    await page.setViewportSize({ width: 768, height: 1000 })
    check(await root.evaluate((node) => node.scrollWidth <= node.clientWidth), '768px 无横向溢出')
    await root.screenshot({ path: '/tmp/yuxi-reference-content-scope-dark-768.png' })
    return { citations: 5, excludedBadges: 0, taskList: true, originalLine: 25, widths: [1440, 768] }
  } finally {
    await page.evaluate(() => { window.cleanupReferenceProbe(); delete window.cleanupReferenceProbe; delete window.setReferenceProbeTheme })
    await page.setViewportSize({ width: 1440, height: 1000 })
  }
}
