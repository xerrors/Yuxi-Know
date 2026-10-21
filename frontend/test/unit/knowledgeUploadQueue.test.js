import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'
import test from 'node:test'
import { createRenderer, effectScope, h as vnode, nextTick, ref } from 'vue'
import AjaxUploaderModule from 'ant-design-vue/lib/vc-upload/AjaxUploader.js'
import UploadModule from 'ant-design-vue/lib/upload/Upload.js'
import { useKnowledgeUploadQueue } from '../../src/modules/knowledge/model/useKnowledgeUploadQueue.js'

/** 用可控 XHR 回应驱动生产上传队列。 */
function setup(t, { count = 1, folder = false, kbId = 'kb-test', throwAt } = {}) {
  const files = Array.from({ length: count }, (_, index) => {
    const file = new File([`body-${index}`], `${index}.txt`)
    file.uid = `file-${index}`
    file.webkitRelativePath = `folder/sub/${file.name}`
    return file
  })
  const fileList = ref(files)
  const requests = []
  const results = []
  let hasThrown = false
  /** 在指定原生方法边界只制造一次同步异常。 */
  function maybeThrow(stage) {
    if (throwAt === stage && !hasThrown) {
      hasThrown = true
      throw new Error(`${stage} failed`)
    }
  }
  const scope = effectScope()
  t.after(() => scope.stop())
  const queue = scope.run(() =>
    useKnowledgeUploadQueue({
      fileList,
      isSupportedFile: (file) => !file.name.startsWith('.') && file.name.endsWith('.txt'),
      getKbId: () => kbId,
      isFolderUpload: () => folder,
      getUploadUrl: (id) => `/api/knowledge/files/upload?kb_id=${id}`,
      getAuthHeaders: () => ({ Authorization: 'Bearer test-token' }),
      createXhr: () => {
        const xhr = {
          headers: {},
          upload: {},
          open(method, url) {
            maybeThrow('open')
            this.method = method
            this.url = url
          },
          setRequestHeader(key, value) {
            maybeThrow('setRequestHeader')
            this.headers[key] = value
          },
          send(body) {
            maybeThrow('send')
            this.body = body
            requests.push(this)
          },
          abort() {
            this.aborted = true
            this.onabort?.()
          },
          respond(status = 200, body = { file_path: 'minio://test/item' }) {
            this.status = status
            this.responseText = typeof body === 'string' ? body : JSON.stringify(body)
            this.onload()
          }
        }
        return xhr
      }
    })
  )
  function enqueue(file = files[0], callbacks = {}) {
    return queue.customRequest({
      file,
      onProgress: (progress) => results.push({ uid: file.uid, kind: 'progress', progress }),
      onSuccess: (response, xhr) => {
        results.push({ uid: file.uid, kind: 'success', response, xhr })
        callbacks.onSuccess?.()
      },
      onError: (error, failedFile) => {
        results.push({ uid: file.uid, kind: 'error', error, failedFile })
        callbacks.onError?.()
      }
    })
  }
  return { queue, files, fileList, requests, results, enqueue }
}

test('最多十个文件并发，失败释放槽位并按入队顺序继续', async (t) => {
  const h = setup(t, { count: 12 })
  for (const file of h.files) await h.enqueue(file)
  assert.equal(h.requests.length, 10)
  assert.equal(h.queue.uploadingUploadCount.value, 10)
  assert.equal(h.queue.queuedUploadCount.value, 2)
  assert.equal(h.queue.hasPendingUploads.value, true)
  assert.equal(h.queue.showAggregateProgress.value, true)
  h.requests[0].respond(409, { detail: '相同内容' })
  await setImmediate()
  assert.equal(h.requests.length, 11)
  assert.equal(h.requests[10].body.get('file').name, '10.txt')
  assert.equal(h.queue.failedUploadCount.value, 1)
  assert.equal(h.queue.uploadingUploadCount.value, 10)
  h.requests[1].respond()
  await setImmediate()
  assert.equal(h.requests.length, 12)
  assert.equal(h.requests[11].body.get('file').name, '11.txt')
  for (const xhr of h.requests.slice(2)) xhr.respond()
  await setImmediate()
  assert.equal(h.queue.successUploadCount.value, 11)
  assert.equal(h.queue.failedUploadCount.value, 1)
  assert.equal(h.queue.hasPendingUploads.value, false)
  assert.equal(h.results.find((result) => result.kind === 'error').error.message, '相同内容')
  assert.deepEqual(h.files[0].response, { detail: '相同内容' })
})

