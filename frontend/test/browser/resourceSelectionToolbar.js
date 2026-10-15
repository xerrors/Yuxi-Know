// 真实 Vite 页面执行：playwright-cli -s=<session> run-code --filename=frontend/test/browser/resourceSelectionToolbar.js
// prettier-ignore
async page => {
  const check = (value, message) => { if (!value) throw new Error(message) }
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.evaluate(async () => {
    const main = await (await fetch('/src/app/main.js')).text()
    const { createApp, h, ref } = await import(main.match(/from "([^"]*\/vue\.js[^"']*)"/)[1])
    const { default: Form } = await import('/src/modules/agents/ui/AgentRuntimeConfigForm.vue')
    const { useThemeStore } = await import('/src/shared/model/theme.js')
    const root = document.querySelector('#app').__vue_app__
    const theme = useThemeStore(root.config.globalProperties.$pinia)
    const themeMode = theme.themeMode
    const savedTheme = localStorage.getItem('theme')
    const config = ref({})
    const readonly = ref(false)
    const items = ref({
      tools: { name: '工具', kind: 'tools', type: 'list', supports_all: true, default: 'all', description: '内置的工具。默认选择当前用户可用的全部工具。', options: ['豆包 网页搜索', '向用户提问', '安装技能', '记录改进线索', 'OCR 解析文件', '展示交付物'].map((name, index) => ({ key: `tool-${index}`, name })) },
      knowledges: { name: '知识库', kind: 'knowledges', type: 'list', supports_all: true, default: 'all', description: '知识库列表，默认选择当前用户可访问的全部知识库。', options: [{ key: 'kb-a', name: '示例知识库' }] }
    })
    const host = document.createElement('div')
    host.id = 'resource-selection-check'
    Object.assign(host.style, { position: 'fixed', inset: '32px 32px auto', maxWidth: '1000px', margin: '0 auto', padding: '24px', zIndex: 900, background: 'var(--gray-0)' })
    document.body.append(host)
    const app = createApp({ render: () => h(Form, { modelValue: config.value, configurableItems: items.value, segment: 'tools', showSegmented: false, readonly: readonly.value, 'onUpdate:modelValue': value => { config.value = value } }) })
    app.use(root.config.globalProperties.$pinia)
    Object.assign(app._context.components, root._context.components)
    app.mount(host)
    window.__resourceSelection = { app, host, config, items, readonly, theme, themeMode, savedTheme }
  })
  const tools = page.locator('#resource-selection-check .config-item').nth(0)
  const knowledge = page.locator('#resource-selection-check .config-item').nth(1)
  try {
    await tools.waitFor()
    for (const field of [tools, knowledge]) {
      check((await field.innerText()).includes('已选择全部（含新增）'), '默认全部必须在状态位置表达含新增')
      check(await field.getByRole('button', { name: '选择全部', exact: true }).count() === 0, '全部态不应重复显示全选按钮')
      check(await field.getByRole('button', { name: '清空全部', exact: true }).count() === 1, '清空图标必须保留可访问名称')
      check((await field.getByRole('button', { name: '清空全部', exact: true }).innerText()).trim() === '', '清空操作应只显示 × 图标')
    }
    check(await page.evaluate(() => Object.keys(window.__resourceSelection.config.value).length) === 0, '默认值展示不得写入配置覆盖')
    await tools.getByRole('button', { name: '清空全部', exact: true }).click()
    check(await page.evaluate(() => JSON.stringify(window.__resourceSelection.config.value.tools)) === '[]', '清空全部必须提交空数组')
    check((await tools.innerText()).includes('已选择 0 项'), '空选择必须显示计数')
    await tools.getByRole('button', { name: '选择全部', exact: true }).click()
    check(await page.evaluate(() => window.__resourceSelection.config.value.tools) === 'all', '全选必须保留动态全部语义')
    await page.evaluate(() => { window.__resourceSelection.items.value.tools.options.push({ key: 'new-tool', name: '新增工具' }) })
    check((await tools.innerText()).includes('新增工具'), '全部态没有自动包含新增资源')
    await page.evaluate(() => { window.__resourceSelection.config.value.tools = window.__resourceSelection.items.value.tools.options.map(option => option.key) })
    await tools.getByRole('button', { name: '选择全部', exact: true }).waitFor()
    check((await tools.innerText()).includes('已选择 7 项'), '固定列表勾完当前项必须保留计数')
    check(!(await tools.innerText()).includes('已选择全部（含新增）'), '固定全选不能冒充动态全部')
    await tools.getByRole('button', { name: '选择...', exact: true }).click()
    await page.locator('.selection-modal .selection-item').first().click()
    await page.locator('.selection-modal').getByRole('button', { name: /确\s*认/ }).click()
    check(await page.evaluate(() => window.__resourceSelection.config.value.tools.length === 6 && !window.__resourceSelection.config.value.tools.includes('tool-0')), '弹窗调整必须保存固定选择')
    for (const field of [tools, knowledge]) {
      if (field === knowledge) await field.getByRole('button', { name: '清空全部', exact: true }).click()
      const status = await field.locator('.selection-count').boundingBox()
      const button = await field.getByRole('button', { name: '选择全部', exact: true }).boundingBox()
      check(button.x > status.x + status.width, '全选操作必须位于状态右侧')
    }
    await page.locator('#resource-selection-check').screenshot({ path: '/tmp/yuxi-selection-manual.png' })
    await page.evaluate(() => { window.__resourceSelection.config.value.knowledges = ['kb-a', 'hidden-kb'] })
    await knowledge.locator('.option-card').click()
    check(await page.evaluate(() => JSON.stringify(window.__resourceSelection.config.value.knowledges)) === '["hidden-kb"]', '局部编辑必须保留不可见引用')
    await knowledge.getByRole('button', { name: '清空全部', exact: true }).click()
    check(await page.evaluate(() => JSON.stringify(window.__resourceSelection.config.value.knowledges)) === '[]', '清空必须移除不可见引用')
    await knowledge.getByRole('button', { name: '选择全部', exact: true }).click()
    await tools.getByRole('button', { name: '选择全部', exact: true }).click()
    for (const [mode, width] of [['light', 1440], ['dark', 1440], ['light', 768], ['dark', 768]]) {
      await page.setViewportSize({ width, height: 900 })
      await page.evaluate(mode => window.__resourceSelection.theme.setTheme(mode), mode)
      const overflow = await page.locator('#resource-selection-check').evaluate(host => host.scrollWidth > host.clientWidth)
      check(!overflow, `${mode}/${width} 选择器横向溢出`)
      await page.locator('#resource-selection-check').screenshot({ path: `/tmp/yuxi-selection-${mode}-${width}.png` })
    }
    await page.evaluate(() => { window.__resourceSelection.readonly.value = true })
    check(await page.locator('#resource-selection-check button').count() === 0, '只读配置不得展示修改操作')
    return { defaultAll: true, clearIcon: true, actionPlacement: true, dynamicAll: true, fixedSelection: true, modalSelection: true, hiddenSelection: true, readonly: true, themes: ['light', 'dark'], widths: [1440, 768] }
  } finally {
    await page.evaluate(() => {
      const state = window.__resourceSelection
      state.app.unmount(); state.host.remove()
      state.theme.setTheme(state.themeMode)
      if (state.savedTheme === null) localStorage.removeItem('theme')
      else localStorage.setItem('theme', state.savedTheme)
      delete window.__resourceSelection
    })
  }
}
