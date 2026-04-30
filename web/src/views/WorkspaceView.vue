<template>
  <div class="workspace-view layout-container">
    <PageHeader title="工作区" :loading="loadingTree || loadingPreview" :show-border="true">
      <template #actions>
        <a-button :disabled="activeSourceKey !== 'personal'" @click="openCreateDirectoryModal">
          新建文件夹
        </a-button>
        <a-button :loading="uploadingFile" :disabled="activeSourceKey !== 'personal'" @click="openUploadFilePicker">
          上传文件
        </a-button>
      </template>
    </PageHeader>

    <input ref="uploadInputRef" class="upload-input" type="file" @change="handleUploadInputChange" />

    <div class="workspace-shell" :class="{ 'is-sidebar-collapsed': sidebarCollapsed }">
      <div v-if="!sidebarCollapsed" class="workspace-sidebar-slot">
        <button
          type="button"
          class="sidebar-collapse-action"
          aria-label="收起工作区侧边栏"
          @click="sidebarCollapsed = true"
        >
          <ChevronLeft :size="16" />
        </button>
        <WorkspaceSidebar
          :active-key="activeSourceKey"
          :databases="databases"
          :loading-databases="loadingDatabases"
          @select-personal="selectPersonalWorkspace"
          @select-database="selectDatabase"
        />
      </div>
      <button
        v-else
        type="button"
        class="sidebar-expand-action"
        aria-label="展开工作区侧边栏"
        @click="sidebarCollapsed = false"
      >
        <ChevronRight :size="16" />
      </button>

      <main
        ref="workspaceMainRef"
        class="workspace-main"
        :class="{ 'is-inline-preview': showInlinePreview }"
        :style="workspaceMainStyle"
      >
        <template v-if="activeSourceKey === 'personal'">
          <WorkspaceFileList
            :entries="filteredEntries"
            :current-path="currentPath"
            :selected-path="selectedEntry?.path || ''"
            :selected-paths="selectedPaths"
            :deleting-paths="deletingPaths"
            :selection-mode="selectionMode"
            :loading="loadingTree"
            @select-entry="handleSelectEntry"
            @go-parent="goParentDirectory"
            @update:selected-paths="selectedPaths = $event"
            @update:selection-mode="handleSelectionModeChange"
            @delete-selected="confirmDeleteEntries(selectedEntries)"
            @delete-entry="(entry) => confirmDeleteEntries([entry])"
            @download-entry="downloadEntry"
          />
          <div
            v-if="showInlinePreview"
            class="workspace-preview-resizer"
            role="separator"
            aria-label="调整预览宽度"
            tabindex="0"
            @pointerdown="startPreviewResize"
          ></div>
          <WorkspacePreviewPane
            v-if="showInlinePreview"
            :file="previewFile"
            :file-path="selectedEntry?.path || ''"
            :loading="loadingPreview"
          />
        </template>

        <div v-else class="workspace-placeholder">
          <LibraryBig :size="32" />
          <h2>{{ selectedDatabase?.name || '知识库' }}</h2>
          <p>当前版本仅展示可访问知识库到列表级别，知识库文件浏览后续支持。</p>
        </div>
      </main>
    </div>

    <a-modal
      v-model:open="createDirectoryModalVisible"
      title="新建文件夹"
      okText="创建"
      cancelText="取消"
      :confirm-loading="creatingDirectory"
      @ok="createDirectory"
    >
      <a-input
        v-model:value="newDirectoryName"
        placeholder="请输入文件夹名称"
        :disabled="creatingDirectory"
        @keyup.enter="createDirectory"
      />
    </a-modal>

    <a-modal
      :open="previewModalVisible && !useInlinePreview"
      width="880px"
      :style="{ maxWidth: '92vw', top: '5vh' }"
      :bodyStyle="{ maxHeight: '90vh', overflow: 'auto' }"
      :footer="null"
      :closable="false"
      wrapClassName="workspace-file-preview-modal"
      @cancel="closePreview"
    >
      <AgentFilePreview
        :file="previewFile"
        :filePath="selectedEntry?.path || ''"
        :showClose="true"
        :showDownload="false"
        :showFullscreen="true"
        @close="closePreview"
      />
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { ChevronLeft, ChevronRight, LibraryBig } from 'lucide-vue-next'
import PageHeader from '@/components/shared/PageHeader.vue'
import AgentFilePreview from '@/components/AgentFilePreview.vue'
import WorkspaceFileList from '@/components/workspace/WorkspaceFileList.vue'
import WorkspacePreviewPane from '@/components/workspace/WorkspacePreviewPane.vue'
import WorkspaceSidebar from '@/components/workspace/WorkspaceSidebar.vue'
import { databaseApi } from '@/apis/knowledge_api'
import {
  createWorkspaceDirectory,
  deleteWorkspacePath,
  downloadWorkspaceFile,
  getWorkspaceFileContent,
  getWorkspaceTree,
  uploadWorkspaceFile
} from '@/apis/workspace_api'

