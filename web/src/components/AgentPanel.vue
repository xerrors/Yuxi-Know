<template>
  <div class="agent-panel" :class="{ resizing: isResizing }">
    <!-- 拖拽手柄 -->
    <div class="resize-handle" @mousedown="startResize"></div>
    <div class="panel-header">
      <div class="panel-title">
        <FolderCode :size="18" class="header-icon" />
        <span><strong>状态工作台</strong></span>
      </div>
      <div class="header-actions">
        <a-button type="text" class="refresh-btn" @click="emitRefresh">
          <!-- <template #icon><RefreshCw :size="14" /></template> -->
          刷新
        </a-button>
        <button class="close-btn" @click="$emit('close')">
          <X :size="18" />
        </button>
      </div>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: activeTab === 'files' }" @click="activeTab = 'files'">
        文件 ({{ fileCount }})
      </button>
      <button class="tab" :class="{ active: activeTab === 'todos' }" @click="activeTab = 'todos'">
        任务 ({{ completedCount }}/{{ todos.length }})
      </button>
    </div>
    <div class="tab-content">
      <!-- Todo Display -->
      <div v-if="activeTab === 'todos'" class="todo-display">
        <div v-if="!todos.length" class="empty">暂无任务</div>
        <div v-else class="todo-list" ref="todoListRef">
          <div v-for="(todo, index) in todos" :key="index" class="todo-item">
            <div class="todo-status">
              <CheckCircleOutlined v-if="todo.status === 'completed'" class="icon completed" />
              <SyncOutlined
                v-else-if="todo.status === 'in_progress'"
                class="icon in-progress"
                spin
              />
              <ClockCircleOutlined v-else-if="todo.status === 'pending'" class="icon pending" />
              <CloseCircleOutlined v-else-if="todo.status === 'cancelled'" class="icon cancelled" />
              <QuestionCircleOutlined v-else class="icon unknown" />
            </div>
            <a-tooltip v-if="overflowedIds.has(index)" placement="topLeft" :title="todo.content">
              <span class="todo-text">{{ todo.content }}</span>
            </a-tooltip>
            <span v-else class="todo-text">{{ todo.content }}</span>
          </div>
        </div>
      </div>

      <!-- Files Display -->
      <div v-if="activeTab === 'files'" class="files-display">
        <div v-if="!fileCount" class="empty">暂无文件</div>
        <div v-else class="file-tree-container">
          <FileTreeComponent
            v-model:expandedKeys="expandedKeys"
            :tree-data="fileTreeData"
            @select="onFileSelect"
          >
            <template #title="{ node }">
              <div class="tree-node-name" :title="node.title">
                <span class="name-start">{{ node.nameStart || node.title }}</span>
                <span class="name-end" v-if="node.nameEnd">{{ node.nameEnd }}</span>
              </div>
            </template>
            <template #actions="{ node }">
              <div v-if="node.isLeaf" class="node-actions-container">
                <button
                  class="tree-action-btn tree-download-btn"
                  @click.stop="downloadFile(node.fileData)"
                  title="下载文件"
                >
                  <Download :size="14" />
                </button>
              </div>
            </template>
          </FileTreeComponent>
        </div>
      </div>
    </div>

    <!-- 文件内容 Modal -->
    <a-modal
      v-model:open="modalVisible"
      width="800px"
      :style="{ maxWidth: '90vw', top: '5vh' }"
      :bodyStyle="{ maxHeight: '90vh', overflow: 'auto' }"
      :footer="null"
      :closable="false"
      @cancel="closeModal"
    >
      <template #title>
        <div class="modal-header-title">
          <div class="file-title">
            <component
              :is="getFileIcon(currentFilePath)"
              :style="{ color: getFileIconColor(currentFilePath), fontSize: '18px' }"
            />
            <span class="file-path-title">{{ currentFilePath }}</span>
          </div>
          <div class="modal-actions">
            <button
              class="modal-action-btn"
              @click="downloadFile(currentFile)"
              v-if="currentFile"
              title="下载"
            >
              <Download :size="18" />
            </button>
            <button class="modal-action-btn" @click="closeModal" title="关闭">
              <X :size="18" />
            </button>
          </div>
        </div>
      </template>
      <div class="file-content flat-md-preview">
        <template v-if="isMarkdown">
          <MdPreview
            :modelValue="formatContent(currentFile?.content)"
            :theme="theme"
            previewTheme="github"
          />
        </template>
        <template v-else>
          <pre v-if="Array.isArray(currentFile?.content)">{{
            formatContent(currentFile.content)
          }}</pre>
          <div v-else-if="typeof currentFile?.content === 'string'">{{ currentFile.content }}</div>
          <pre v-else>{{ JSON.stringify(currentFile, null, 2) }}</pre>
        </template>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUpdated, nextTick, watch } from 'vue'
