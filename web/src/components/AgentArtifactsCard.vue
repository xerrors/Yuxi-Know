<template>
  <section v-if="normalizedArtifacts.length" class="artifacts-card" :class="{ expanded }">
    <button type="button" class="artifacts-toggle" @click="expanded = !expanded">
      <div class="artifacts-summary">
        <FolderOutput class="artifacts-icon" :size="16" />
        <span class="artifacts-title">交付物</span>
        <span class="artifacts-count">{{ artifactsCountLabel }}</span>
      </div>
      <div class="artifacts-action">
        <span class="artifacts-action-text">{{ expanded ? '收起' : '展开' }}</span>
        <ChevronDown class="artifacts-arrow" :size="16" />
      </div>
    </button>

    <div class="artifacts-panel" :class="{ expanded }">
      <div class="artifacts-panel-inner">
        <div class="output-list">
          <div v-for="file in normalizedArtifacts" :key="file.path" class="output-item">
            <div class="item-main" @click="openPreview(file)">
              <component
                :is="getFileIcon(file.path)"
                class="item-icon"
                :style="{ color: getFileIconColor(file.path) }"
              />
              <div class="item-meta">
                <div class="item-name">{{ file.name }}</div>
              </div>
            </div>
            <div class="item-actions">
              <button
                v-if="file.canPreview"
                class="item-action-btn"
                title="预览"
                @click.stop="openPreview(file)"
              >
                <Eye :size="15" />
              </button>
              <button class="item-action-btn" title="下载" @click.stop="downloadFile(file)">
                <Download :size="15" />
              </button>
              <button
                class="item-action-btn"
                :title="isSaving(file.path) ? '保存中' : '保存到工作区'"
                :disabled="isSaving(file.path)"
                @click.stop="saveToWorkspace(file)"
              >
                <LoaderCircle v-if="isSaving(file.path)" :size="15" class="item-action-spin" />
                <Save v-else :size="15" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <a-modal
      v-model:open="modalVisible"
      width="800px"
      :style="{ maxWidth: '90vw', top: '5vh' }"
      :bodyStyle="{ maxHeight: '90vh', overflow: 'auto' }"
      :footer="null"
      :closable="false"
      wrapClassName="agent-file-preview-modal"
      @cancel="closePreview"
    >
      <AgentFilePreview
        :file="currentFile"
        :filePath="currentFilePath"
        :showClose="true"
        :showDownload="true"
        :showFullscreen="true"
        @download="downloadFile"
        @close="closePreview"
      />
    </a-modal>
  </section>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ChevronDown, Download, Eye, FolderOutput, LoaderCircle, Save } from 'lucide-vue-next'
import { threadApi } from '@/apis/agent_api'
import AgentFilePreview from '@/components/AgentFilePreview.vue'
import { getFileIcon, getFileIconColor } from '@/utils/file_utils'
import { getPreviewTypeByPath } from '@/utils/file_preview'
import { downloadViewerFile, getViewerFileContent } from '@/apis/viewer_filesystem'

const props = defineProps({
  artifacts: {
    type: Array,
    default: () => []
  },
  threadId: {
    type: String,
    default: null
  },
  agentId: {
    type: String,
    default: null
  },
  agentConfigId: {
    type: [String, Number],
    default: null
  }
})
const emit = defineEmits(['saved'])

const normalizedArtifacts = computed(() =>
  (props.artifacts || [])
    .filter((path) => typeof path === 'string' && path.trim())
    .map((path) => {
      const normalizedPath = path.trim()
      return {
        path: normalizedPath,
        name: normalizedPath.split('/').pop() || normalizedPath,
        canPreview: ['text', 'markdown', 'pdf', 'image'].includes(
          getPreviewTypeByPath(normalizedPath)
        )
      }
    })
)
const artifactsCountLabel = computed(() => `${normalizedArtifacts.value.length} 个文件`)
const expanded = ref(false)

const modalVisible = ref(false)
const currentFile = ref(null)
const currentFilePath = ref('')
const savingState = ref({})

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
  return asciiMatch?.[1] || ''
}

const revokeCurrentPreviewUrl = () => {
  const previewUrl = currentFile.value?.previewUrl
  if (previewUrl) {
    window.URL.revokeObjectURL(previewUrl)
  }
}

const closePreview = () => {
  revokeCurrentPreviewUrl()
  modalVisible.value = false
  currentFile.value = null
  currentFilePath.value = ''
}

const openPreview = async (file) => {
  if (!props.threadId || !file?.path) return

  revokeCurrentPreviewUrl()
  currentFilePath.value = file.path
  currentFile.value = {
    ...file,
    content: 'Loading...',
    supported: true,
    previewType: 'text',
    message: '',
    previewUrl: ''
  }
  modalVisible.value = true

  try {
    const res = await getViewerFileContent(
      props.threadId,
      file.path,
      props.agentId,
      props.agentConfigId
    )
    const previewType = res?.preview_type || 'text'
    let previewUrl = ''

    if ((previewType === 'image' || previewType === 'pdf') && res?.supported) {
      const response = await downloadViewerFile(
        props.threadId,
        file.path,
        props.agentId,
        props.agentConfigId
      )
      const blob = await response.blob()
      previewUrl = window.URL.createObjectURL(blob)
    }

    currentFile.value = {
      ...file,
      content: res?.content ?? '',
      supported: res?.supported !== false,
      previewType,
      message: res?.message || '',
      previewUrl
    }
  } catch (error) {
    currentFile.value = {
      ...file,
      content: `Error loading file: ${error?.message || 'unknown error'}`,
      supported: false,
      previewType: 'unsupported',
      message: error?.message || '文件预览失败',
      previewUrl: ''
    }
  }
}