for (const folder of [false, true]) {
  test(`multipart 保持${folder ? '目录相对路径' : '原文件名'}、端点、认证头与成功响应`, async (t) => {
    const h = setup(t, { folder })
    await h.enqueue()
    const xhr = h.requests[0]
    assert.equal(xhr.method, 'POST')
    assert.equal(xhr.url, '/api/knowledge/files/upload?kb_id=kb-test')
    assert.deepEqual(xhr.headers, { Authorization: 'Bearer test-token' })
    assert.equal(xhr.body.get('file').name, folder ? 'folder/sub/0.txt' : '0.txt')
    assert.equal(await xhr.body.get('file').text(), 'body-0')
    const response = {
      file_path: 'minio://test/item',
      has_same_name: true,
      same_name_files: [{ file_id: 'old' }]
    }
    xhr.respond(200, response)
    await setImmediate()
    assert.deepEqual(h.results[0].response, response)
    assert.equal(h.results[0].xhr, xhr)
    assert.equal(h.queue.successUploadCount.value, 1)
    assert.equal(h.queue.overallUploadProgress.value, 100)
  })
}

test('聚合只统计有效文件，进度封顶，不可计算进度不覆盖；移除后清理状态', async (t) => {
  const h = setup(t, { count: 2 })
  const hidden = new File(['hidden'], '.hidden.txt')
  hidden.uid = 'hidden'
  const unsupported = new File(['binary'], 'image.bin')
  unsupported.uid = 'unsupported'
  h.fileList.value = [...h.files, hidden, unsupported]
  for (const file of h.fileList.value) await h.enqueue(file)
  h.requests[0].upload.onprogress({ lengthComputable: true, loaded: 1, total: 2 })
  h.requests[1].upload.onprogress({ lengthComputable: true, loaded: 2, total: 1 })
  h.requests[0].upload.onprogress({ lengthComputable: false, loaded: 0, total: 0 })
  assert.equal(h.queue.totalUploadCount.value, 2)
  assert.equal(h.queue.uploadingUploadCount.value, 2)
  assert.equal(h.queue.overallUploadProgress.value, 75)
  assert.equal(h.queue.showAggregateProgress.value, false)
  assert.equal(h.results[1].progress.percent, 100)
  h.fileList.value = [h.files[1]]
  await nextTick()
  assert.equal(h.queue.totalUploadCount.value, 1)
  assert.equal(h.queue.overallUploadProgress.value, 100)
  assert.equal(h.queue.uploadTaskStatus.value['file-0'], undefined)
  h.fileList.value = []
  await nextTick()
  assert.equal(h.queue.overallUploadProgress.value, 0)
  assert.equal(h.queue.hasPendingUploads.value, false)
  for (const xhr of h.requests) xhr.respond()
  await setImmediate()
})

for (const failure of ['http', 'invalid-json', 'network', 'missing-kb']) {
  test(`${failure} 保留失败回调且允许重新提交同一文件`, async (t) => {
    const h = setup(t, { kbId: failure === 'missing-kb' ? null : 'kb-test' })
    await h.enqueue()
    const xhr = h.requests[0]
    if (failure === 'http') xhr.respond(500, 'not-json')
    if (failure === 'invalid-json') xhr.respond(200, 'not-json')
    if (failure === 'network') xhr.onerror(new Error('network unavailable'))
    await setImmediate()
    assert.equal(h.queue.failedUploadCount.value, 1)
    assert.equal(h.queue.hasPendingUploads.value, false)
    assert.equal(h.results.length, 1)
    assert.equal(h.results[0].kind, 'error')
    if (failure === 'http') {
      assert.equal(h.results[0].error.message, 'Upload failed')
      assert.equal(h.results[0].failedFile, h.files[0])
    }
    if (failure === 'missing-kb') {
      assert.equal(h.requests.length, 0)
      assert.equal(h.results[0].error.message, 'Knowledge base ID is missing')
      return
    }
    await h.enqueue()
    assert.equal(h.queue.failedUploadCount.value, 0)
    assert.equal(h.queue.uploadingUploadCount.value, 1)
    h.requests[1].respond()
    await setImmediate()
    assert.equal(h.queue.successUploadCount.value, 1)
  })
}

test('取消排队请求后不发送该文件，取消活动请求释放槽位', async (t) => {
  const h = setup(t, { count: 12 })
  const handles = []
  for (const file of h.files) handles.push(await h.enqueue(file))
  handles[10].abort()
  assert.equal(h.requests.length, 10)
  assert.equal(h.queue.queuedUploadCount.value, 1)
  handles[0].abort()
  await setImmediate()
  assert.equal(h.requests.length, 11)
  assert.equal(h.requests[0].aborted, true)
  assert.equal(h.requests[10].body.get('file').name, '11.txt')
  assert.equal(h.queue.failedUploadCount.value, 2)
  for (const xhr of h.requests.slice(1)) xhr.respond()
  await setImmediate()
})