import { Download, X, FolderCode, RefreshCw, Folder, FolderOpen } from 'lucide-vue-next'
import {
  CheckCircleOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons-vue'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { useThemeStore } from '@/stores/theme'
import { getFileIcon, getFileIconColor, formatFileSize } from '@/utils/file_utils'
import FileTreeComponent from '@/components/FileTreeComponent.vue'

const props = defineProps({
  agentState: {
    type: Object,
    default: () => ({})
  },
  threadId: {
    type: String,
    default: null
  },
  panelRatio: {
    type: Number,
    default: 0.35
  }
})

const emit = defineEmits(['refresh', 'close', 'resize', 'resizing'])

const activeTab = ref('files')
const modalVisible = ref(false)
const currentFile = ref(null)
const currentFilePath = ref('')

const themeStore = useThemeStore()
const theme = computed(() => (themeStore.isDark ? 'dark' : 'light'))

const isMarkdown = computed(() => {
  return currentFilePath.value?.toLowerCase().endsWith('.md')
})

const todos = computed(() => {
  return props.agentState?.todos || []
})

const files = computed(() => {
  return props.agentState?.files || []
})

const completedCount = computed(() => {
  return todos.value.filter((t) => t.status === 'completed').length
})

// 溢出检测
const overflowedIds = ref(new Set())
const todoListRef = ref(null)

const checkOverflow = () => {
  if (!todoListRef.value) return

  const newOverflowed = new Set()
  const textElements = todoListRef.value.querySelectorAll('.todo-text')
  textElements.forEach((el, index) => {
    if (el.scrollWidth > el.clientWidth) {
      newOverflowed.add(index)
    }
  })

  // 简单的 Set 相等性检查，防止无限循环
  if (overflowedIds.value.size === newOverflowed.size) {
    let isSame = true
    for (const val of newOverflowed) {
      if (!overflowedIds.value.has(val)) {
        isSame = false
        break
      }
    }
    if (isSame) return
  }

  overflowedIds.value = newOverflowed
}

onMounted(() => {
  nextTick(checkOverflow)
  updateActiveTab()
})

onUpdated(() => {
  nextTick(checkOverflow)
})

// 适配实际数据格式
const normalizedFiles = computed(() => {
  const rawFiles = files.value
  const result = []

  // 兼容字典格式 {"/path/file": {content: [...]}} 和旧数组格式
  if (typeof rawFiles === 'object' && !Array.isArray(rawFiles) && rawFiles !== null) {
    // 新格式：字典格式
    Object.entries(rawFiles).forEach(([filePath, fileData]) => {
      result.push({
        path: filePath,
        ...fileData
      })
    })
  } else if (Array.isArray(rawFiles)) {
    // 旧格式：数组格式
    rawFiles.forEach((item) => {
      if (typeof item === 'object' && item !== null) {
        Object.entries(item).forEach(([filePath, fileData]) => {
          result.push({
            path: filePath,
            ...fileData
          })
        })
      }
    })
  }

  return result
})

// 自动切换 tab 逻辑：如果 files 为空且有 todos，自动切换到 todos tab
const updateActiveTab = () => {
  const fileList = normalizedFiles.value
  const todoList = todos.value

  // 如果当前是 files tab，但文件为空且有 todos，切换到 todos
  if (activeTab.value === 'files' && fileList.length === 0 && todoList.length > 0) {
    activeTab.value = 'todos'
  }
}

// 监听 files 和 todos 变化，自动切换 tab
watch([() => props.agentState?.files, () => props.agentState?.todos], () => {
  updateActiveTab()
}, { deep: true })

const expandedKeys = ref([])

const buildTreeData = (filesList) => {
  if (!filesList.length) return []

  const root = []

  // Helper to find or create folder node
  const findOrCreateFolder = (nodes, key, title) => {
    let node = nodes.find((n) => n.key === key)
    if (!node) {
      node = {
        key,
        title,
        isLeaf: false,
        children: [],
        class: 'folder-node'
      }
      nodes.push(node)
    }
    return node
  }

  filesList.forEach((file) => {
    const cleanPath = file.path.startsWith('/') ? file.path.slice(1) : file.path
    const parts = cleanPath.split('/')
    let currentLevel = root
    let currentPath = ''

    parts.forEach((part, index) => {
      const isLast = index === parts.length - 1
      currentPath = currentPath ? `${currentPath}/${part}` : part

      if (isLast) {
        const nameParts = part.split('.')
        let nameStart = part
        let nameEnd = ''

        if (nameParts.length > 1) {
          // If extension exists
          const ext = nameParts.pop()
          // Keep last 5 chars if possible, or just the extension
          // User asked for "last 5 chars".
          // If we treat the whole thing as a string:
          if (part.length > 5) {
            nameEnd = part.slice(-5)
            nameStart = part.slice(0, -5)
          } else {
            nameStart = part
            nameEnd = ''
          }
        } else {
          if (part.length > 5) {
            nameEnd = part.slice(-5)
            nameStart = part.slice(0, -5)
          }
        }

        currentLevel.push({
          key: currentPath,
          title: part,
          nameStart,
          nameEnd,
          isLeaf: true,
          fileData: file,
          class: 'file-node'
        })
      } else {
        const folderNode = findOrCreateFolder(currentLevel, currentPath, part)
        currentLevel = folderNode.children
      }
    })
  })

  const sortNodes = (nodes) => {
    nodes.sort((a, b) => {
      if (a.isLeaf === b.isLeaf) {
        return a.title.localeCompare(b.title)
      }
      return a.isLeaf ? 1 : -1
    })
    nodes.forEach((node) => {
      if (node.children) sortNodes(node.children)
    })
  }

  sortNodes(root)
  return root
}

// Helper to truncate filename with tail preservation
const truncateFilename = (name) => {
  if (!name) return ''
  // This is a visual truncation helper; for true dynamic CSS truncation,
  // we'd need a more complex setup. Here we rely on CSS text-overflow
  // but if we want specifically "last 5 chars" visible, we might need
  // to split the string if we were using a JS-only approach.
  // However, the user asked for "show ellipsis, and last 5 chars".
  // CSS `text-overflow: ellipsis` puts it at the end.
  // To do middle truncation via CSS is hard.
  // Let's try to do it via JS for the title attribute, but for visual
  // we might use a CSS trick or just standard ellipsis if the JS one is too static.
  // Let's stick to standard ellipsis for now but maybe try to implement the requested logic if possible.
  // Actually, pure CSS start/end truncation is tricky.
  // Let's provide a computed display name logic in the template or a method.
  return name
}

const fileTreeData = computed(() => buildTreeData(normalizedFiles.value))

const onFileSelect = (selectedKeys, { node }) => {
  if (node.isLeaf) {
    if (node.fileData) {
      showFileContent(node.key, node.fileData)
    }
  }
}

const fileCount = computed(() => {
  return normalizedFiles.value.length
})

// 方法
const getFileName = (fileItem) => {
  if (fileItem.path) {
    return fileItem.path.split('/').pop() || fileItem.path
  }
  return '未知文件'
}

const formatDate = (dateString) => {
  if (!dateString) return ''
  try {
    const date = new Date(dateString)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch (error) {
    return dateString
  }
}

const formatContent = (contentArray) => {
  if (!Array.isArray(contentArray)) return String(contentArray)
  return contentArray.join('\n')
}

const showFileContent = (filePath, fileData) => {
  currentFilePath.value = filePath
  currentFile.value = fileData
  modalVisible.value = true
}

const closeModal = () => {
  modalVisible.value = false
  currentFile.value = null
  currentFilePath.value = ''
}

const downloadFile = (fileItem) => {
  try {
    // /attachments/ 下的文件直接从内容下载（已经是 Markdown）
    if (fileItem.path?.startsWith('/attachments/') && fileItem.content) {
      const content = formatContent(fileItem.content)
      const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = getFileName(fileItem)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      return
    }

    // 其他文件：优先使用 minio_url 下载源文件
    if (fileItem.minio_url) {
      const link = document.createElement('a')
      link.href = fileItem.minio_url
      link.download = getFileName(fileItem)
      link.target = '_blank'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      return
    }

    // 降级：从 content 创建下载
    const content = formatContent(fileItem.content)
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = getFileName(fileItem)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (error) {
    console.error('下载文件失败:', error)
  }
}

const emitRefresh = () => {
  emit('refresh')
}

// 拖拽调整宽度相关
const isResizing = ref(false)
const startX = ref(0)

const startResize = (e) => {
  isResizing.value = true
  emit('resizing', true)
  startX.value = e.clientX
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', stopResize)
}

const onMouseMove = (e) => {
  if (!isResizing.value) return
  const deltaX = e.clientX - startX.value
  startX.value = e.clientX
  emit('resize', deltaX)
}

const stopResize = () => {
  if (isResizing.value) {
    isResizing.value = false
    emit('resizing', false)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', stopResize)
  }
}
</script>

<style scoped lang="less">
.resize-handle {
  position: absolute;
  left: -2px;
  top: 50%;
  transform: translateY(-50%);
  height: 32px;
  width: 4px;
  cursor: col-resize;
  background: var(--gray-300);
  border-radius: 2px;
  z-index: 10;
  transition: background 0.2s;

  &:hover {
    background: var(--main-400);
  }
}

.agent-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--gray-0);
  transition: none;

  &.resizing {
    transition: none;
  }
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 16px;
  height: 48px;
  background: var(--gray-25);
  flex-shrink: 0;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
  color: var(--gray-900);

  .header-icon {
    color: var(--gray-700);
  }
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.refresh-btn {
  color: var(--gray-700);
  font-size: 13px;
  height: 24px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
}

.close-btn {
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--gray-500);
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover {
    background: var(--gray-100);
    color: var(--gray-700);
  }
}

.tabs {
  display: flex;
  background: var(--gray-25);
  position: relative;
  align-items: center;
  padding: 8px 10px;
  padding-top: 0px;
  gap: 4px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--gray-150);
}

