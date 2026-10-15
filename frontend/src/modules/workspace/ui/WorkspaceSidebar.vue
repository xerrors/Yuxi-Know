<template>
  <aside class="workspace-sidebar" aria-label="空间导航">
    <div class="sidebar-actions">
      <div ref="uploadActionMenuRef" class="file-action-dropdown">
        <button
          type="button"
          class="sidebar-action-btn"
          :disabled="disabled || uploading"
          :title="disabled ? '当前目录不支持上传文件' : '上传文件'"
          aria-haspopup="menu"
          :aria-expanded="uploadActionMenuOpen"
          @click="toggleUploadActionMenu"
        >
          <Loader2 v-if="uploading" class="action-spinner" :size="16" />
          <Upload v-else :size="16" />
          <span>{{ uploading ? '上传中...' : '上传文件' }}</span>
          <ChevronDown
            :size="14"
            class="file-action-chevron"
            :class="{ 'is-open': uploadActionMenuOpen }"
          />
        </button>
        <Transition name="file-action-menu">
          <div v-if="uploadActionMenuOpen" class="file-action-menu" role="menu">
            <button
              type="button"
              class="file-action-menu-item"
              role="menuitem"
              @click="onUploadAction"
            >
              <Upload :size="14" />
              <span>上传文件</span>
            </button>
            <button
              type="button"
              class="file-action-menu-item"
              role="menuitem"
              @click="onCreateFolderAction"
            >
              <FolderPlus :size="14" />
              <span>新建文件夹</span>
            </button>
          </div>
        </Transition>
      </div>
    </div>

    <section class="sidebar-section">
      <button
        type="button"
        class="workspace-nav-item"
        :class="{ active: activeKey === 'personal' && !isQuickAccessPath(currentPath) }"
        @click="$emit('select-personal')"
      >
        <FileTypeIcon is-dir folder-variant="personal" :size="16" />
        <span>全部文件</span>
      </button>
    </section>

    <section class="sidebar-section">
      <div class="section-title">快速访问</div>
      <button
        type="button"
        class="workspace-nav-item secondary"
        :class="{ active: activeKey === 'personal' && isSamePath(currentPath, agentsPath) }"
        @click="$emit('select-path', agentsPath)"
      >
        <FileTypeIcon is-dir :size="16" />
        <span>智能体文件</span>
      </button>
      <button
        type="button"
        class="workspace-nav-item secondary"
        :class="{
          active: activeKey === 'personal' && isSamePath(currentPath, savedArtifactsPath)
        }"
        @click="$emit('select-path', savedArtifactsPath)"
      >
        <FileTypeIcon is-dir :size="16" />
        <span>保存的产物</span>
      </button>
    </section>

    <section v-if="myKnowledgeBases.length" class="sidebar-section">
      <div class="section-title">我的知识库</div>
      <button
        v-for="knowledgeBase in myKnowledgeBases"
        :key="knowledgeBase.kb_id || knowledgeBase.id || knowledgeBase.name"
        type="button"
        class="workspace-nav-item secondary"
        :class="{ active: activeKey === `knowledge-base:${knowledgeBase.kb_id}` }"
        @click="$emit('select-knowledge-base', knowledgeBase)"
      >
        <FileTypeIcon is-dir :size="16" />
        <span :title="knowledgeBase.name">{{ knowledgeBase.name }}</span>
      </button>
    </section>

    <section v-if="sharedKnowledgeBases.length" class="sidebar-section">
      <div class="section-title">共享知识库</div>
      <button
        v-for="knowledgeBase in sharedKnowledgeBases"
        :key="knowledgeBase.kb_id || knowledgeBase.id || knowledgeBase.name"
        type="button"
        class="workspace-nav-item secondary"
        :class="{ active: activeKey === `knowledge-base:${knowledgeBase.kb_id}` }"
        @click="$emit('select-knowledge-base', knowledgeBase)"
      >
        <FileTypeIcon is-dir :size="16" />
        <span :title="knowledgeBase.name">{{ knowledgeBase.name }}</span>
      </button>
    </section>

    <section v-if="loadingKnowledgeBases" class="sidebar-section">
      <div class="sidebar-muted">正在加载知识库...</div>
    </section>
    <section v-else-if="!knowledgeBases.length" class="sidebar-section">
      <div class="sidebar-muted">暂无可访问知识库</div>
    </section>
  </aside>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ChevronDown, FolderPlus, Loader2, Upload } from '@lucide/vue'
import FileTypeIcon from '@/shared/ui/FileTypeIcon.vue'
import { useOutsidePointerdown } from '@/shared/lib/useOutsidePointerdown'

