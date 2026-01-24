<template>
  <div class="agent-panel">
    <div class="panel-header">
      <div class="panel-title">状态工作台</div>
      <div class="header-actions">
        <a-button type="text" class="refresh-btn" @click="emitRefresh">
          <template #icon><RefreshCw :size="16" /></template>
          刷新
        </a-button>
        <button class="close-btn" @click="$emit('close')">
          <X :size="18" />
        </button>
      </div>
    </div>

    <div class="tabs">
      <button
        class="tab"
        :class="{ active: activeTab === 'todos' }"
        @click="activeTab = 'todos'"
        v-if="hasTodos"
      >
        任务 ({{ todoCount }})
      </button>
      <button
        class="tab"
        :class="{ active: activeTab === 'files' }"
        @click="activeTab = 'files'"
        v-if="hasFiles"
      >
        文件 ({{ fileCount }})
      </button>
      <button
        class="tab"
        :class="{ active: activeTab === 'attachments' }"
        @click="activeTab = 'attachments'"
        v-if="hasAttachments"
      >
        附件 ({{ attachmentCount }})
      </button>
    </div>
    <div class="tab-content">
      <!-- Todo Display -->
      <div v-if="activeTab === 'todos'" class="todo-display">
        <div v-if="!todos.length" class="empty">暂无任务</div>
        <div v-else class="todo-list">
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
            <span class="todo-text">{{ todo.content }}</span>
          </div>
        </div>
      </div>

      <!-- Files Display -->
      <div v-if="activeTab === 'files'" class="files-display">
        <div v-if="!fileCount" class="empty">暂无文件</div>
        <div v-else class="file-list">
          <div
            v-for="(fileItem, index) in normalizedFiles"
            :key="fileItem.path || index"
            class="file-item"
            @click="showFileContent(fileItem.path, fileItem)"
          >
            <div class="file-info">
              <div class="file-icon-wrapper">
                <component
                  :is="getFileIcon(fileItem.path)"
                  :style="{ color: getFileIconColor(fileItem.path), fontSize: '18px' }"
                />
              </div>
              <div class="file-content-wrapper">
                <div class="file-name">{{ getFileName(fileItem) }}</div>
                <div class="file-meta">
                  <span class="file-time" v-if="fileItem.modified_at">
                    {{ formatDate(fileItem.modified_at) }}
                  </span>
                  <span class="file-size" v-if="fileItem.size">{{
                    formatFileSize(fileItem.size)
                  }}</span>
                </div>
              </div>
              <button class="download-btn" @click.stop="downloadFile(fileItem)" title="下载文件">
                <Download :size="18" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Attachments Display -->
      <div v-if="activeTab === 'attachments'" class="files-display">
        <div class="list-header" v-if="attachmentCount">
          <div class="list-header-left">
            <span class="count">{{ attachmentCount }} 个附件</span>
            <a-tooltip title="支持 txt/md/docx/html 格式 ≤ 5 MB">
              <Info :size="14" class="info-icon" />
            </a-tooltip>
          </div>
          <button class="add-btn" @click="triggerUpload" :disabled="isUploading">
            <Plus :size="16" />
            <span>添加</span>
          </button>
        </div>
        <div v-if="!attachmentCount" class="empty">
          <p>暂无附件</p>
          <a-button type="primary" @click="triggerUpload" :loading="isUploading">上传附件</a-button>
        </div>
        <div v-else class="file-list">
          <div
            v-for="(fileItem, index) in normalizedAttachments"
            :key="fileItem.path || index"
            class="file-item"
            @click="showFileContent(fileItem.path, fileItem)"
          >
            <div class="file-info">
              <div class="file-icon-wrapper">
                <component
                  :is="getFileIcon(fileItem.path)"
                  :style="{ color: getFileIconColor(fileItem.path), fontSize: '18px' }"
                />
              </div>
              <div class="file-content-wrapper">
                <div class="file-name">{{ getFileName(fileItem) }}</div>
                <div class="file-meta">
                  <span class="file-time" v-if="fileItem.modified_at">
                    {{ formatDate(fileItem.modified_at) }}
                  </span>
                  <span class="file-size" v-if="fileItem.size">{{
                    formatFileSize(fileItem.size)
                  }}</span>
                </div>
              </div>
              <button class="download-btn" @click.stop="downloadFile(fileItem)" title="下载附件">
                <Download :size="18" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Hidden File Input -->
    <input
      type="file"
      ref="fileInputRef"
      style="display: none"
      multiple
      @change="handleFileChange"
    />

    <!-- 文件内容 Modal -->
    <a-modal
      v-model:open="modalVisible"
      width="80%"
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
      <div class="file-content">
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
import { computed, ref, watch } from 'vue'
import { Download, X, Plus, Info } from 'lucide-vue-next'
import {
  CheckCircleOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  DownloadOutlined
} from '@ant-design/icons-vue'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { useThemeStore } from '@/stores/theme'
import { getFileIcon, getFileIconColor, formatFileSize } from '@/utils/file_utils'
import { threadApi } from '@/apis'
import { message } from 'ant-design-vue'