test('切换模式丢弃待发任务和统计，活动请求仍占并发槽位', async (t) => {
  const h = setup(t, { count: 12 })
  for (const file of h.files) await h.enqueue(file)
  h.fileList.value = []
  h.queue.reset()
  await nextTick()
  assert.equal(h.queue.totalUploadCount.value, 0)
  assert.deepEqual(h.queue.uploadTaskStatus.value, {})
  assert.equal(
    h.requests.some((xhr) => xhr.aborted),
    false
  )
  const fresh = new File(['fresh'], 'fresh.txt')
  fresh.uid = 'fresh'
  h.fileList.value = [fresh]
  await h.enqueue(fresh)
  assert.equal(h.requests.length, 10)
  assert.equal(h.queue.queuedUploadCount.value, 1)
  h.requests[0].respond()
  await setImmediate()
  assert.equal(h.requests.length, 11)
  assert.equal(h.requests[10].body.get('file').name, 'fresh.txt')
  for (const xhr of h.requests.slice(1)) xhr.respond()
  await setImmediate()
  assert.equal(h.queue.successUploadCount.value, 1)
  assert.equal(h.queue.overallUploadProgress.value, 100)
  assert.equal(h.queue.hasPendingUploads.value, false)
})

test('customRequest 同步返回取消句柄', async (t) => {
  const h = setup(t)
  const request = h.enqueue()
  assert.equal(typeof request.abort, 'function')
  assert.equal(request.then, undefined)
  request.abort()
  await setImmediate()
})

/** 使用真实 Ant 组件和最小宿主验证事件装配。 */
function mountUploader(t, render) {
  function makeNode(type) {
    return { type, children: [], props: {}, parent: null }
  }
  const renderer = createRenderer({
    createElement: makeNode,
    createText: () => makeNode('text'),
    createComment: () => makeNode('comment'),
    insert(child, parent, anchor = null) {
      child.parent = parent
      const index = anchor ? parent.children.indexOf(anchor) : -1
      if (index < 0) parent.children.push(child)
      else parent.children.splice(index, 0, child)
    },
    remove(child) {
      const index = child.parent?.children.indexOf(child) ?? -1
      if (index >= 0) child.parent.children.splice(index, 1)
    },
    setText() {},
    setElementText() {},
    parentNode: (node) => node.parent,
    nextSibling: () => null,
    patchProp(node, key, _previous, value) {
      node.props[key] = value
    }
  })
  const app = renderer.createApp({ render })
  const root = makeNode('root')
  app.mount(root)
  t.after(() => app.unmount())
  return root
}

test('Ant Upload 删除动作中止真实队列请求', async (t) => {
  const mounted = setup(t)
  const uploader = ref(null)
  const errors = []
  const root = mountUploader(t, () =>
    vnode(AjaxUploaderModule.default, {
      ref: uploader,
      componentTag: 'span',
      prefixCls: 'upload',
      customRequest: mounted.queue.customRequest,
      onStart() {},
      onError: (error) => errors.push(error)
    })
  )
  const input = root.children[0].children.find((node) => node.type === 'input')
  input.props.onChange({ target: { files: [mounted.files[0]] } })
  await setImmediate()
  assert.equal(mounted.requests.length, 1)
  assert.equal(mounted.queue.uploadingUploadCount.value, 1)
  uploader.value.abort(mounted.files[0])
  await setImmediate()
  assert.equal(mounted.requests[0].aborted, true)
  assert.equal(mounted.queue.failedUploadCount.value, 1)
  assert.equal(mounted.queue.hasPendingUploads.value, false)
  assert.deepEqual(errors, [])
})

for (const throwAt of ['open', 'setRequestHeader', 'send']) {
  test(`${throwAt} 同步抛错变为可重试错误并释放并发槽位`, async (t) => {
    const h = setup(t, { count: 11, throwAt })
    for (const file of h.files) h.enqueue(file)
    await setImmediate()
    assert.equal(h.queue.uploadTaskStatus.value['file-0'], 'error')
    assert.equal(h.results.length, 1)
    assert.equal(h.results[0].kind, 'error')
    assert.equal(h.results[0].error.message, `${throwAt} failed`)
    assert.equal(h.requests.length, 10)
    assert.equal(h.queue.uploadingUploadCount.value, 10)
    for (const xhr of h.requests) xhr.respond()
    await setImmediate()
    assert.equal(h.queue.hasPendingUploads.value, false)
    h.enqueue(h.files[0])
    h.requests[10].respond()
    await setImmediate()
    assert.equal(h.queue.successUploadCount.value, 11)
  })
}