const activeSourceKey = ref('personal')
const currentPath = ref('/')
const entries = ref([])
const selectedEntry = ref(null)
const selectedPaths = ref([])
const selectionMode = ref(false)
const previewFile = ref(null)
const previewObjectUrl = ref('')
const previewModalVisible = ref(false)
const loadingTree = ref(false)
const loadingPreview = ref(false)
const loadingDatabases = ref(false)
const databases = ref([])
const selectedDatabase = ref(null)
const searchQuery = ref('')
const workspaceMainRef = ref(null)
const workspaceMainWidth = ref(0)
const createDirectoryModalVisible = ref(false)
const newDirectoryName = ref('')
const creatingDirectory = ref(false)
const uploadingFile = ref(false)
const uploadInputRef = ref(null)
const deletingPaths = ref([])
const sidebarCollapsed = ref(false)
const previewWidthPercent = ref(50)
const INLINE_PREVIEW_MIN_WIDTH = 960

const useInlinePreview = computed(() => workspaceMainWidth.value >= INLINE_PREVIEW_MIN_WIDTH)
const showInlinePreview = computed(() => useInlinePreview.value && Boolean(previewFile.value))
const workspaceMainStyle = computed(() => {
  if (!showInlinePreview.value) return {}
  const listWidthPercent = 100 - previewWidthPercent.value
  return {
    gridTemplateColumns: `minmax(0, ${listWidthPercent}%) 6px minmax(280px, ${previewWidthPercent.value}%)`
  }
})

const filteredEntries = computed(() => {
  const keyword = searchQuery.value.trim().toLowerCase()
  if (!keyword) return entries.value
  return entries.value.filter((entry) => String(entry.name || '').toLowerCase().includes(keyword))
})

const selectedEntries = computed(() => {
  const selectedPathSet = new Set(selectedPaths.value)
  return entries.value.filter((entry) => selectedPathSet.has(entry.path))
})

const revokePreviewObjectUrl = () => {
  if (!previewObjectUrl.value) return
  URL.revokeObjectURL(previewObjectUrl.value)
  previewObjectUrl.value = ''
}

const normalizePreviewFile = async (entry, response) => {
  const previewType = response.preview_type || response.previewType || 'text'
  const file = {
    ...response,
    previewType,
    supported: response.supported !== false
  }

  if (previewType === 'image' || previewType === 'pdf') {
    const response = await downloadWorkspaceFile(entry.path)
    const blob = await response.blob()
    revokePreviewObjectUrl()
    previewObjectUrl.value = URL.createObjectURL(blob)
    file.previewUrl = previewObjectUrl.value
  }

  return file
}

const syncSelectedPaths = () => {
  const entryPathSet = new Set(entries.value.map((entry) => entry.path))
  selectedPaths.value = selectedPaths.value.filter((path) => entryPathSet.has(path))
}

const clearWorkspaceSelection = () => {
  selectedPaths.value = []
}

const handleSelectionModeChange = (enabled) => {
  selectionMode.value = enabled
  if (!enabled) {
    clearWorkspaceSelection()
  }
}

const loadWorkspaceEntries = async (path = '/') => {
  loadingTree.value = true
  try {
    const response = await getWorkspaceTree(path)
    entries.value = response.entries || []
    currentPath.value = path
    syncSelectedPaths()
    if (!selectedPaths.value.length) {
      selectionMode.value = false
    }
  } catch (error) {
    console.warn('加载工作区目录失败:', error)
    message.error('加载工作区目录失败')
  } finally {
    loadingTree.value = false
  }
}

const loadDatabases = async () => {
  loadingDatabases.value = true
  try {
    const response = await databaseApi.getAccessibleDatabases()
    databases.value = response?.databases || []
  } catch (error) {
    console.warn('加载可访问知识库失败:', error)
    databases.value = []
  } finally {
    loadingDatabases.value = false
  }
}

const selectPersonalWorkspace = async () => {
  activeSourceKey.value = 'personal'
  selectedDatabase.value = null
  clearWorkspaceSelection()
  if (!entries.value.length) {
    await loadWorkspaceEntries(currentPath.value)
  }
}

const selectDatabase = (database) => {
  closePreview()
  clearWorkspaceSelection()
  selectedDatabase.value = database
  activeSourceKey.value = `database:${database.db_id}`
}

