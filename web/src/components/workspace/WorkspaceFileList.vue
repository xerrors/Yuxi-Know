<template>
  <section class="workspace-file-list">
    <div class="file-list-header">
      <div class="path-line">
        <button
          type="button"
          class="path-action"
          :disabled="currentPath === '/'"
          aria-label="返回上级目录"
          @click="$emit('go-parent')"
        >
          <ChevronLeft :size="16" />
        </button>
        <span class="path-text" :title="currentPath">{{ currentPath }}</span>
      </div>
      <span class="entry-count">{{ entries.length }} 项</span>
    </div>

    <div class="file-table" role="table" aria-label="工作区文件列表">
      <div class="file-row table-head" role="row">
        <span>名称</span>
        <span>大小</span>
        <span>修改时间</span>
      </div>
      <button
        v-for="entry in entries"
        :key="entry.path"
        type="button"
        class="file-row"
        :class="{ selected: selectedPath === entry.path }"
        role="row"
        @click="$emit('select-entry', entry)"
      >
        <span class="name-cell">
          <Folder v-if="entry.is_dir" :size="17" class="folder-icon" />
          <component
            v-else
            :is="getFileIcon(entry.path)"
            :style="{ color: getFileIconColor(entry.path), fontSize: '16px' }"
          />
          <span class="entry-name" :title="entry.name">{{ entry.name }}</span>
        </span>
        <span>{{ entry.is_dir ? '-' : formatFileSize(entry.size) }}</span>
        <span>{{ formatRelativeTime(entry.modified_at) }}</span>
      </button>
    </div>

    <div v-if="loading" class="list-state">
      <a-spin />
      <span>正在加载文件...</span>
    </div>
    <a-empty v-else-if="!entries.length" class="list-empty" description="当前文件夹为空" />
  </section>
</template>

<script setup>
import { ChevronLeft, Folder } from 'lucide-vue-next'
import { formatFileSize, formatRelativeTime, getFileIcon, getFileIconColor } from '@/utils/file_utils'

defineProps({
  entries: { type: Array, default: () => [] },
  currentPath: { type: String, default: '/' },
  selectedPath: { type: String, default: '' },
  loading: { type: Boolean, default: false }
})

defineEmits(['select-entry', 'go-parent'])
</script>

<style scoped lang="less">
.workspace-file-list {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: var(--gray-0);
}

.file-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 44px;
  padding: 0 14px;
  border-bottom: 1px solid var(--gray-100);
}

.path-line {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.path-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  background: var(--gray-0);
  color: var(--gray-600);
  cursor: pointer;

  &:disabled {
    color: var(--gray-300);
    cursor: not-allowed;
  }

  &:hover:not(:disabled) {
    background: var(--main-20);
    color: var(--main-color);
  }
}

.path-text {
  min-width: 0;
  overflow: hidden;
  color: var(--gray-900);
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entry-count {
  flex: 0 0 auto;
  color: var(--gray-500);
  font-size: 12px;
}

.file-table {
  min-height: 0;
  overflow-y: auto;
}

.file-row {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) 86px 130px;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 38px;
  padding: 0 14px;
  border: 0;
  border-bottom: 1px solid var(--gray-50);
  background: transparent;
  color: var(--gray-700);
  font-size: 13px;
  text-align: left;

  &:not(.table-head) {
    cursor: pointer;
  }

  &:hover:not(.table-head),
  &.selected {
    background: var(--main-20);
    color: var(--gray-1000);
  }

  &.selected {
    box-shadow: inset 3px 0 0 var(--main-color);
  }
}

.table-head {
  position: sticky;
  top: 0;
  z-index: 1;
  min-height: 34px;
  background: var(--gray-25);
  color: var(--gray-500);
  font-size: 12px;
  font-weight: 600;
}

.name-cell {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.folder-icon {
  color: var(--main-500);
  fill: var(--main-500);
  fill-opacity: 0.16;
}

.entry-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.list-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 180px;
  color: var(--gray-500);
}

.list-empty {
  margin-top: 48px;
}
</style>