test('删除在途文件静默取消，迟到回调不重建状态或影响同 UID 重传', async (t) => {
  const h = setup(t)
  const handle = h.enqueue()
  const stale = h.requests[0]
  const late = {
    progress: stale.upload.onprogress,
    load: stale.onload,
    error: stale.onerror,
    abort: stale.onabort
  }
  handle.abort()
  await setImmediate()
  assert.deepEqual(h.results, [])
  h.fileList.value = []
  await nextTick()
  late.progress({ lengthComputable: true, loaded: 1, total: 2 })
  late.error(new Error('late network failure'))
  late.abort()
  stale.status = 200
  stale.responseText = JSON.stringify({ file_path: 'minio://stale' })
  late.load()
  assert.deepEqual(h.queue.uploadTaskStatus.value, {})
  assert.equal(h.queue.overallUploadProgress.value, 0)
  assert.deepEqual(h.results, [])
  h.fileList.value = h.files
  h.enqueue()
  late.error(new Error('old attempt failed'))
  late.progress({ lengthComputable: true, loaded: 99, total: 100 })
  handle.abort()
  assert.equal(h.queue.uploadTaskStatus.value['file-0'], 'uploading')
  assert.equal(h.queue.overallUploadProgress.value, 0)
  h.requests[1].respond()
  await setImmediate()
  assert.equal(h.queue.successUploadCount.value, 1)
  assert.equal(h.results.length, 1)
  assert.equal(h.results[0].kind, 'success')
})

for (const callback of ['onSuccess', 'onError']) {
  test(`${callback} 消费回调抛错保持已结束状态并继续 FIFO`, async (t) => {
    const h = setup(t, { count: 11 })
    const callbackError = new Error(`${callback} consumer failed`)
    h.enqueue(h.files[0], {
      [callback]: () => {
        throw callbackError
      }
    })
    for (const file of h.files.slice(1)) h.enqueue(file)
    assert.equal(h.requests.length, 10)
    assert.throws(
      () => {
        if (callback === 'onSuccess') h.requests[0].respond()
        else h.requests[0].onerror(new Error('network failed'))
      },
      (error) => error === callbackError
    )
    await setImmediate()
    assert.equal(
      h.queue.uploadTaskStatus.value['file-0'],
      callback === 'onSuccess' ? 'done' : 'error'
    )
    assert.equal(h.results.length, 1)
    assert.equal(h.results[0].kind, callback === 'onSuccess' ? 'success' : 'error')
    assert.equal(h.requests.length, 11)
    assert.equal(h.requests[10].body.get('file').name, '10.txt')
    h.requests[0].upload.onprogress({ lengthComputable: true, loaded: 1, total: 2 })
    h.requests[0].onerror(new Error('late failure'))
    h.requests[0].respond()
    assert.equal(h.results.length, 1)
    assert.equal(
      h.queue.uploadTaskStatus.value['file-0'],
      callback === 'onSuccess' ? 'done' : 'error'
    )
    for (const xhr of h.requests.slice(1)) xhr.respond()
    await setImmediate()
    assert.equal(h.queue.hasPendingUploads.value, false)
  })
}

for (const throwAt of ['open', 'setRequestHeader', 'send', 'missing-kb']) {
  test(`受控 Ant Upload 将 ${throwAt} 同步失败投影为错误文件`, async (t) => {
    const h = setup(t, { throwAt, kbId: throwAt === 'missing-kb' ? null : 'kb-test' })
    h.fileList.value = []
    const changes = []
    const root = mountUploader(t, () =>
      vnode(UploadModule.default, {
        fileList: h.fileList.value,
        showUploadList: false,
        customRequest: h.queue.customRequest,
        onChange(info) {
          changes.push(info.file.status)
          h.fileList.value = info.fileList
        }
      })
    )
    /** 从真实组件树定位原生文件输入。 */
    function findInput(node) {
      if (node.type === 'input') return node
      for (const child of node.children) {
        const input = findInput(child)
        if (input) return input
      }
    }
    findInput(root).props.onChange({ target: { files: [h.files[0]] } })
    await setImmediate()
    assert.deepEqual(changes, ['uploading', 'error'])
    assert.equal(h.fileList.value[0].status, 'error')
    assert.equal(
      h.fileList.value[0].error.message,
      throwAt === 'missing-kb' ? 'Knowledge base ID is missing' : `${throwAt} failed`
    )
    assert.equal(h.queue.hasPendingUploads.value, false)
  })
}

test('同步准备失败通知前删除文件仍静默释放预算', async (t) => {
  const h = setup(t, { throwAt: 'open' })
  const handle = h.enqueue()
  handle.abort()
  await setImmediate()
  assert.deepEqual(h.results, [])
  assert.equal(h.queue.hasPendingUploads.value, false)
  h.enqueue()
  h.requests[0].respond()
  await setImmediate()
  assert.equal(h.queue.successUploadCount.value, 1)
})
