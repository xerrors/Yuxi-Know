<template>
  <section class="workspace-file-list">
    <div class="file-list-header">
      <div class="path-line">
        <a-breadcrumb class="path-breadcrumb">
          <a-breadcrumb-item v-for="item in breadcrumbItems" :key="item.path">
            <button
              type="button"
              class="breadcrumb-action"
              :class="{ current: item.path === currentPath }"
              :disabled="item.path === currentPath"
              :title="item.path"
              @click="$emit('select-path', item.path)"
            >
              {{ item.name }}
            </button>
          </a-breadcrumb-item>
        </a-breadcrumb>
      </div>
      <div class="list-actions">
        <span class="entry-count">{{ entries.length }} 项</span>
        <a-tooltip title="多选">
          <a-button
            size="small"
            class="lucide-icon-btn"
            :type="selectionMode ? 'primary' : 'default'"
            aria-label="多选"
            @click="toggleSelectionMode"
          >
            <ListChecks :size="14" />
          </a-button>
        </a-tooltip>
        <a-button
          v-if="selectionMode"
          size="small"
          danger
          :disabled="!selectedPaths.length"
          :loading="deletingPaths.length > 0"
          @click="$emit('delete-selected')"
        >
          删除选中
        </a-button>
      </div>
    </div>

    <div class="file-table" role="table" aria-label="工作区文件列表">
      <div class="file-row table-head" :class="{ 'selection-enabled': selectionMode }" role="row">
        <span v-if="selectionMode" class="selection-cell">
          <a-checkbox
            :checked="allSelected"
            :indeterminate="partiallySelected"
            :disabled="!entries.length"
            aria-label="全选当前目录文件"
            @change="toggleAllSelection"
          />
        </span>
        <span>名称</span>
        <span>大小</span>
        <span>修改时间</span>
        <span class="action-head">操作</span>
      </div>
      <div
        v-for="entry in entries"
        :key="entry.path"
        class="file-row"
        :class="{
          selected: selectedPath === entry.path,
          deleting: isDeleting(entry.path),
          'selection-enabled': selectionMode
        }"
        role="row"
        tabindex="0"
        @click="$emit('select-entry', entry)"
        @keydown.enter="$emit('select-entry', entry)"
      >
        <span v-if="selectionMode" class="selection-cell" @click.stop>
          <a-checkbox
            :checked="selectedPathSet.has(entry.path)"
            :disabled="isDeleting(entry.path)"
            :aria-label="`选择 ${entry.name}`"
            @change="(event) => toggleEntrySelection(entry.path, event.target.checked)"
          />
        </span>
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
        <span class="action-cell" @click.stop>
          <a-dropdown :trigger="['click']">
            <button
              type="button"
              class="more-action"
              :disabled="isDeleting(entry.path)"
              aria-label="更多操作"
              @click.stop
            >
              <MoreHorizontal :size="16" />
            </button>
            <template #overlay>
              <a-menu>
                <a-menu-item v-if="!entry.is_dir" key="download" @click="$emit('download-entry', entry)">
                  <span class="menu-item-content">
                    <Download :size="14" />
                    <span>下载</span>
                  </span>
                </a-menu-item>
                <a-menu-item key="delete" danger @click="$emit('delete-entry', entry)">
                  <span class="menu-item-content">
                    <Trash2 :size="14" />
                    <span>删除</span>
                  </span>
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </span>
      </div>
    </div>

    <div v-if="loading" class="list-state">
      <a-spin />
      <span>正在加载文件...</span>
    </div>
    <a-empty v-else-if="!entries.length" class="list-empty" description="当前文件夹为空" />
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Download, Folder, ListChecks, MoreHorizontal, Trash2 } from 'lucide-vue-next'
import { formatFileSize, formatRelativeTime, getFileIcon, getFileIconColor } from '@/utils/file_utils'

const props = defineProps({
  entries: { type: Array, default: () => [] },
  currentPath: { type: String, default: '/' },
  selectedPath: { type: String, default: '' },
  selectedPaths: { type: Array, default: () => [] },
  deletingPaths: { type: Array, default: () => [] },
  selectionMode: { type: Boolean, default: false },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits([
  'select-entry',
  'select-path',
  'update:selectedPaths',
  'update:selectionMode',
  'delete-selected',
  'delete-entry',
  'download-entry'
])

const selectedPathSet = computed(() => new Set(props.selectedPaths))
const deletingPathSet = computed(() => new Set(props.deletingPaths))
const entryPaths = computed(() => props.entries.map((entry) => entry.path))
const breadcrumbItems = computed(() => {
  const normalizedPath = props.currentPath || '/'
  if (normalizedPath === '/') {
    return [{ name: '工作区', path: '/' }]
  }

  const segments = normalizedPath.split('/').filter(Boolean)
  return segments.reduce(
    (items, segment) => {
      const parentPath = items[items.length - 1].path
      const path = parentPath === '/' ? `/${segment}` : `${parentPath}/${segment}`
      items.push({ name: segment, path })
      return items
    },
    [{ name: '工作区', path: '/' }]
  )
})

const allSelected = computed(() => {
  return entryPaths.value.length > 0 && entryPaths.value.every((path) => selectedPathSet.value.has(path))
})

const partiallySelected = computed(() => {
  return !allSelected.value && entryPaths.value.some((path) => selectedPathSet.value.has(path))
})

const isDeleting = (path) => deletingPathSet.value.has(path)

const toggleSelectionMode = () => {
  const nextMode = !props.selectionMode
  emit('update:selectionMode', nextMode)
  if (!nextMode) {
    emit('update:selectedPaths', [])
  }
}

const toggleAllSelection = (event) => {
  emit('update:selectedPaths', event.target.checked ? [...entryPaths.value] : [])
}

const toggleEntrySelection = (path, checked) => {
  const nextSelectedPaths = new Set(props.selectedPaths)
  if (checked) {
    nextSelectedPaths.add(path)
  } else {
    nextSelectedPaths.delete(path)
  }
  emit('update:selectedPaths', [...nextSelectedPaths].filter((selectedPath) => entryPaths.value.includes(selectedPath)))
}
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

.path-line,
.list-actions {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.list-actions {
  flex: 0 0 auto;
}

.path-breadcrumb {
  min-width: 0;
  overflow: hidden;
  font-size: 14px;
}

.breadcrumb-action {
  max-width: 180px;
  padding: 0;
  overflow: hidden;
  border: 0;
  background: transparent;
  color: var(--main-800);
  cursor: pointer;
  font: inherit;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 400;

  &:hover:not(:disabled) {
    color: var(--main-600);
  }

  &.current,
  &:disabled {
    color: var(--gray-900);
    cursor: default;
  }
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
  grid-template-columns: minmax(150px, 1fr) 76px 118px 34px;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 38px;
  padding: 0 14px;
  border: 0;
  border-bottom: 1px solid var(--gray-50);
  background: transparent;
  color: var(--gray-700);
  font-size: 13px;
  text-align: left;

  &.selection-enabled {
    grid-template-columns: 34px minmax(150px, 1fr) 76px 118px 34px;
  }

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

  &.deleting {
    opacity: 0.62;
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

.selection-cell,
.action-cell {
  display: inline-flex;
  align-items: center;
}

.action-head,
.action-cell {
  justify-content: center;
}

.more-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--gray-500);
  cursor: pointer;

  &:hover:not(:disabled) {
    background: var(--gray-100);
    color: var(--gray-900);
  }

  &:disabled {
    color: var(--gray-300);
    cursor: not-allowed;
  }
}

.menu-item-content {
  display: inline-flex;
  align-items: center;
  gap: 4px;
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
