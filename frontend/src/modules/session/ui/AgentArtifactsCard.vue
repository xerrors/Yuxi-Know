<template>
  <section
    v-if="normalizedArtifacts.length"
    class="artifacts-list"
    :class="{ 'is-box-group': normalizedArtifacts.length > 3 }"
    aria-label="交付物"
  >
    <div v-if="normalizedArtifacts.length > 3" class="artifacts-heading">
      <span>交付物 <span class="artifact-count">{{ normalizedArtifacts.length }}</span></span>
      <button
        type="button"
        class="lucide-icon-btn artifacts-toggle"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? '收起' : `展开其余 ${normalizedArtifacts.length - 3} 个` }}
        <ChevronDown :size="14" :class="{ 'is-expanded': expanded }" aria-hidden="true" />
      </button>
    </div>
    <TransitionGroup name="artifact-reveal" tag="div" class="artifact-items">
      <div v-for="file in visibleArtifacts" :key="file.path" class="artifact-entry">
        <div class="artifact-card">
          <button
            type="button"
            class="item-main"
            :title="`打开 ${file.name}`"
            @click="openPreview(file)"
          >
            <FileTypeIcon :name="file.path" :size="20" class="item-icon" />
            <div class="item-meta">
              <div class="item-name">{{ file.name }}</div>
              <div class="item-desc">{{ getFileMetaLabel(file.path) }}</div>
            </div>
          </button>
          <div class="item-actions">
            <button class="item-action-btn" title="下载" aria-label="下载" @click.stop="downloadFile(file)">
              <Download :size="15" />
            </button>
            <button
              class="item-action-btn"
              :title="isSaving(file.path) ? '保存中' : '保存到个人空间'"
              aria-label="保存到个人空间"
              :disabled="isSaving(file.path)"
              @click.stop="saveToWorkspace(file)"
            >
              <LoaderCircle v-if="isSaving(file.path)" :size="15" class="item-action-spin" />
              <Save v-else :size="15" />
            </button>
          </div>
        </div>
      </div>
    </TransitionGroup>
  </section>

  <a-modal
    :open="saveDialogOpen"
    title="保存交付物"
    ok-text="保存"
    cancel-text="取消"
    :ok-button-props="{ disabled: !selectedDestination || pickerLoading }"
    :confirm-loading="pendingSaveFile ? isSaving(pendingSaveFile.path) : false"
    @ok="confirmSave"
    @cancel="closeSaveDialog"
  >
    <p class="save-dialog-hint">选择保存到个人工作区的目录</p>
    <WorkspacePathPicker
      v-model="selectedDestination"
      selection-mode="directory"
      :active="saveDialogOpen"
      :disabled="pendingSaveFile ? isSaving(pendingSaveFile.path) : false"
      @loading-change="pickerLoading = $event"
    />
  </a-modal>
</template>

<script setup>
import { computed, ref } from 'vue'
import { normalizeArtifacts } from '@/modules/session/model/artifacts'
import { message } from 'ant-design-vue'
import { ChevronDown, Download, LoaderCircle, Save } from '@lucide/vue'
import { threadApi } from '@/apis/agent_api'
import FileTypeIcon from '@/shared/ui/FileTypeIcon.vue'
import WorkspacePathPicker from '@/modules/workspace/ui/WorkspacePathPicker.vue'
import { parseDownloadFilename } from '@/shared/lib/file_utils'

const props = defineProps({
  artifacts: {
    type: Array,
    default: () => []
  },
  threadId: {
    type: String,
    default: null
  }
})
const emit = defineEmits(['saved', 'open-preview'])

const normalizedArtifacts = computed(() =>
  normalizeArtifacts(props.artifacts)
    .reverse()
    .map((path) => ({ path, name: path.split('/').pop() || path }))
)
const expanded = ref(false)
const visibleArtifacts = computed(() =>
  expanded.value ? normalizedArtifacts.value : normalizedArtifacts.value.slice(0, 3)
)
const savingState = ref({})
const saveDialogOpen = ref(false)
const pendingSaveFile = ref(null)
const selectedDestination = ref('/saved_artifacts')
const pickerLoading = ref(false)

const getFileMetaLabel = (path) => {
  const filename =
    String(path || '')
      .split('/')
      .pop() || ''
  if (!filename.includes('.')) return '交付文件'

  const extension = filename.split('.').pop()
  return extension ? `交付文件 · ${extension.toUpperCase()}` : '交付文件'
}

