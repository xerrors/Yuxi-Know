import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { databaseApi, documentApi, queryApi } from '@/apis/knowledge_api'
import { useTaskerStore } from '@/stores/tasker'
import { useRouter } from 'vue-router'
import { parseToShanghai } from '@/utils/time'

export const useDatabaseStore = defineStore('database', () => {
  const router = useRouter()
  const taskerStore = useTaskerStore()

  // State
  const databases = ref([])
  const database = ref({})
  const databaseId = ref(null)
  const selectedFile = ref(null)

  const queryParams = ref([])
  const meta = reactive({})
  const selectedRowKeys = ref([])

  const state = reactive({
    listLoading: false,
    creating: false,
    databaseLoading: false,
    refrashing: false,
    searchLoading: false,
    lock: false,
    fileDetailModalVisible: false,
    fileDetailLoading: false,
    batchDeleting: false,
    chunkLoading: false,
    autoRefresh: false,
    queryParamsLoading: false,
    rightPanelVisible: true
  })

  let refreshInterval = null
  let autoRefreshSource = null // Tracks whether auto-refresh was user-triggered or automatic
  let autoRefreshManualOverride = false // Indicates user explicitly disabled auto-refresh

  // Actions
  async function loadDatabases() {
    state.listLoading = true
    try {
      const data = await databaseApi.getDatabases()
      databases.value = data.databases.sort((a, b) => {
        const timeA = parseToShanghai(a.created_at)
        const timeB = parseToShanghai(b.created_at)
        if (!timeA && !timeB) return 0
        if (!timeA) return 1
        if (!timeB) return -1
        return timeB.valueOf() - timeA.valueOf() // 降序排列，最新的在前面
      })
    } catch (error) {
      console.error('加载数据库列表失败:', error)
      if (error.message.includes('权限')) {
        message.error('没有权限访问知识库')
      }
      throw error
    } finally {
      state.listLoading = false
    }
  }

  async function createDatabase(formData) {
    // 验证
    if (!formData.database_name?.trim()) {
      message.error('数据库名称不能为空')
      return false
    }

    if (!formData.kb_type) {
      message.error('请选择知识库类型')
      return false
    }

    // 向量数据库的重排序模型验证
    if (['milvus'].includes(formData.kb_type)) {
      if (formData.reranker_config?.enabled && !formData.reranker_config?.model) {
        message.error('请选择重排序模型')
        return false
      }
    }

    state.creating = true
    try {
      const data = await databaseApi.createDatabase(formData)
      message.success('创建成功')
      await loadDatabases() // 刷新列表
      return data
    } catch (error) {
      console.error('创建数据库失败:', error)
      message.error(error.message || '创建失败')
      throw error
    } finally {
      state.creating = false
    }
  }

  async function getDatabaseInfo(id, skipQueryParams = false, isBackground = false) {
    const db_id = id || databaseId.value
    if (!db_id) return

    if (!isBackground) {
      state.lock = true
      state.databaseLoading = true
    }
    try {
      const data = await databaseApi.getDatabaseInfo(db_id)
      database.value = data
      ensureAutoRefreshForProcessing(data?.files)

      // Only load query parameters if explicitly requested or if not loaded yet
      if (!skipQueryParams && queryParams.value.length === 0) {
        await loadQueryParams(db_id)
      }
    } catch (error) {
      console.error(error)
      message.error(error.message || '获取数据库信息失败')
    } finally {
      if (!isBackground) {
        state.lock = false
        state.databaseLoading = false
      }
    }
  }

  async function updateDatabaseInfo(formData) {
    try {
      state.lock = true
      await databaseApi.updateDatabase(databaseId.value, formData)
      message.success('知识库信息更新成功')
      await getDatabaseInfo() // Load query params after updating database info
    } catch (error) {
      console.error(error)
      message.error(error.message || '更新失败')
    } finally {
      state.lock = false
    }
  }

  function deleteDatabase() {
    Modal.confirm({
      title: '删除数据库',
      content: '确定要删除该数据库吗？',
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        state.lock = true
        try {
          const data = await databaseApi.deleteDatabase(databaseId.value)
          message.success(data.message || '删除成功')
          router.push('/database')
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
      await documentApi.deleteDocument(databaseId.value, fileId)
      await getDatabaseInfo(undefined, true) // Skip query params for file deletion
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
    const files = database.value.files || {}
    const validFileIds = selectedRowKeys.value.filter((fileId) => {
      const file = files[fileId]
      return file && !(file.status === 'processing' || file.status === 'waiting')
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
        let progressMessage = message.loading(`正在删除文件 0/${validFileIds.length}`, 0)

        try {
          for (let i = 0; i < validFileIds.length; i++) {
            const fileId = validFileIds[i]
            try {
              await deleteFile(fileId)
              successCount++
            } catch (error) {
              console.error(`删除文件 ${fileId} 失败:`, error)
              failureCount++
            }
            progressMessage?.()
            if (i + 1 < validFileIds.length) {
              progressMessage = message.loading(`正在删除文件 ${i + 1}/${validFileIds.length}`, 0)
            }
          }
          progressMessage?.()
          if (successCount > 0 && failureCount === 0) {
            message.success(`成功删除 ${successCount} 个文件`)
          } else if (successCount > 0 && failureCount > 0) {
            message.warning(`成功删除 ${successCount} 个文件，${failureCount} 个文件删除失败`)
          } else if (failureCount > 0) {
            message.error(`${failureCount} 个文件删除失败`)
          }
          selectedRowKeys.value = []
          await getDatabaseInfo(undefined, true) // Skip query params for batch deletion
        } catch (error) {
          progressMessage?.()
          console.error('批量删除出错:', error)
          message.error('批量删除过程中发生错误')
        } finally {
          state.batchDeleting = false
        }
      }
    })
  }

  const processingStatuses = new Set(['processing', 'waiting', 'parsing', 'indexing'])

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

  function ensureAutoRefreshForProcessing(filesMap) {
    const files = Object.values(filesMap || {})
    const hasPending = files.some((file) => file && processingStatuses.has(file.status))
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

  async function moveFile(fileId, newParentId) {
    state.lock = true
    try {
      await documentApi.moveDocument(databaseId.value, fileId, newParentId)
      await getDatabaseInfo(undefined, true) // Skip query params for file movement
      message.success('移动成功')
    } catch (error) {
      console.error(error)
      message.error(error.message || '移动失败')
      throw error
    } finally {
      state.lock = false
    }
  }

  async function addFiles({ items, contentType, params, parentId }) {
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
      const data = await documentApi.addDocuments(databaseId.value, items, requestParams)
      if (data.status === 'success' || data.status === 'queued') {
        const itemType = contentType === 'file' ? '文件' : 'URL'
        enableAutoRefresh('auto')
        message.success(data.message || `${itemType}已提交处理，请在任务中心查看进度`)
        if (data.task_id) {
          taskerStore.registerQueuedTask({
            task_id: data.task_id,
            name: `知识库导入 (${databaseId.value || ''})`,
            task_type: 'knowledge_ingest',
            message: data.message,
            payload: {
              db_id: databaseId.value,
              count: items.length,
              content_type: contentType
            }
          })
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

  async function parseFiles(fileIds) {
    if (fileIds.length === 0) return
    state.chunkLoading = true
    try {
      const data = await documentApi.parseDocuments(databaseId.value, fileIds)
      if (data.status === 'success' || data.status === 'queued') {
        enableAutoRefresh('auto')
        message.success(data.message || '解析任务已提交')
        if (data.task_id) {
          taskerStore.registerQueuedTask({
            task_id: data.task_id,
            name: `文档解析 (${databaseId.value})`,
            task_type: 'knowledge_parse',
            message: data.message,
            payload: { db_id: databaseId.value, count: fileIds.length }
          })
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

  async function indexFiles(fileIds, params = {}) {
    if (fileIds.length === 0) return
    state.chunkLoading = true
    try {
      const data = await documentApi.indexDocuments(databaseId.value, fileIds, params)
      if (data.status === 'success' || data.status === 'queued') {
        enableAutoRefresh('auto')
        message.success(data.message || '入库任务已提交')
        if (data.task_id) {
          taskerStore.registerQueuedTask({
            task_id: data.task_id,
            name: `文档入库 (${databaseId.value})`,
            task_type: 'knowledge_index',
            message: data.message,
            payload: { db_id: databaseId.value, count: fileIds.length }
          })
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

  async function openFileDetail(record) {
    // 只要有 markdown_file (隐含在 status >= parsed 中) 或者是 error_indexing (说明解析成功但入库失败)，就可以查看
    const allowStatuses = ['done', 'parsed', 'indexed', 'error_indexing']
    if (!allowStatuses.includes(record.status)) {
      message.error('文件未处理完成，请稍后再试')
      return
    }
    state.fileDetailModalVisible = true
    selectedFile.value = { ...record, lines: [] }
    state.fileDetailLoading = true
    state.lock = true

    try {
      const data = await documentApi.getDocumentInfo(databaseId.value, record.file_id)
      if (data.status == 'failed') {
        message.error(data.message)
        state.fileDetailModalVisible = false
        return
      }
      selectedFile.value = { ...record, lines: data.lines || [], content: data.content }
    } catch (error) {
      console.error(error)
      message.error(error.message)
      state.fileDetailModalVisible = false
    } finally {
      state.fileDetailLoading = false
      state.lock = false
    }
  }

  async function loadQueryParams(id) {
    const db_id = id || databaseId.value
    if (!db_id) return

    state.queryParamsLoading = true
    try {
      const response = await queryApi.getKnowledgeBaseQueryParams(db_id)
      queryParams.value = response.params?.options || []

      // Create a set of currently supported parameter keys
      const supportedParamKeys = new Set(queryParams.value.map((param) => param.key))

      // Remove unsupported parameters from meta
      for (const key in meta) {
        if (key !== 'db_id' && !supportedParamKeys.has(key)) {
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

  function startAutoRefresh() {
    if (state.autoRefresh && !refreshInterval) {
      refreshInterval = setInterval(() => {
        getDatabaseInfo(undefined, true, true) // Skip loading query params during auto-refresh
      }, 1000)
    }
  }

  function stopAutoRefresh() {
    if (refreshInterval) {
      clearInterval(refreshInterval)
      refreshInterval = null
    }
  }

  // 延时刷新文件理解（延迟1秒后刷新）
  async function delayedRefresh() {
    await new Promise((resolve) => setTimeout(resolve, 1000))
    await getDatabaseInfo(undefined, true)
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
    const files = Object.values(database.value.files || {})
    const failedFiles = files.filter((file) => file.status === 'failed').map((file) => file.file_id)

    const newSelectedKeys = [...new Set([...selectedRowKeys.value, ...failedFiles])]
    selectedRowKeys.value = newSelectedKeys

    if (failedFiles.length > 0) {
      message.success(`已选择 ${failedFiles.length} 个失败的文件`)
    } else {
      message.info('当前没有失败的文件')
    }
  }

  return {
    databases,
    database,
    databaseId,
    selectedFile,
    queryParams,
    meta,
    selectedRowKeys,
    state,
    loadDatabases,
    createDatabase,
    getDatabaseInfo,
    updateDatabaseInfo,
    deleteDatabase,
    deleteFile,
    handleDeleteFile,
    handleBatchDelete,
    moveFile,
    addFiles,
    parseFiles,
    indexFiles,
    openFileDetail,
    loadQueryParams,

    startAutoRefresh,
    stopAutoRefresh,
    toggleAutoRefresh,
    selectAllFailedFiles
  }
})
