import { computed, nextTick, ref, watch } from 'vue'

const MAX_UPLOAD_CONCURRENCY = 10

/** 拥有知识文件上传的并发、请求生命周期与有效文件进度。 */
export function useKnowledgeUploadQueue({
  fileList,
  isSupportedFile,
  getKbId,
  isFolderUpload,
  getUploadUrl,
  getAuthHeaders,
  createXhr = () => new XMLHttpRequest()
}) {
  const validFileList = computed(() => fileList.value.filter(isSupportedFile))
  const uploadQueue = ref([])
  const activeUploadCount = ref(0)
  const uploadTaskStatus = ref({})
  const uploadTaskProgress = ref({})

  const totalUploadCount = computed(() => validFileList.value.length)
  const validUidSet = computed(
    () => new Set(validFileList.value.map((file) => file.uid).filter(Boolean))
  )
  const queuedUploadCount = computed(
    () =>
      Object.entries(uploadTaskStatus.value).filter(
        ([uid, status]) => validUidSet.value.has(uid) && status === 'queued'
      ).length
  )
  const uploadingUploadCount = computed(
    () =>
      Object.entries(uploadTaskStatus.value).filter(
        ([uid, status]) => validUidSet.value.has(uid) && status === 'uploading'
      ).length
  )
  const successUploadCount = computed(
    () =>
      Object.entries(uploadTaskStatus.value).filter(
        ([uid, status]) => validUidSet.value.has(uid) && status === 'done'
      ).length
  )
  const failedUploadCount = computed(
    () =>
      Object.entries(uploadTaskStatus.value).filter(
        ([uid, status]) => validUidSet.value.has(uid) && status === 'error'
      ).length
  )
  const hasPendingUploads = computed(() => queuedUploadCount.value + uploadingUploadCount.value > 0)

  const overallUploadProgress = computed(() => {
    const total = totalUploadCount.value
    if (!total) {
      return 0
    }
    let sum = 0
    for (const uid of validUidSet.value) {
      sum += uploadTaskProgress.value[uid] || 0
    }
    return Math.round(sum / total)
  })

  const showAggregateProgress = computed(() => totalUploadCount.value >= MAX_UPLOAD_CONCURRENCY)

  function reset() {
    for (const task of uploadQueue.value) {
      task.canceled = true
    }
    uploadQueue.value = []
    uploadTaskStatus.value = {}
    uploadTaskProgress.value = {}
  }

  watch(fileList, (newFileList) => {
    const validUidSet = new Set(newFileList.map((file) => file.uid).filter(Boolean))
    const nextStatus = {}
    const nextProgress = {}

    for (const [uid, status] of Object.entries(uploadTaskStatus.value)) {
      if (validUidSet.has(uid)) {
        nextStatus[uid] = status
      }
    }
    for (const [uid, progress] of Object.entries(uploadTaskProgress.value)) {
      if (validUidSet.has(uid)) {
        nextProgress[uid] = progress
      }
    }

    uploadTaskStatus.value = nextStatus
    uploadTaskProgress.value = nextProgress
  })

  const customRequest = (options) => {
    const fileUid = options.file?.uid
    if (fileUid) {
      uploadTaskStatus.value[fileUid] = 'queued'
      uploadTaskProgress.value[fileUid] = 0
    }

    const task = {
      options,
      xhr: null,
      canceled: false
    }

    uploadQueue.value.push(task)
    processUploadQueue()

    return {
      abort: () => {
        if (task.canceled) return
        task.canceled = true
        const queueIndex = uploadQueue.value.indexOf(task)
        if (queueIndex !== -1) {
          uploadQueue.value.splice(queueIndex, 1)
        }
        if (task.cancel) {
          task.cancel()
        } else if (fileUid) {
          uploadTaskStatus.value[fileUid] = 'error'
        }
      }
    }
  }

  const processUploadQueue = () => {
    while (activeUploadCount.value < MAX_UPLOAD_CONCURRENCY && uploadQueue.value.length > 0) {
      const task = uploadQueue.value.shift()
      if (!task || task.canceled) {
        continue
      }

      activeUploadCount.value += 1
      runUploadTask(task)
        .catch(() => {
          // 错误已经在 runUploadTask 内处理，这里只保证队列继续消费
        })
        .finally(() => {
          activeUploadCount.value -= 1
          processUploadQueue()
        })
    }
  }

  const runUploadTask = (task) => {
    const { file, onProgress, onSuccess, onError } = task.options
    const fileUid = file?.uid

    if (fileUid) {
      uploadTaskStatus.value[fileUid] = 'uploading'
    }

    return new Promise((resolve, reject) => {
      let settled = false

      /** 只将当前请求的真实失败投影给上传组件。 */
      function fail(error, failedFile) {
        if (settled) return
        settled = true
        if (fileUid) {
          uploadTaskStatus.value[fileUid] = 'error'
        }
        reject(error)
        onError(error, failedFile)
      }

      task.cancel = () => {
        if (settled) return
        settled = true
        if (fileUid) {
          uploadTaskStatus.value[fileUid] = 'error'
        }
        // 原生 abort 同步触发事件，先结束请求以保持主动取消静默。
        resolve()
        task.xhr?.abort()
      }

      try {
        const formData = new FormData()
        const filename =
          isFolderUpload() && file.webkitRelativePath ? file.webkitRelativePath : file.name
        formData.append('file', file, filename)

        const currentKbId = getKbId()
        if (!currentKbId) {
          throw new Error('Knowledge base ID is missing')
        }

        const xhr = createXhr()
        task.xhr = xhr
        xhr.open('POST', getUploadUrl(currentKbId))

        const headers = getAuthHeaders()
        for (const [key, value] of Object.entries(headers)) {
          xhr.setRequestHeader(key, value)
        }

        xhr.upload.onprogress = (event) => {
          if (settled || !event.lengthComputable) return
          const percent = Math.min(100, (event.loaded / event.total) * 100)
          if (fileUid) {
            uploadTaskProgress.value[fileUid] = percent
          }
          onProgress({ percent })
        }

        xhr.onload = () => {
          if (settled) return
          if (xhr.status >= 200 && xhr.status < 300) {
            let response
            try {
              response = JSON.parse(xhr.responseText)
            } catch (error) {
              fail(error)
              return
            }
            settled = true
            if (fileUid) {
              uploadTaskStatus.value[fileUid] = 'done'
              uploadTaskProgress.value[fileUid] = 100
            }
            resolve()
            onSuccess(response, xhr)
            return
          }

          let errorResp
          try {
            errorResp = JSON.parse(xhr.responseText || '{}')
          } catch {
            errorResp = {}
          }
          file.response = errorResp
          fail(new Error(errorResp.detail || 'Upload failed'), file)
        }

        xhr.onerror = (errorEvent) => fail(errorEvent)
        xhr.onabort = () => fail(new Error('Upload aborted'))
        xhr.send(formData)
      } catch (error) {
        // Ant 的受控 fileList 经 Vue 刷新后才可见；同步失败不能早于列表装配。
        nextTick(() => fail(error))
      }
    })
  }

  return {
    validFileList,
    uploadTaskStatus,
    totalUploadCount,
    queuedUploadCount,
    uploadingUploadCount,
    successUploadCount,
    failedUploadCount,
    hasPendingUploads,
    overallUploadProgress,
    showAggregateProgress,
    customRequest,
    reset
  }
}