const openPreview = (file) => {
  emit('open-preview', { ...file })
}

const downloadFile = async (file) => {
  if (!props.threadId || !file?.path) return

  try {
    const response = await threadApi.downloadThreadArtifact(props.threadId, file.path)
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
  } catch (error) {
    message.error(error?.message || '下载文件失败')
  }
}

const isSaving = (path) => !!savingState.value[path]

const setSaving = (path, saving) => {
  savingState.value = {
    ...savingState.value,
    [path]: saving
  }
}

const saveToWorkspace = (file) => {
  if (!props.threadId || !file?.path || isSaving(file.path)) {
    return
  }
  pendingSaveFile.value = file
  selectedDestination.value = '/saved_artifacts'
  saveDialogOpen.value = true
}

const closeSaveDialog = () => {
  if (pendingSaveFile.value && isSaving(pendingSaveFile.value.path)) return
  saveDialogOpen.value = false
  pendingSaveFile.value = null
}

const confirmSave = async () => {
  const file = pendingSaveFile.value
  if (!props.threadId || !file?.path || !selectedDestination.value || isSaving(file.path)) return

  setSaving(file.path, true)
  try {
    const result = await threadApi.saveThreadArtifactToWorkspace(
      props.threadId,
      file.path,
      selectedDestination.value
    )
    message.success(`已保存到个人空间：${result.saved_path}`)
    emit('saved', result)
    saveDialogOpen.value = false
    pendingSaveFile.value = null
  } catch (error) {
    message.error(error?.message || '保存到个人空间失败')
  } finally {
    setSaving(file.path, false)
  }
}
</script>

<style scoped lang="less">
.save-dialog-hint {
  margin-bottom: 12px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.artifacts-list {
  width: 100%;
  margin: 8px 0 4px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.artifacts-list.is-box-group {
  gap: 0;
  border: 1px solid var(--gray-150);
  border-radius: 10px;
  overflow: hidden;
  background: var(--gray-25);

  .artifact-items {
    gap: 0;
  }

  .artifact-card {
    border: 0;
    border-top: 1px solid var(--gray-100);
    border-radius: 0;
    background: transparent;

    &:hover {
      background: var(--gray-50);
    }
  }
}

.artifact-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.artifact-entry {
  display: grid;
  grid-template-rows: 1fr;

  .artifact-card {
    min-height: 0;
    overflow: hidden;
  }
}

.artifact-reveal-enter-active,
.artifact-reveal-leave-active {
  transition: grid-template-rows 0.24s ease, opacity 0.2s ease;
}

.artifact-reveal-enter-from,
.artifact-reveal-leave-to {
  grid-template-rows: 0fr;
  opacity: 0;
}

.artifacts-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  color: var(--color-text);
  font-size: 13px;
  font-weight: 500;
}

.artifact-count {
  margin-left: 4px;
  color: var(--color-text-secondary);
  font-weight: 400;
}

.artifacts-toggle {
  gap: 4px;
  padding: 4px 6px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;

  &:hover {
    background: var(--gray-100);
    color: var(--color-text);
  }

  svg {
    transition: transform 0.24s ease;
  }

  .is-expanded {
    transform: rotate(180deg);
  }
}

.artifacts-toggle:focus-visible {
  outline: 2px solid var(--main-color);
  outline-offset: 2px;
}

.artifact-card {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  border: 1px solid var(--gray-150);
  border-radius: 12px;
  background: linear-gradient(180deg, var(--gray-25) 0%, var(--gray-0) 100%);
  transition:
    background 0.18s ease,
    border-color 0.18s ease;

  &:hover {
    border-color: var(--gray-300);
    background: var(--gray-0);
  }
}

.item-main {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  border: none;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  padding: 10px 8px 10px 12px;
}

.item-icon {
  flex-shrink: 0;
  font-size: 18px;
  opacity: 0.86;
}

.item-meta {
  min-width: 0;
  flex: 1;
}

.item-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--gray-900);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
}

.item-desc {
  margin-top: 2px;
  font-size: 12px;
  color: var(--gray-500);
  line-height: 1.2;
}

.item-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-right: 8px;
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

.item-action-btn:hover:not(:disabled) {
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
  .artifacts-list {
    margin-top: 6px;
  }

  .artifact-card {
    align-items: stretch;
  }

  .item-main {
    padding: 9px 6px 9px 12px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .artifact-reveal-enter-active,
  .artifact-reveal-leave-active,
  .artifacts-toggle svg {
    transition: none;
  }
}
</style>