const handleSelectEntry = async (entry) => {
  if (entry.is_dir) {
    closePreview()
    clearWorkspaceSelection()
    await loadWorkspaceEntries(entry.path)
    return
  }

  selectedEntry.value = entry
  revokePreviewObjectUrl()
  previewFile.value = {
    ...entry,
    content: 'Loading...',
    supported: true,
    previewType: 'text',
    message: '',
    previewUrl: ''
  }
  previewModalVisible.value = !useInlinePreview.value
  loadingPreview.value = true
  try {
    const response = await getWorkspaceFileContent(entry.path)
    previewFile.value = await normalizePreviewFile(entry, response)
  } catch (error) {
    console.warn('加载文件预览失败:', error)
    previewFile.value = {
      ...entry,
      content: `Error loading file: ${error?.message || 'unknown error'}`,
      supported: false,
      previewType: 'unsupported',
      message: error?.message || '文件预览失败',
      previewUrl: ''
    }
    message.error('加载文件预览失败')
  } finally {
    loadingPreview.value = false
  }
}

const closePreview = () => {
  previewModalVisible.value = false
  selectedEntry.value = null
  previewFile.value = null
  revokePreviewObjectUrl()
}

const goParentDirectory = async () => {
  if (currentPath.value === '/') return
  const trimmed = currentPath.value.replace(/\/$/, '')
  const parent = trimmed.slice(0, trimmed.lastIndexOf('/')) || '/'
  closePreview()
  clearWorkspaceSelection()
  await loadWorkspaceEntries(parent)
}

const openCreateDirectoryModal = () => {
  if (activeSourceKey.value !== 'personal') return
  newDirectoryName.value = ''
  createDirectoryModalVisible.value = true
}

const createDirectory = async () => {
  if (creatingDirectory.value) return
  const directoryName = newDirectoryName.value.trim()
  if (!directoryName) {
    message.warning('请输入文件夹名')
    return
  }

  creatingDirectory.value = true
  try {
    await createWorkspaceDirectory(currentPath.value, directoryName)
    await loadWorkspaceEntries(currentPath.value)
    createDirectoryModalVisible.value = false
    newDirectoryName.value = ''
    message.success('文件夹创建成功')
  } catch (error) {
    console.warn('创建文件夹失败:', error)
    message.error(error?.message || '创建文件夹失败')
  } finally {
    creatingDirectory.value = false
  }
}

const openUploadFilePicker = () => {
  if (activeSourceKey.value !== 'personal' || uploadingFile.value) return
  if (uploadInputRef.value) {
    uploadInputRef.value.value = ''
    uploadInputRef.value.click()
  }
}

const handleUploadInputChange = async (event) => {
  const file = event.target?.files?.[0]
  if (!file || uploadingFile.value) return

  uploadingFile.value = true
  try {
    await uploadWorkspaceFile(currentPath.value, file)
    await loadWorkspaceEntries(currentPath.value)
    message.success('文件上传成功')
  } catch (error) {
    console.warn('上传文件失败:', error)
    message.error(error?.message || '上传文件失败')
  } finally {
    uploadingFile.value = false
    event.target.value = ''
  }
}

const comparablePath = (path) => String(path || '/').replace(/\/$/, '') || '/'

const isSameOrChildPath = (path, targetPath) => {
  const normalizedPath = comparablePath(path)
  const normalizedTargetPath = comparablePath(targetPath)
  return normalizedPath === normalizedTargetPath || normalizedPath.startsWith(`${normalizedTargetPath}/`)
}

const confirmDeleteEntries = (targetEntries) => {
  const validEntries = (targetEntries || []).filter(Boolean)
  if (!validEntries.length) return

  const isBatch = validEntries.length > 1
  const firstEntry = validEntries[0]
  Modal.confirm({
    title: isBatch
      ? `确认删除选中的 ${validEntries.length} 项？`
      : firstEntry.is_dir
        ? `确认删除文件夹「${firstEntry.name}」？`
        : `确认删除文件「${firstEntry.name}」？`,
    content: isBatch || firstEntry.is_dir ? '将删除文件夹及其所有内容，删除后不可恢复。' : '删除后不可恢复。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => deleteEntries(validEntries)
  })
}

const deleteEntries = async (targetEntries) => {
  const paths = targetEntries.map((entry) => entry.path)
  deletingPaths.value = paths
  try {
    await Promise.all(paths.map((path) => deleteWorkspacePath(path)))
    if (selectedEntry.value && paths.some((path) => isSameOrChildPath(selectedEntry.value.path, path))) {
      closePreview()
    }
    clearWorkspaceSelection()
    await loadWorkspaceEntries(currentPath.value)
    message.success(paths.length > 1 ? '选中项删除成功' : '删除成功')
  } catch (error) {
    console.warn('删除工作区文件失败:', error)
    message.error(error?.message || '删除失败')
    await loadWorkspaceEntries(currentPath.value)
  } finally {
    deletingPaths.value = []
  }
}