.tab {
  padding: 4px 12px;
  border: none;
  background: none;
  color: var(--gray-600);
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.15s ease;
  border-radius: 999px;

  &:hover {
    background: var(--gray-150);
    color: var(--gray-900);
  }

  &.active {
    background: var(--gray-150);
    color: var(--gray-900);
  }
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  min-height: 0; /* Important for flex child scroll */

  /* 自定义滚动条 */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: var(--gray-50);
  }

  &::-webkit-scrollbar-thumb {
    background: var(--gray-300);
    border-radius: 3px;

    &:hover {
      background: var(--gray-400);
    }
  }
}

.empty {
  text-align: center;
  color: var(--gray-500);
  padding: 60px 0;
  font-size: 14px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;

  &::before {
    content: '📋';
    font-size: 32px;
    opacity: 0.6;
  }
}

.todo-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid var(--gray-150);
  transition: all 0.15s ease;

  &:hover {
    background: var(--main-10);
    border-color: var(--gray-200);
  }
}

.todo-status {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;

  .icon {
    font-size: 16px;

    &.completed {
      color: #52c41a;
    }
    &.in-progress {
      color: #1890ff;
    }
    &.pending {
      color: #faad14;
    }
    &.cancelled {
      color: #ff4d4f;
    }
    &.unknown {
      color: var(--gray-400);
    }
  }
}

