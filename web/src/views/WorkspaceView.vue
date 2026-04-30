<template>
  <div class="workspace-view layout-container">
    <PageHeader title="工作区" :loading="loadingTree || loadingPreview" :show-border="true">
      <template #info>
        <span class="workspace-info">个人文件的只读预览空间</span>
      </template>
      <template #actions>
        <a-tooltip title="即将支持">
          <a-button type="primary" disabled>新建文件夹</a-button>
        </a-tooltip>
      </template>
    </PageHeader>

    <div class="workspace-shell">
      <WorkspaceSidebar
        :active-key="activeSourceKey"
        :databases="databases"
        :loading-databases="loadingDatabases"
        @select-personal="selectPersonalWorkspace"
        @select-database="selectDatabase"
      />

      <main
        ref="workspaceMainRef"
        class="workspace-main"
        :class="{ 'is-inline-preview': useInlinePreview }"
      >
        <template v-if="activeSourceKey === 'personal'">
          <WorkspaceFileList
            :entries="filteredEntries"
            :current-path="currentPath"
            :selected-path="selectedEntry?.path || ''"
            :loading="loadingTree"
            @select-entry="handleSelectEntry"
            @go-parent="goParentDirectory"
          />
          <WorkspacePreviewPane
            v-if="useInlinePreview"
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
import { message } from 'ant-design-vue'
import { LibraryBig } from 'lucide-vue-next'
import PageHeader from '@/components/shared/PageHeader.vue'
import AgentFilePreview from '@/components/AgentFilePreview.vue'
import WorkspaceFileList from '@/components/workspace/WorkspaceFileList.vue'
import WorkspacePreviewPane from '@/components/workspace/WorkspacePreviewPane.vue'
import WorkspaceSidebar from '@/components/workspace/WorkspaceSidebar.vue'
import { databaseApi } from '@/apis/knowledge_api'
import { downloadWorkspaceFile, getWorkspaceFileContent, getWorkspaceTree } from '@/apis/workspace_api'

const activeSourceKey = ref('personal')
const currentPath = ref('/')
const entries = ref([])
const selectedEntry = ref(null)
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
const INLINE_PREVIEW_MIN_WIDTH = 960

const useInlinePreview = computed(() => workspaceMainWidth.value >= INLINE_PREVIEW_MIN_WIDTH)

const filteredEntries = computed(() => {
  const keyword = searchQuery.value.trim().toLowerCase()
  if (!keyword) return entries.value
  return entries.value.filter((entry) => String(entry.name || '').toLowerCase().includes(keyword))
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
    const blob = await downloadWorkspaceFile(entry.path)
    revokePreviewObjectUrl()
    previewObjectUrl.value = URL.createObjectURL(blob)
    file.previewUrl = previewObjectUrl.value
  }

  return file
}

const loadWorkspaceEntries = async (path = '/') => {
  loadingTree.value = true
  try {
    const response = await getWorkspaceTree(path)
    entries.value = response.entries || []
    currentPath.value = path
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
  if (!entries.value.length) {
    await loadWorkspaceEntries(currentPath.value)
  }
}

const selectDatabase = (database) => {
  selectedDatabase.value = database
  activeSourceKey.value = `database:${database.db_id}`
}

const handleSelectEntry = async (entry) => {
  if (entry.is_dir) {
    closePreview()
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
  await loadWorkspaceEntries(parent)
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

.workspace-info {
  color: var(--gray-500);
  font-size: 13px;
}

.workspace-shell {
  display: grid;
  grid-template-columns: clamp(210px, 18vw, 280px) minmax(0, 1fr);
  flex: 1 1 auto;
  min-height: 0;
  // margin: 16px var(--page-padding) var(--page-padding);
  // border: 1px solid var(--gray-100);
  // border-radius: 12px;
  background: var(--gray-0);
  overflow: hidden;
}

.workspace-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
}

.workspace-main.is-inline-preview {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
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