const props = defineProps({
  agentState: {
    type: Object,
    default: () => ({})
  },
  threadId: {
    type: String,
    default: null
  }
})

const emit = defineEmits(['refresh', 'close'])

const activeTab = ref('todos')
const modalVisible = ref(false)
const currentFile = ref(null)
const currentFilePath = ref('')
const isUploading = ref(false)
const fileInputRef = ref(null)

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

const attachments = computed(() => {
  return props.agentState?.attachments || []
})

const hasTodos = computed(() => {
  return todos.value.length > 0
})

const hasFiles = computed(() => {
  return files.value.length > 0
})

const hasAttachments = computed(() => {
  return attachments.value.length > 0
})

const todoCount = computed(() => {
  return todos.value.length
})

// 适配实际数据格式
const normalizedFiles = computed(() => {
  if (!Array.isArray(files.value)) return []

  const result = []
  files.value.forEach((item) => {
    if (typeof item === 'object' && item !== null) {
      Object.entries(item).forEach(([filePath, fileData]) => {
        result.push({
          path: filePath,
          ...fileData
        })
      })
    }
  })

  return result
})

const normalizedAttachments = computed(() => {
  if (!Array.isArray(attachments.value)) return []
  return attachments.value.map((item) => ({
    ...item,
    path: item.file_name,
    content: item.markdown,
    modified_at: item.uploaded_at,
    size: item.file_size
  }))
})

const fileCount = computed(() => {
  return normalizedFiles.value.length
})

const attachmentCount = computed(() => {
  return normalizedAttachments.value.length
})

// 监听 agentState 变化，自动选择有内容的标签
watch(
  () => props.agentState,
  (newState) => {
    if (newState) {
      if (hasAttachments.value && !hasFiles.value && !hasTodos.value) {
        activeTab.value = 'attachments'
      } else if (hasFiles.value && !hasTodos.value) {
        activeTab.value = 'files'
      } else if (hasTodos.value) {
        activeTab.value = 'todos'
      }
    }
  },
  { immediate: true }
)

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

const triggerUpload = () => {
  if (fileInputRef.value) {
    fileInputRef.value.click()
  }
}

const handleFileChange = async (event) => {
  const files = event.target.files
  if (!files?.length || !props.threadId) return

  isUploading.value = true
  try {
    for (const file of Array.from(files)) {
      await threadApi.uploadThreadAttachment(props.threadId, file)
      message.success(`${file.name} 上传成功`)
    }
    emitRefresh()
  } catch (error) {
    console.error('上传附件失败:', error)
    message.error('上传附件失败')
  } finally {
    isUploading.value = false
    event.target.value = ''
  }
}

const emitRefresh = () => {
  emit('refresh')
}
</script>

<style scoped lang="less">
.agent-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--gray-0);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  height: 48px;
  border-bottom: 1px solid var(--gray-200);
  flex-shrink: 0;
}

.panel-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--gray-900);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.refresh-btn {
  color: var(--gray-700);
  font-size: 13px;
  height: 32px;
  display: flex;
  align-items: center;
  gap: 4px;
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
  border-bottom: 1px solid var(--gray-200);
  position: relative;
  align-items: center;
  padding: 0 16px;
  flex-shrink: 0;
}

.tab {
  padding: 12px 16px;
  border: none;
  background: none;
  color: var(--gray-600);
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.15s ease;
  position: relative;

  &:hover {
    color: var(--main-700);
  }

  &.active {
    color: var(--main-700);

    &::after {
      content: '';
      position: absolute;
      bottom: -1px;
      left: 0;
      right: 0;
      height: 2px;
      background: var(--main-500);
      border-radius: 1px;
    }
  }
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
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
  padding: 12px;
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
  font-size: 14px;
  line-height: 1.5;
  color: var(--gray-1000);
  word-break: break-word;

  .todo-item.completed & {
    color: var(--gray-500);
    text-decoration: line-through;
  }
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-item {
  padding: 10px 14px;
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;

  &:hover {
    background: var(--main-10);
    border-color: var(--main-300);
  }
}

.file-info {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.file-icon-wrapper {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.file-content-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.file-name {
  font-size: 14px;
  color: var(--gray-1000);
  font-weight: 500;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--gray-500);
  font-weight: 400;
}

.file-time {
  white-space: nowrap;
}

.file-size {
  color: var(--gray-400);
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

.download-btn {
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
  flex-shrink: 0;

  &:hover {
    color: var(--main-600);
    background: var(--main-20);
  }

  &:active {
    color: var(--main-400);
  }
}

.file-content {
  min-height: 300px;
  max-height: 60vh;
  overflow-y: auto;
  background: var(--main-5);
  border-radius: 6px;
  padding: 16px;
  border: 1px solid var(--gray-200);

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

  :deep(.md-editor-preview-wrapper) {
    padding: 0;
  }

  :deep(.md-editor-preview) {
    font-size: 14px;
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
</style>