.todo-text {
  flex: 1;
  font-size: 13px;
  line-height: 1.5;
  color: var(--gray-1000);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  .todo-item.completed & {
    color: var(--gray-500);
    text-decoration: line-through;
  }
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding: 0 4px;

  .list-header-left {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .count {
    font-size: 13px;
    color: var(--gray-500);
  }

  .info-icon {
    color: var(--gray-400);
    cursor: help;
    transition: color 0.2s;

    &:hover {
      color: var(--main-500);
    }
  }

  .add-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    height: 28px;
    border: 1px solid var(--gray-200);
    border-radius: 6px;
    background: var(--gray-0);
    color: var(--gray-700);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;

    &:hover:not(:disabled) {
      background: var(--gray-50);
      color: var(--main-700);
      border-color: var(--main-300);
    }

    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  }
}

.file-content {
  min-height: 300px;
  max-height: 60vh;
  overflow-y: auto;
  border-radius: 6px;

  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: var(--gray-50);
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--gray-300);
    border-radius: 4px;

    &:hover {
      background: var(--gray-400);
    }
  }

  pre {
    font-family: 'JetBrains Mono', 'Fira Code', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    color: var(--gray-1000);
    background: transparent;
  }
}

.modal-header-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.file-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.modal-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.modal-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--gray-600);
  cursor: pointer;
  transition: all 0.15s ease;
  padding: 0;

  &:hover {
    background: var(--gray-100);
    color: var(--gray-900);
  }

  &:active {
    background: var(--gray-200);
  }
}