const savedArtifactsPath = '/saved_artifacts'
const agentsPath = '/agents/'
const quickAccessPaths = [savedArtifactsPath, agentsPath]

const normalizePath = (path) => String(path || '/').replace(/\/$/, '') || '/'
const isSameOrChildPath = (path, targetPath) => {
  const current = normalizePath(path)
  const target = normalizePath(targetPath)
  return current === target || current.startsWith(`${target}/`)
}
const isSamePath = (path, targetPath) => normalizePath(path) === normalizePath(targetPath)
const isQuickAccessPath = (path) =>
  quickAccessPaths.some((targetPath) => isSameOrChildPath(path, targetPath))

const props = defineProps({
  activeKey: { type: String, default: 'personal' },
  currentPath: { type: String, default: '/' },
  knowledgeBases: { type: Array, default: () => [] },
  loadingKnowledgeBases: { type: Boolean, default: false },
  currentUid: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  uploading: { type: Boolean, default: false }
})

const emit = defineEmits([
  'select-personal',
  'select-knowledge-base',
  'select-path',
  'upload-file',
  'create-directory'
])

const uploadActionMenuOpen = ref(false)
const uploadActionMenuRef = ref(null)

const toggleUploadActionMenu = () => {
  if (props.disabled || props.uploading) return
  uploadActionMenuOpen.value = !uploadActionMenuOpen.value
}

const onUploadAction = () => {
  uploadActionMenuOpen.value = false
  emit('upload-file')
}

const onCreateFolderAction = () => {
  uploadActionMenuOpen.value = false
  emit('create-directory')
}

useOutsidePointerdown(uploadActionMenuOpen, [uploadActionMenuRef])

const myKnowledgeBases = computed(() =>
  props.knowledgeBases.filter((kb) => kb.created_by === props.currentUid)
)

const sharedKnowledgeBases = computed(() =>
  props.knowledgeBases.filter((kb) => kb.created_by !== props.currentUid)
)
</script>

<style scoped lang="less">
.workspace-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  padding: 16px 12px;
  border-right: 1px solid var(--gray-100);
  background: var(--gray-10);
  overflow-y: auto;
}

.sidebar-actions {
  display: flex;
  flex-direction: column;
  padding-bottom: 2px;
}

.file-action-dropdown {
  position: relative;
  width: 100%;
}

.sidebar-action-btn {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border-radius: 6px;
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  color: var(--gray-800);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  outline: none;
  transition: all 0.16s ease;

  span {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &:hover:not(:disabled) {
    background: var(--gray-50);
    border-color: var(--gray-200);
    color: var(--gray-2000);
  }

  &:active:not(:disabled) {
    background: var(--gray-100);
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    box-shadow: none;
  }
}

.file-action-chevron {
  flex: 0 0 auto;
  margin-left: auto;
  transition: transform 0.15s ease;

  &.is-open {
    transform: rotate(180deg);
  }
}

.file-action-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 20;
  min-width: 130px;
  padding: 4px;
  background: var(--gray-0);
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.file-action-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--gray-700);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    color 0.15s ease;

  &:hover,
  &:focus-visible {
    background: var(--gray-50);
    color: var(--gray-900);
    outline: none;
  }
}

.file-action-menu-enter-active {
  transition:
    opacity 0.16s ease,
    transform 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}

.file-action-menu-leave-active {
  transition:
    opacity 0.12s ease,
    transform 0.16s ease;
}

.file-action-menu-enter-from,
.file-action-menu-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.96);
}

.action-spinner {
  animation: action-spin 1s linear infinite;
}

@keyframes action-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.sidebar-section {
  display: flex;
  flex-direction: column;
}

.section-title {
  padding: 0 10px 6px;
  color: var(--gray-500);
  font-size: 12px;
  font-weight: 600;
  line-height: 18px;
}

.workspace-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--gray-700);
  font-size: 13px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease;

  > span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &:hover:not(:disabled) {
    border-color: transparent;
    color: var(--gray-2000);
    background-color: var(--gray-50);
  }

  &.active {
    border-color: transparent;
    color: var(--gray-1000);
    background-color: var(--gray-100);
    font-weight: 600;
  }

  &.secondary {
    font-weight: 400;

    &.active {
      font-weight: 600;
    }
  }
}

.workspace-nav-item :deep(svg),
.workspace-nav-item :deep(.file-type-icon) {
  flex-shrink: 0;
}

.workspace-nav-item:focus-visible,
.sidebar-action-btn:focus-visible {
  outline: 2px solid var(--gray-700);
  outline-offset: 2px;
}

.sidebar-muted {
  padding: 4px 6px;
  color: var(--gray-500);
  font-size: 11.5px;
  line-height: 1.5;
}
</style>