const downloadFile = async (file) => {
  if (!props.threadId || !file?.path) return

  const response = await downloadViewerFile(
    props.threadId,
    file.path,
    props.agentId,
    props.agentConfigId
  )
  const blob = await response.blob()
  const contentDisposition =
    response.headers.get('Content-Disposition') || response.headers.get('content-disposition')
  const filename = parseDownloadFilename(contentDisposition) || file.name
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

const isSaving = (path) => !!savingState.value[path]

const setSaving = (path, saving) => {
  savingState.value = {
    ...savingState.value,
    [path]: saving
  }
}

const saveToWorkspace = async (file) => {
  if (!props.threadId || !file?.path || isSaving(file.path)) return

  setSaving(file.path, true)
  try {
    const result = await threadApi.saveThreadArtifactToWorkspace(props.threadId, file.path)
    message.success(`已保存到工作区：${result.saved_path}`)
    emit('saved', result)
  } catch (error) {
    message.error(error?.message || '保存到工作区失败')
  } finally {
    setSaving(file.path, false)
  }
}

onUnmounted(() => {
  revokeCurrentPreviewUrl()
})

watch(
  () => [props.threadId, normalizedArtifacts.value.map((file) => file.path).join('|')],
  () => {
    expanded.value = false
  }
)
</script>

<style scoped lang="less">
.artifacts-card {
  width: 90%;
  max-width: 800px;
  margin: 0 auto;
  border-radius: 12px 12px 0 0;
  overflow: hidden;
  border: 1px solid var(--gray-100);
  background: linear-gradient(180deg, var(--gray-25) 0%, var(--gray-0) 100%);
  border-bottom: none;
  position: relative;
  z-index: 1;

  &.expanded {
    .artifacts-toggle {
      border-bottom-color: var(--gray-150);
    }
  }
}

.artifacts-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 12px;
  border: none;
  border-bottom: 1px solid transparent;
  background: linear-gradient(180deg, var(--gray-25) 0%, var(--gray-50) 100%);
  color: var(--gray-900);
  cursor: pointer;
  text-align: left;
  transition: background 0.2s ease;
}

.artifacts-summary,
.artifacts-action {
  display: flex;
  align-items: center;
}

.artifacts-summary {
  min-width: 0;
  gap: 8px;
}

.artifacts-icon {
  flex-shrink: 0;
  color: var(--gray-600);
  opacity: 0.92;
}

.artifacts-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--gray-900);
  line-height: 1;
}

.artifacts-count {
  font-size: 12px;
  color: var(--gray-500);
  white-space: nowrap;
}

.artifacts-action {
  gap: 6px;
  flex-shrink: 0;
}

.artifacts-action-text {
  font-size: 12px;
  font-weight: 600;
  color: var(--gray-600);
}

.artifacts-arrow {
  flex-shrink: 0;
  color: var(--gray-600);
  transition: transform 0.24s ease;
}

.artifacts-card.expanded .artifacts-arrow {
  transform: rotate(180deg);
}

.artifacts-panel {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.28s ease;
  background: transparent;

  &.expanded {
    max-height: 240px;
  }
}

.artifacts-panel-inner {
  padding: 4px 6px 6px;
  background: var(--gray-0);
}

.output-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.output-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  border-radius: 0;
  background: transparent;
  border-bottom: 1px solid var(--gray-150);
  transition: background 0.18s ease;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: var(--gray-25);
  }
}

@media (max-width: 768px) {
  .artifacts-card {
    width: 100%;
  }

  .artifacts-toggle {
    padding: 11px 12px;
  }

  .artifacts-panel-inner {
    padding: 8px;
  }

  .artifacts-title {
    font-size: 14px;
  }

  .artifacts-count,
  .artifacts-action-text {
    font-size: 12px;
  }
}

.item-main {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.item-icon {
  flex-shrink: 0;
  font-size: 16px;
  opacity: 0.82;
}

.item-meta {
  min-width: 0;
}

.item-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--gray-900);
  word-break: break-word;
  line-height: 1.3;
}

.item-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: 8px;
}

.item-action-btn {
  width: 30px;
  height: 30px;
  border: none;
  background: transparent;
  color: var(--gray-600);
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.item-action-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.item-action-btn:hover {
  color: var(--main-700);
  background: var(--gray-100);
}

.item-action-spin {
  animation: artifacts-spin 1s linear infinite;
}

@keyframes artifacts-spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 768px) {
  .output-item {
    align-items: flex-start;
    flex-direction: column;
  }

  .item-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