const parseDownloadFilename = (contentDisposition) => {
  if (!contentDisposition) return ''

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match && utf8Match[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch (error) {
      console.warn('解析 UTF-8 文件名失败:', error)
    }
  }

  const asciiMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  if (asciiMatch && asciiMatch[1]) {
    return asciiMatch[1]
  }

  return ''
}

const downloadEntry = async (entry) => {
  if (!entry?.path || entry.is_dir) return

  try {
    const response = await downloadWorkspaceFile(entry.path)
    const blob = await response.blob()
    const contentDisposition =
      response.headers.get('Content-Disposition') || response.headers.get('content-disposition')
    const filename = parseDownloadFilename(contentDisposition) || entry.name || 'download'
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (error) {
    console.warn('下载文件失败:', error)
    message.error(error?.message || '下载文件失败')
  }
}

let resizePointerId = null

const stopPreviewResize = () => {
  resizePointerId = null
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', resizePreview)
  window.removeEventListener('pointerup', stopPreviewResize)
}

const resizePreview = (event) => {
  if (!workspaceMainRef.value || resizePointerId === null) return
  const rect = workspaceMainRef.value.getBoundingClientRect()
  const relativeX = event.clientX - rect.left
  const nextPreviewPercent = Math.round(((rect.width - relativeX) / rect.width) * 100)
  previewWidthPercent.value = Math.min(70, Math.max(30, nextPreviewPercent))
}

const startPreviewResize = (event) => {
  if (!showInlinePreview.value) return
  resizePointerId = event.pointerId
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', resizePreview)
  window.addEventListener('pointerup', stopPreviewResize)
}

let workspaceResizeObserver = null

onMounted(async () => {
  await Promise.all([loadWorkspaceEntries('/'), loadDatabases()])

  if (workspaceMainRef.value && typeof ResizeObserver !== 'undefined') {
    workspaceMainWidth.value = workspaceMainRef.value.clientWidth || 0
    workspaceResizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      workspaceMainWidth.value = entry.contentRect.width
    })
    workspaceResizeObserver.observe(workspaceMainRef.value)
  }
})

onUnmounted(() => {
  workspaceResizeObserver?.disconnect()
  workspaceResizeObserver = null
  stopPreviewResize()
  revokePreviewObjectUrl()
})

watch(useInlinePreview, (isInline) => {
  if (!previewFile.value) {
    previewModalVisible.value = false
    return
  }
  previewModalVisible.value = !isInline
})
</script>

<style scoped lang="less">
.workspace-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.upload-input {
  display: none;
}

.workspace-shell {
  position: relative;
  display: grid;
  grid-template-columns: 195px minmax(0, 1fr);
  flex: 1 1 auto;
  min-height: 0;
  background: var(--gray-0);
  overflow: hidden;

  &.is-sidebar-collapsed {
    grid-template-columns: minmax(0, 1fr);
  }
}

.workspace-sidebar-slot {
  position: relative;
  min-width: 0;
  min-height: 0;
}

.workspace-sidebar-slot :deep(.workspace-sidebar) {
  height: 100%;
}

.sidebar-collapse-action,
.sidebar-expand-action {
  width: 26px;
  height: 26px;
  position: absolute;
  top: 50%;
  z-index: 4;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--gray-150);
  background: var(--gray-0);
  color: var(--gray-600);
  cursor: pointer;
  transform: translateY(-50%);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);

  &:hover {
    background: var(--main-20);
    color: var(--main-color);
  }
}

.sidebar-collapse-action {
  right: -13px;
  width: 26px;
  border-radius: 50%;
}

.sidebar-expand-action {
  left: 0;
  width: 22px;
  border-left: 0;
  border-radius: 0 12px 12px 0;
}

.workspace-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
}

.workspace-preview-resizer {
  width: 6px;
  min-width: 6px;
  border-left: 1px solid var(--gray-100);
  border-right: 1px solid var(--gray-100);
  background: var(--gray-25);
  cursor: col-resize;

  &:hover {
    background: var(--main-20);
  }
}

.workspace-placeholder {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 360px;
  padding: 32px;
  color: var(--gray-500);
  text-align: center;

  h2 {
    margin: 8px 0 0;
    color: var(--gray-900);
    font-size: 18px;
    font-weight: 600;
  }

  p {
    max-width: 360px;
    margin: 0;
    font-size: 14px;
    line-height: 1.6;
  }
}
</style>

<style lang="less">
.workspace-file-preview-modal {
  .ant-modal {
    z-index: 1050;

    .ant-modal-content {
      padding: 0;
      overflow: hidden;
      border: 1px solid var(--gray-200);
      border-radius: 8px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    }

    .ant-modal-body {
      padding: 0;
    }
  }
}
</style>
