// 在真实 Vite 页面挂载生产弹窗，用受控 HTTP 检查 Ant Upload 的请求取消与上传结果。
// 执行：playwright-cli run-code --filename=frontend/test/browser/knowledgeUploadQueue.js
// prettier-ignore
async (page) => {
  const check = (value, message) => { if (!value) throw new Error(message) }
  const origin = page.url().match(/^https?:\/\/[^/]+/)?.[0] || 'http://localhost:5173'
  const originalViewport = page.viewportSize()
  const failedRequests = []
  const waiting = []
  let originalTheme
  let uploadRequests = 0
  let nextOutcome = 'hold'
  const onRequestFailed = request => {
    if (request.url().includes('/api/knowledge/files/upload')) failedRequests.push(request.failure()?.errorText)
  }
  page.on('requestfailed', onRequestFailed)
  const handler = async route => {
    const path = route.request().url().replace(/^https?:\/\/[^/]+/, '').split('?')[0]
    if (path === '/api/knowledge/files/upload') {
      uploadRequests++
      if (nextOutcome === 'hold') {
        let release
        const gate = new Promise(resolve => { release = resolve })
        const finished = gate.then(() => route.fulfill({ status: 200, json: { file_path: 'minio://fixture/cancelled' } }).catch(() => {}))
        waiting.push({ release, finished })
        return finished
      }
      if (nextOutcome === 'error') return route.fulfill({ status: 409, json: { detail: '知识库中已经存在了相同内容文件' } })
      return route.fulfill({ json: { file_path: 'minio://fixture/success.txt', content_hash: 'fixture-hash', size: 7, has_same_name: false, same_name_files: [] } })
    }
    let json
    if (path === '/api/auth/me') json = { uid: 'upload-fixture-user', username: '上传验证', role: 'admin' }
    else if (path.endsWith('/supported-types')) json = { file_types: ['.txt', '.md'] }
    else if (path.includes('ocr')) json = { engines: [{ engine_id: 'rapid_ocr' }], default_engine: 'rapid_ocr' }
    else if (path.includes('/models')) json = { providers: [], models: [], data: [] }
    else if (path === '/api/projects') json = []
    else json = { data: [], files: [], skills: [], config: {}, site_name: '语析', first_run: false }
    await route.fulfill({ json })
  }
  await page.route('**/api/**', handler)
  try {
    await page.goto(origin)
    originalTheme = await page.evaluate(() => localStorage.getItem('theme'))
    await page.evaluate(async () => {
      const source = await (await fetch('/src/app/main.js')).text()
      const { createApp, h, ref } = await import(source.match(/from "([^"]*\/vue\.js[^"']*)"/)[1])
      const { createPinia } = await import(source.match(/from "([^"]*\/pinia\.js[^"']*)"/)[1])
      const { default: Modal } = await import('/src/modules/knowledge/ui/FileUploadModal.vue')
      const { useKnowledgeBaseStore } = await import('/src/modules/knowledge/model/knowledgeBase.js')
      const { useUserStore } = await import('/src/modules/identity/model/user.js')
      const { useThemeStore } = await import('/src/shared/model/theme.js')
      const { configureApiAuth } = await import('/src/apis/auth_context.js')
      const root = document.querySelector('#app').__vue_app__
      const pinia = createPinia()
      const visible = ref(true)
      const store = useKnowledgeBaseStore(pinia)
      store.kbId = 'upload-fixture-kb'
      store.knowledgeBase = { kb_id: store.kbId, name: '上传验证' }
      const user = useUserStore(pinia)
      user.userRole = 'admin'
      user.token = 'upload-fixture-token'
      configureApiAuth({ getToken: () => user.token, isAdmin: () => true })
      const theme = useThemeStore(pinia)
      theme.setTheme('light')
      const observed = { abortEvents: 0, successLoads: 0, errorEvents: 0 }
      const originalOpen = XMLHttpRequest.prototype.open
      let lastUploadXhr
      XMLHttpRequest.prototype.open = function (method, url, ...args) {
        if (String(url).includes('/api/knowledge/files/upload')) {
          lastUploadXhr = this
          this.addEventListener('abort', () => { observed.abortEvents++ })
          this.addEventListener('load', () => { if (this.status >= 200 && this.status < 300) observed.successLoads++ })
          this.addEventListener('error', () => { observed.errorEvents++ })
        }
        if (String(url).includes('/api/knowledge/files/upload') && window.uploadQueueProbe?.failNextOpen) {
          window.uploadQueueProbe.failNextOpen = false
          return originalOpen.call(this, method, 'http://[', ...args)
        }
        return originalOpen.call(this, method, url, ...args)
      }
      const host = document.createElement('div')
      document.body.append(host)
      const app = createApp({ render: () => h(root._context.components.AConfigProvider, { theme: theme.currentTheme }, () => h(Modal, { visible: visible.value, 'onUpdate:visible': value => { visible.value = value } })) })
      app.use(pinia)
      Object.assign(app._context.components, root._context.components)
      app.mount(host)
      window.uploadQueueProbe = { app, host, visible, theme, observed, getXhrObservation: () => ({ ...observed, readyState: lastUploadXhr?.readyState }), restoreXhr: () => { XMLHttpRequest.prototype.open = originalOpen }, restoreAuth: () => {
        const original = useUserStore(root.config.globalProperties.$pinia)
        configureApiAuth({ getToken: () => original.token, isAdmin: () => original.isAdmin, isSuperAdmin: () => original.isSuperAdmin })
      } }
    })
    await page.setViewportSize({ width: 1440, height: 1000 })
    const modal = page.locator('.ant-modal').filter({ hasText: '添加文件' })
    await modal.waitFor()
    const settleAnimations = () => page.evaluate(async () => {
      const finite = document.getAnimations().filter(animation => animation.playState === 'running' && Number.isFinite(animation.effect?.getComputedTiming().endTime))
      await Promise.all(finite.map(animation => animation.finished.catch(() => {})))
    })
    const checkSuccessFrame = async () => {
      const facts = await modal.evaluate(element => ({
        done: element.querySelectorAll('.ant-upload-list-item-done').length,
        errors: element.querySelectorAll('.ant-upload-list-item-error').length,
        disabled: [...element.querySelectorAll('button')].find(button => button.textContent.trim() === '添加到知识库')?.disabled
      }))
      check(facts.done === 1 && facts.errors === 0 && facts.disabled === false, `成功截图帧状态不一致：${JSON.stringify(facts)}`)
    }
    const fileInput = modal.locator('input[type=file]')
    const selectFile = (name, content) => fileInput.evaluate((input, payload) => {
      const transfer = new DataTransfer()
      transfer.items.add(new File([payload.content], payload.name, { type: 'text/plain' }))
      input.files = transfer.files
      input.dispatchEvent(new Event('change', { bubbles: true }))
    }, { name, content })
    const sent = page.waitForRequest(request => request.url().includes('/api/knowledge/files/upload'))
    await selectFile('cancel.txt', 'cancel')
    await sent
    await modal.locator('.ant-upload-list-item').filter({ hasText: 'cancel.txt' }).waitFor()
    await page.waitForFunction(() => document.querySelector('.ant-upload-list-item-uploading'))
    const cancelRow = modal.locator('.ant-upload-list-item').filter({ hasText: 'cancel.txt' })
    await cancelRow.hover()
    await cancelRow.locator('.ant-upload-list-item-actions button').click()
    await page.waitForFunction(() => window.uploadQueueProbe.observed.abortEvents === 1)
    const cancelled = await page.evaluate(() => window.uploadQueueProbe.getXhrObservation())
    check(cancelled.abortEvents === 1 && cancelled.readyState === 0 && cancelled.successLoads === 0, '删除在途文件没有产生原生 abort 事件、回到 UNSENT，或误产生成功响应')
    await modal.locator('.ant-upload-list-item').waitFor({ state: 'detached' })
    check(await modal.getByRole('button', { name: '添加到知识库', exact: true }).isDisabled(), '取消后错误地允许提交')
    const held = waiting.splice(0)
    held.forEach(item => item.release())
    await Promise.all(held.map(item => item.finished))
    const released = await page.evaluate(() => window.uploadQueueProbe.getXhrObservation())
    check(released.abortEvents === 1 && released.readyState === 0 && released.successLoads === 0, '释放响应后取消请求产生了迟到成功')
    check(await modal.locator('.ant-upload-list-item').count() === 0, '释放响应后取消文件重新出现')
    check(await page.locator('.ant-message-error').count() === 0, '正常删除在途文件出现上传失败提示')

    await page.evaluate(() => { window.uploadQueueProbe.failNextOpen = true })
    await selectFile('sync-fail.txt', 'sync-fail')
    const syncFailed = modal.locator('.ant-upload-list-item-error').filter({ hasText: 'sync-fail.txt' })
    await syncFailed.waitFor()
    check(await modal.getByRole('button', { name: '添加到知识库', exact: true }).isDisabled(), 'XHR 同步异常后错误地允许提交')
    check((await page.locator('.ant-message-error').allTextContents()).some(text => text.includes('open')), 'XHR 原生同步异常没有显示失败提示')
    await syncFailed.hover()
    await syncFailed.locator('.ant-upload-list-item-actions button').click()
    await syncFailed.waitFor({ state: 'detached' })

    nextOutcome = 'error'
    await selectFile('retry.txt', 'retry')
    const failed = modal.locator('.ant-upload-list-item-error').filter({ hasText: 'retry.txt' })
    await failed.waitFor()
    check(await modal.getByRole('button', { name: '添加到知识库', exact: true }).isDisabled(), '失败文件错误地允许提交')
    await settleAnimations()
    await page.screenshot({ path: '/tmp/yuxi-upload-queue-error-light.png' })
    await failed.hover()
    await failed.locator('.ant-upload-list-item-actions button').click()
    await failed.waitFor({ state: 'detached' })
    nextOutcome = 'success'
    await selectFile('retry.txt', 'retry')
    await modal.locator('.ant-upload-list-item-done').filter({ hasText: 'retry.txt' }).waitFor()
    check(await modal.getByRole('button', { name: '添加到知识库', exact: true }).isEnabled(), '重新上传成功后无法提交')
    await page.evaluate(() => window.uploadQueueProbe.theme.setTheme('dark'))
    await page.setViewportSize({ width: 1024, height: 900 })
    await settleAnimations()
    await checkSuccessFrame()
    await page.screenshot({ path: '/tmp/yuxi-upload-queue-success-dark.png' })
    await page.setViewportSize({ width: 768, height: 900 })
    await settleAnimations()
    await checkSuccessFrame()
    await page.screenshot({ path: '/tmp/yuxi-upload-queue-success-768.png' })
    return { uploadRequests, aborted: cancelled.abortEvents, cancelledReadyState: released.readyState, lateSuccesses: released.successLoads, networkFailures: failedRequests.length, failed: true, nativeSyncFailure: true, silentCancel: true, resubmitted: true, widths: [1440, 1024, 768] }
  } finally {
    const held = waiting.splice(0)
    held.forEach(item => item.release())
    await Promise.all(held.map(item => item.finished))
    page.off('requestfailed', onRequestFailed)
    await page.evaluate(theme => {
      const probe = window.uploadQueueProbe
      if (probe) { probe.theme.setTheme(theme || 'light'); probe.app.unmount(); probe.restoreXhr(); probe.host.remove(); probe.restoreAuth(); delete window.uploadQueueProbe }
      if (theme === null) localStorage.removeItem('theme')
    }, originalTheme)
    if (originalViewport) await page.setViewportSize(originalViewport)
    await page.unroute('**/api/**', handler)
  }
}