.file-path-title {
  font-family: 'JetBrains Mono', 'Fira Code', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-weight: 600;
  color: var(--gray-1000);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Modal 样式优化 - shadcn 风格 */
:deep(.ant-modal) {
  z-index: 1050;
}

:deep(.ant-modal-content) {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--gray-200);
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
}

:deep(.ant-modal-header) {
  background: var(--main-5);
  border-bottom: 1px solid var(--gray-200);
  padding: 16px 20px;
}

:deep(.ant-modal-title) {
  font-weight: 600;
  color: var(--gray-1000);
  font-family: 'JetBrains Mono', 'Fira Code', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

:deep(.ant-modal-body) {
  padding: 0;
}

/* File Tree Styles - VS Code Style Refined */
.file-tree-container {
  padding: 4px;
  margin: 0 -4px;
}

.tree-node-name {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  font-family:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  font-size: 14px;
  color: var(--gray-800);
}

.name-start {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.name-end {
  flex-shrink: 0;
  white-space: nowrap;
}

.node-actions-container {
  display: flex;
  align-items: center;
  gap: 4px;
}

.tree-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--gray-500);
  cursor: pointer;
  padding: 0;
}

.tree-download-btn:hover {
  color: var(--main-600);
}

/* 附件列表专用样式 */
.attachment-tree :deep(.ant-tree-node-content-wrapper) {
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  margin-bottom: 4px;

  &:hover {
    background-color: var(--gray-50);
    border-color: var(--gray-300);
  }

  &.ant-tree-node-selected {
    background-color: var(--gray-100);
    border-color: var(--main-300);
  }
}
</style>
