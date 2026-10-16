import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { knowledgeBaseApi, documentApi, queryApi } from '@/apis/knowledge_api'
import { useBackgroundJobsStore } from '@/modules/background-jobs/model/jobs'
import { useUserStore } from '@/modules/identity/model/user'
import { useRouter } from 'vue-router'
import { parseToShanghai } from '@/shared/lib/time'
import { canSelectFile, isProcessingFile } from '@/modules/knowledge/model/knowledge_file_policy'

// 自动轮询参数：链式调度（等上一轮请求全部返回后再排下一轮），处理中文件长时间无进展时按 2 倍退避并最终自动停止；
// 基础间隔与后端文件统计缓存节奏（10s）对齐，避免高频请求重复全表聚合
const AUTO_REFRESH_POLL_INTERVAL_MS = 10000
const AUTO_REFRESH_MAX_INTERVAL_MS = 30000
const AUTO_REFRESH_STALE_POLLS_LIMIT = 6

export const useKnowledgeBaseStore = defineStore('knowledgeBase', () => {
  const router = useRouter()
  const jobsStore = useBackgroundJobsStore()
  const userStore = useUserStore()

  // State
  const knowledgeBases = ref([])
  const knowledgeBase = ref({})
  const kbId = ref(null)
  const fileDetailFileId = ref(null)
  const documentFiles = ref([])
  const folderBreadcrumbs = ref([{ file_id: null, filename: '全部文件', path_prefix: '' }])

  const queryParams = ref([])
  const meta = reactive({})
  const selectedRowKeys = ref([])
  const fileBrowser = reactive({
    loading: false,
    parentId: null,
    page: 1,
    pageSize: 100,
    total: 0,
    hasMore: false,
    pathPrefix: '',
    status: 'all',
    recursive: false
  })

  const state = reactive({
    listLoading: false,
    creating: false,
    knowledgeBaseLoading: false,
    lock: false,
    fileDetailModalVisible: false,
    batchDeleting: false,
    chunkLoading: false,
    autoRefresh: false,
    queryParamsLoading: false
  })

  let autoRefreshSource = null // Tracks whether auto-refresh was user-triggered or automatic
  let autoRefreshManualOverride = false // Indicates user explicitly disabled auto-refresh
  // 自动轮询状态：refreshTimer 保存链式调度的定时器；refreshGeneration 用于废弃过期轮询轮次
  let refreshTimer = null
  let refreshGeneration = 0
  let refreshStablePolls = 0
  let refreshIntervalMs = AUTO_REFRESH_POLL_INTERVAL_MS
  let refreshLastProcessingCount = null
  let fileBrowserContextId = 0
  let infoRequestId = 0
  let fileRequestId = 0
  let fileSnapshotRevision = 0

  function setCurrentFileMap(items = []) {
    knowledgeBase.value = {
      ...knowledgeBase.value,
      files: Object.fromEntries(items.map((item) => [item.file_id, item]))
    }
  }

  function resetFileBrowser() {
    fileBrowserContextId += 1
    documentFiles.value = []
    folderBreadcrumbs.value = [{ file_id: null, filename: '全部文件', path_prefix: '' }]
    selectedRowKeys.value = []
    Object.assign(fileBrowser, {
      loading: false,
      parentId: null,
      page: 1,
      pageSize: 100,
      total: 0,
      hasMore: false,
      pathPrefix: '',
      status: 'all',
      recursive: false
    })
    setCurrentFileMap([])
  }

  // Actions
  // 管理员获取所有知识库，普通用户获取有权限访问的知识库
  async function loadKnowledgeBases() {
    state.listLoading = true
    try {
      const data = userStore.isAdmin
        ? await knowledgeBaseApi.getKnowledgeBases()
        : await knowledgeBaseApi.getAccessibleKnowledgeBases()
      const list = data?.knowledge_bases || []
      knowledgeBases.value = list.sort((a, b) => {
        const timeA = parseToShanghai(a.created_at)
        const timeB = parseToShanghai(b.created_at)
        if (!timeA && !timeB) return 0
        if (!timeA) return 1
        if (!timeB) return -1
        return timeB.valueOf() - timeA.valueOf() // 降序排列，最新的在前面
      })
    } catch (error) {
      console.error('加载知识库列表失败:', error)
      if (error.message.includes('权限')) {
        message.error('没有权限访问知识库')
      }
      throw error
    } finally {
      state.listLoading = false
    }
  }

  async function createKnowledgeBase(formData) {
    // 验证
    if (!formData.name?.trim()) {
      message.error('知识库名称不能为空')
      return false
    }

    if (!formData.kb_type) {
      message.error('请选择知识库类型')
      return false
    }

    state.creating = true
    try {
      const data = await knowledgeBaseApi.createKnowledgeBase(formData)
      message.success('创建成功')
      await loadKnowledgeBases() // 刷新列表
      return data
    } catch (error) {
      console.error('创建知识库失败:', error)
      message.error(error.message || '创建失败')
      throw error
    } finally {
      state.creating = false
    }
  }

  async function getKnowledgeBaseInfo(id, skipQueryParams = false, isBackground = false) {
    const kbIdValue = id || kbId.value
    const token = userStore.token
    if (!kbIdValue) return
    const requestId = ++infoRequestId
    const filesRevision = fileSnapshotRevision

    if (!isBackground) {
      state.lock = true
      state.knowledgeBaseLoading = true
    }
    try {
      const data = await knowledgeBaseApi.getKnowledgeBaseInfo(kbIdValue)
      if (requestId !== infoRequestId || kbIdValue !== kbId.value || token !== userStore.token)
        return
      const currentFiles = knowledgeBase.value.files || {}
      // 文件分页快照更新后，较早的元信息不能覆盖它的文件与统计。
      const current = knowledgeBase.value
      const keepFileSnapshot = filesRevision !== fileSnapshotRevision
      knowledgeBase.value = {
        ...data,
        files: keepFileSnapshot ? currentFiles : data?.files || currentFiles,
        ...(keepFileSnapshot ? { stats: current.stats, row_count: current.row_count } : {})
      }
      ensureAutoRefreshForProcessing(knowledgeBase.value.files, knowledgeBase.value.stats)

      // Only load query parameters if explicitly requested or if not loaded yet
      if (!skipQueryParams && queryParams.value.length === 0) {
        await loadQueryParams(kbIdValue)
      }
    } catch (error) {
      console.error(error)
      message.error(error.message || '获取知识库信息失败')
    } finally {
      if (requestId === infoRequestId) {
        state.lock = false
        state.knowledgeBaseLoading = false
      }
    }
  }

  async function updateKnowledgeBaseInfo(formData) {
    try {
      state.lock = true
      await knowledgeBaseApi.updateKnowledgeBase(kbId.value, formData)
      message.success('知识库信息更新成功')
      await getKnowledgeBaseInfo() // Load query params after updating knowledgeBase info
    } catch (error) {
      console.error(error)
      message.error(error.message || '更新失败')
    } finally {
      state.lock = false
    }
  }

  function deleteKnowledgeBase() {
    Modal.confirm({
      title: '删除知识库',
      content: '确定要删除该知识库吗？',
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        state.lock = true
        try {
          const data = await knowledgeBaseApi.deleteKnowledgeBase(kbId.value)
          message.success(data.message || '删除成功')
          router.push({ path: '/extensions', query: { tab: 'knowledge' } })
        } catch (error) {
          console.error(error)
          message.error(error.message || '删除失败')
        } finally {
          state.lock = false
        }
      }
    })
  }

  async function deleteFile(fileId) {
    state.lock = true
    try {
      await documentApi.deleteDocument(kbId.value, fileId)
      await getKnowledgeBaseInfo(undefined, true) // Skip query params for file deletion
      await loadDocumentFiles({ isBackground: true })
    } catch (error) {
      console.error(error)
      message.error(error.message || '删除失败')
      throw error
    } finally {
      state.lock = false
    }
  }

  function handleDeleteFile(fileId) {
    Modal.confirm({
      title: '删除文件',
      content: '确定要删除该文件吗？',
      okText: '确认',
      cancelText: '取消',
      onOk: () => deleteFile(fileId)
    })
  }

  function handleBatchDelete() {
    const files = knowledgeBase.value.files || {}
    const validFileIds = selectedRowKeys.value.filter((fileId) => {
      const file = files[fileId]
      return canSelectFile(file)
    })

    if (validFileIds.length === 0) {
      message.info('没有可删除的文件')
      return
    }

    Modal.confirm({
      title: '批量删除文件',
      content: `确定要删除选中的 ${validFileIds.length} 个文件吗？`,
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        state.batchDeleting = true
        let successCount = 0
        let failureCount = 0
        let processedCount = 0
        const totalCount = validFileIds.length
        const progressKey = `batch-delete-${Date.now()}`
        message.loading({ content: `正在删除文件 0/${totalCount}`, key: progressKey, duration: 0 })

        try {
          const CHUNK_SIZE = 50
          for (let i = 0; i < totalCount; i += CHUNK_SIZE) {
            const chunk = validFileIds.slice(i, i + CHUNK_SIZE)

            try {
              const res = await documentApi.batchDeleteDocuments(kbId.value, chunk)
              successCount += res.deleted_count || 0
              if (res.failed_items) {
                failureCount += res.failed_items.length
              }
            } catch (err) {
              console.error(`删除批次 ${i / CHUNK_SIZE + 1} 失败:`, err)
              failureCount += chunk.length
            } finally {
              processedCount += chunk.length
              message.loading({
                content: `正在删除文件 ${processedCount}/${totalCount}`,
                key: progressKey,
                duration: 0
              })
            }
          }

          message.destroy(progressKey)
          if (successCount > 0 && failureCount === 0) {
            message.success(`成功删除 ${successCount} 个文件`)
          } else if (successCount > 0 && failureCount > 0) {
            message.warning(`成功删除 ${successCount} 个文件，${failureCount} 个文件删除失败`)
          } else if (failureCount > 0) {
            message.error(`${failureCount} 个文件删除失败`)
          }

          selectedRowKeys.value = []
          await getKnowledgeBaseInfo(undefined, true) // Skip query params for batch deletion
          await loadDocumentFiles({ isBackground: true })
        } catch (error) {
          message.destroy(progressKey)
          console.error('批量删除出错:', error)
          message.error(error.message || '批量删除过程中发生错误')
        } finally {
          state.batchDeleting = false
        }
      }
    })
  }

  function enableAutoRefresh(source = 'auto') {
    if (autoRefreshManualOverride && source === 'auto') {
      return
    }

    if (!state.autoRefresh) {
      state.autoRefresh = true
      autoRefreshSource = source
      autoRefreshManualOverride = false
      startAutoRefresh()
      return
    }

    if (source === 'auto' && autoRefreshSource !== 'manual') {
      autoRefreshSource = 'auto'
    }
  }

  function ensureAutoRefreshForProcessing(filesMap, stats = null) {
    if (Number(stats?.processing_count || 0) > 0) {
      enableAutoRefresh('auto')
      return true
    }

    const files = Array.isArray(filesMap) ? filesMap : Object.values(filesMap || {})
    const hasPending = files.some((file) => isProcessingFile(file))
    if (hasPending) {
      enableAutoRefresh('auto')
    } else if (autoRefreshSource === 'auto' && state.autoRefresh) {
      state.autoRefresh = false
      autoRefreshSource = null
      autoRefreshManualOverride = false
      stopAutoRefresh()
    }
    return hasPending
  }

  async function loadDocumentFiles(options = {}) {
    const kbIdValue = options.kbId || kbId.value
    const token = userStore.token
    if (!kbIdValue) return
    const requestId = ++fileRequestId

    const nextStatus = options.status ?? fileBrowser.status
    const nextRecursive = options.recursive ?? nextStatus !== 'all'
    const nextParentId = nextRecursive
      ? null
      : options.parentId === null
        ? null
        : (options.parentId ?? fileBrowser.parentId)
    const nextPathPrefix = nextRecursive ? '' : (options.pathPrefix ?? fileBrowser.pathPrefix)
    const nextPage = Number(options.page ?? fileBrowser.page) || 1
    const nextPageSize = Number(options.pageSize ?? fileBrowser.pageSize) || 100
    const contextChanged =
      fileBrowser.parentId !== nextParentId ||
      fileBrowser.page !== nextPage ||
      fileBrowser.pageSize !== nextPageSize ||
      fileBrowser.pathPrefix !== nextPathPrefix ||
      fileBrowser.status !== nextStatus ||
      fileBrowser.recursive !== nextRecursive
    if (contextChanged) fileBrowserContextId += 1
    const contextId = fileBrowserContextId

    Object.assign(fileBrowser, {
      parentId: nextParentId,
      page: nextPage,
      pageSize: nextPageSize,
      pathPrefix: nextPathPrefix,
      status: nextStatus,
      recursive: nextRecursive
    })

    if (!options.isBackground) {
      fileBrowser.loading = true
    }

    try {
      const params = {
        page: nextPage,
        page_size: nextPageSize,
        status: nextStatus,
        recursive: nextRecursive
      }
      if (!nextRecursive && nextParentId) {
        params.parent_id = nextParentId
      }
      if (!nextRecursive && nextPathPrefix) {
        params.path_prefix = nextPathPrefix
      }

      const data = await documentApi.listDocuments(kbIdValue, params)
      if (
        requestId !== fileRequestId ||
        contextId !== fileBrowserContextId ||
        kbIdValue !== kbId.value ||
        token !== userStore.token
      )
        return

      const items = data?.items || []
      fileSnapshotRevision += 1
      documentFiles.value = items
      setCurrentFileMap(items)
      Object.assign(fileBrowser, {
        parentId: nextParentId,
        page: data?.page || nextPage,
        pageSize: data?.page_size || nextPageSize,
        total: data?.total || 0,
        hasMore: Boolean(data?.has_more),
        pathPrefix: data?.path_prefix || nextPathPrefix,
        status: nextStatus,
        recursive: nextRecursive
      })

      if (data?.stats) {
        knowledgeBase.value = {
          ...knowledgeBase.value,
          stats: data.stats,
          row_count: data.stats.row_count
        }
      }
      ensureAutoRefreshForProcessing(items, data?.stats)
    } catch (error) {
      console.error(error)
      if (!options.isBackground) {
        message.error(error.message || '加载文件列表失败')
      }
    } finally {
      if (contextId === fileBrowserContextId && requestId === fileRequestId) {
        fileBrowser.loading = false
      }
    }
  }

  async function enterFolder(folder) {
    if (!folder?.is_folder) return
    const isVirtualFolder = Boolean(folder.is_virtual_folder)
    const currentParentId = fileBrowser.parentId
    folderBreadcrumbs.value = [
      ...folderBreadcrumbs.value,
      {
        file_id: folder.file_id,
        filename: folder.filename,
        is_virtual_folder: isVirtualFolder,
        parent_id: isVirtualFolder ? currentParentId : folder.file_id,
        path_prefix: isVirtualFolder ? folder.path_prefix || '' : ''
      }
    ]
    selectedRowKeys.value = []
    await loadDocumentFiles({
      parentId: isVirtualFolder ? currentParentId : folder.file_id,
      pathPrefix: isVirtualFolder ? folder.path_prefix || '' : '',
      page: 1,
      status: 'all',
      recursive: false
    })
  }

  async function goToFolder(index) {
    const nextBreadcrumbs = folderBreadcrumbs.value.slice(0, index + 1)
    const target = nextBreadcrumbs[nextBreadcrumbs.length - 1]
    folderBreadcrumbs.value = nextBreadcrumbs
    selectedRowKeys.value = []
    const isVirtualFolder = Boolean(target?.is_virtual_folder)
    await loadDocumentFiles({
      parentId: isVirtualFolder ? target?.parent_id || null : target?.file_id || null,
      pathPrefix: isVirtualFolder ? target?.path_prefix || '' : '',
      page: 1,
      status: 'all',
      recursive: false
    })
  }

  /** 绑定提交时的账号与知识库，在作业终态回读文件和统计。 */
  function createFileJobRegistration() {
    const submittedKbId = kbId.value
    const token = userStore.token
    return jobsStore.createJobRegistration(() => {
      if (kbId.value !== submittedKbId || userStore.token !== token) return
      void getKnowledgeBaseInfo(undefined, true, true)
      void loadDocumentFiles({ isBackground: true })
    })
  }

  async function addFiles({ items, contentType, params, parentId }) {
    const registerJob = createFileJobRegistration()
    if (items.length === 0) {
      message.error(contentType === 'file' ? '请先上传文件' : '请输入有效的网页链接')
      return
    }

    state.chunkLoading = true
    try {
      const requestParams = { ...params, content_type: contentType }
      if (parentId) {
        requestParams.parent_id = parentId
      }
      const data = await documentApi.addDocuments(kbId.value, items, requestParams)
      if (data.status === 'success' || data.status === 'queued') {
        const itemType = contentType === 'file' ? '文件' : 'URL'
        enableAutoRefresh('auto')
        message.success(data.message || `${itemType}已提交处理，请查看文件列表中的状态`)
        if (data.job_id) {
          registerJob({ job_id: data.job_id })
        }
        await delayedRefresh() // 延迟1秒后刷新
        return true // Indicate success
      } else {
        message.error(data.message || '处理失败')
        return false
      }
    } catch (error) {
      console.error(error)
      message.error(error.message || '处理请求失败')
      return false
    } finally {
      state.chunkLoading = false
    }
  }

  async function parseFiles(fileIds, params = {}) {
    const registerJob = createFileJobRegistration()
    if (fileIds.length === 0) return
    state.chunkLoading = true
    try {
      const data = await documentApi.parseDocuments(kbId.value, fileIds, params)
      if (data.status === 'success' || data.status === 'queued') {
        enableAutoRefresh('auto')
        message.success(data.message || '解析任务已提交')
        if (data.job_id) {
          registerJob({ job_id: data.job_id })
        }
        await delayedRefresh() // 延迟1秒后刷新
        return true
      } else {
        message.error(data.message || '提交失败')
        return false
      }
    } catch (error) {
      console.error(error)
      message.error(error.message || '请求失败')
      return false
    } finally {
      state.chunkLoading = false
    }
  }

  async function parsePendingFiles(params = {}) {
    const registerJob = createFileJobRegistration()
    state.chunkLoading = true
    try {
      const data = await documentApi.parsePendingDocuments(kbId.value, params)
      if (data.status === 'success' || data.status === 'queued') {
        enableAutoRefresh('auto')
        message.success(data.message || '解析任务已提交')
        if (data.job_id) {
          registerJob({ job_id: data.job_id })
        }
        await delayedRefresh()
        return true
      } else {
        message.error(data.message || '提交失败')
        return false
      }
    } catch (error) {
      console.error(error)
      message.error(error.message || '请求失败')
      return false
    } finally {
      state.chunkLoading = false
    }
  }

  async function indexFiles(fileIds, params = {}) {
    const registerJob = createFileJobRegistration()
    if (fileIds.length === 0) return
    state.chunkLoading = true
    try {
      const data = await documentApi.indexDocuments(kbId.value, fileIds, params)
      if (data.status === 'success' || data.status === 'queued') {
        enableAutoRefresh('auto')
        message.success(data.message || '入库任务已提交')
        if (data.job_id) {
          registerJob({ job_id: data.job_id })
        }
        await delayedRefresh() // 延迟1秒后刷新
        return true
      } else {
        message.error(data.message || '提交失败')
        return false
      }
    } catch (error) {
      console.error(error)
      message.error(error.message || '请求失败')
      return false
    } finally {
      state.chunkLoading = false
    }
  }

  async function indexPendingFiles(params = {}) {
    const registerJob = createFileJobRegistration()
    state.chunkLoading = true
    try {
      const data = await documentApi.indexPendingDocuments(kbId.value, params)
      if (data.status === 'success' || data.status === 'queued') {
        enableAutoRefresh('auto')
        message.success(data.message || '入库任务已提交')
        if (data.job_id) {
          registerJob({ job_id: data.job_id })
        }
        await delayedRefresh()
        return true
      } else {
        message.error(data.message || '提交失败')
        return false
      }
    } catch (error) {
      console.error(error)
      message.error(error.message || '请求失败')
      return false
    } finally {
      state.chunkLoading = false
    }
  }

  function openFileDetail(fileId) {
    const nextFileId = typeof fileId === 'object' ? fileId?.file_id : fileId
    if (!nextFileId) {
      message.error('文件信息不完整')
      return
    }
    fileDetailFileId.value = nextFileId
    state.fileDetailModalVisible = true
  }

  function closeFileDetail() {
    state.fileDetailModalVisible = false
    fileDetailFileId.value = null
  }

  async function loadQueryParams(id) {
    const kbIdValue = id || kbId.value
    if (!kbIdValue) return

    state.queryParamsLoading = true
    try {
      const response = await queryApi.getKnowledgeBaseQueryParams(kbIdValue)
      queryParams.value = response.params?.options || []

      // Create a set of currently supported parameter keys
      const supportedParamKeys = new Set(queryParams.value.map((param) => param.key))

      // Remove unsupported parameters from meta
      for (const key in meta) {
        if (key !== 'kb_id' && !supportedParamKeys.has(key)) {
          delete meta[key]
        }
      }

      // Add default values for supported parameters that are not in meta
      queryParams.value.forEach((param) => {
        if (!(param.key in meta)) {
          meta[param.key] = param.default
        }
      })
    } catch (error) {
      console.error('Failed to load query params:', error)
      message.error('加载查询参数失败')
    } finally {
      state.queryParamsLoading = false
    }
  }

  // 链式调度：等上一轮请求全部返回后再排下一轮，避免慢接口下请求堆积重叠
  function scheduleAutoRefresh() {
    refreshTimer = setTimeout(runAutoRefreshTick, refreshIntervalMs)
  }

  async function runAutoRefreshTick() {
    const generation = refreshGeneration
    refreshTimer = null
    if (!state.autoRefresh) return

    await Promise.all([
      getKnowledgeBaseInfo(undefined, true, true), // Skip loading query params during auto-refresh
      loadDocumentFiles({ isBackground: true })
    ])

    // 期间被重新 start/stop，本轮的退避结论作废
    if (generation !== refreshGeneration) return
    if (!state.autoRefresh) return

    // 处理中文件数量持续不变则按 2 倍退避，达到上限仍无进展即自动停止（覆盖僵尸状态）
    const processingCount = Number(knowledgeBase.value?.stats?.processing_count || 0)
    if (processingCount === refreshLastProcessingCount) {
      refreshStablePolls += 1
      refreshIntervalMs = Math.min(refreshIntervalMs * 2, AUTO_REFRESH_MAX_INTERVAL_MS)
    } else {
      refreshStablePolls = 0
      refreshIntervalMs = AUTO_REFRESH_POLL_INTERVAL_MS
    }
    refreshLastProcessingCount = processingCount

    if (refreshStablePolls >= AUTO_REFRESH_STALE_POLLS_LIMIT) {
      state.autoRefresh = false
      autoRefreshSource = null
      autoRefreshManualOverride = false
      stopAutoRefresh()
      return
    }
    scheduleAutoRefresh()
  }

  function startAutoRefresh() {
    if (!state.autoRefresh) return
    refreshGeneration += 1
    refreshStablePolls = 0
    refreshIntervalMs = AUTO_REFRESH_POLL_INTERVAL_MS
    refreshLastProcessingCount = Number(knowledgeBase.value?.stats?.processing_count || 0)
    if (refreshTimer) {
      clearTimeout(refreshTimer)
      refreshTimer = null
    }
    scheduleAutoRefresh()
  }

  function stopAutoRefresh() {
    refreshGeneration += 1
    if (refreshTimer) {
      clearTimeout(refreshTimer)
      refreshTimer = null
    }
  }

  // 延时刷新文件理解（延迟1秒后刷新）
  async function delayedRefresh() {
    await new Promise((resolve) => setTimeout(resolve, 1000))
    await getKnowledgeBaseInfo(undefined, true)
    await loadDocumentFiles({ isBackground: true })
  }

  function toggleAutoRefresh() {
    const nextState = !state.autoRefresh
    state.autoRefresh = nextState
    if (nextState) {
      autoRefreshSource = 'manual'
      autoRefreshManualOverride = false
      startAutoRefresh()
    } else {
      autoRefreshManualOverride = true
      autoRefreshSource = null
      stopAutoRefresh()
    }
  }

  function selectAllFailedFiles() {
    const files = Object.values(knowledgeBase.value.files || {})
    const failedFiles = files.filter((file) => file.status === 'failed').map((file) => file.file_id)

    const newSelectedKeys = [...new Set([...selectedRowKeys.value, ...failedFiles])]
    selectedRowKeys.value = newSelectedKeys

    if (failedFiles.length > 0) {
      message.success(`已选择 ${failedFiles.length} 个失败的文件`)
    } else {
      message.info('当前没有失败的文件')
    }
  }

  function getKnowledgeBaseNameById(id) {
    const normalizedId = String(id || '').trim()
    if (!normalizedId) return ''

    const matchedKnowledgeBase = knowledgeBases.value.find(
      (item) => String(item.kb_id || '').trim() === normalizedId
    )
    if (matchedKnowledgeBase?.name) return matchedKnowledgeBase.name

    if (String(knowledgeBase.value?.kb_id || '').trim() === normalizedId) {
      return knowledgeBase.value?.name || ''
    }

    return ''
  }

  return {
    knowledgeBases,
    knowledgeBase,
    kbId,
    fileDetailFileId,
    documentFiles,
    folderBreadcrumbs,
    queryParams,
    meta,
    selectedRowKeys,
    fileBrowser,
    state,
    loadKnowledgeBases,
    createKnowledgeBase,
    getKnowledgeBaseInfo,
    updateKnowledgeBaseInfo,
    deleteKnowledgeBase,
    deleteFile,
    handleDeleteFile,
    handleBatchDelete,
    addFiles,
    parseFiles,
    parsePendingFiles,
    indexFiles,
    indexPendingFiles,
    openFileDetail,
    closeFileDetail,
    loadQueryParams,
    loadDocumentFiles,
    enterFolder,
    goToFolder,
    resetFileBrowser,

    startAutoRefresh,
    stopAutoRefresh,
    toggleAutoRefresh,
    selectAllFailedFiles,
    getKnowledgeBaseNameById
  }
})
