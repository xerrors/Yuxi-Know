<template>
  <FileBrowserTable
    class="workspace-file-list"
    :rows="entries"
    :columns="columns"
    row-key="path"
    :selected-key="selectedPath"
    :row-class-name="rowClassName"
    :loading="loading"
    :breadcrumbs="resolvedBreadcrumbItems"
    :root-label="rootLabel"
    :pagination="pagination"
    :selection="tableSelection"
    :scroll="{ x: 520 }"
    empty-text="当前文件夹为空"
    @open-row="(entry) => $emit('select-entry', entry)"
    @breadcrumb-click="handleBreadcrumbClick"
    @page-change="(payload) => $emit('page-change', payload)"
  >
    <template #toolbar-actions>
      <span class="entry-count">{{ entryCountText }}</span>
      <a-tooltip v-if="!readonly" title="多选">
        <a-button
          size="small"
          class="lucide-icon-btn"
          :type="effectiveSelectionMode ? 'primary' : 'default'"
          aria-label="多选"
          @click="toggleSelectionMode"
        >
          <ListChecks :size="14" />
        </a-button>
      </a-tooltip>
      <a-button
        v-if="effectiveSelectionMode"
        size="small"
        danger
        :disabled="!selectedPaths.length"
        :loading="deletingPaths.length > 0"
        @click="$emit('delete-selected')"
      >
        删除选中
      </a-button>
    </template>

    <template #name="{ row }">
      <span class="name-cell">
        <FileTypeIcon :name="row.name || row.path" :is-dir="row.is_dir" :size="17" />
        <span class="entry-name" :title="row.title || row.name">{{ row.title || row.name }}</span>
      </span>
    </template>

    <template #cell-size="{ row }">
      <span>{{ row.is_dir ? '-' : formatFileSize(row.size) }}</span>
    </template>

    <template #cell-modified_at="{ row }">
      <span>{{ formatRelativeTime(row.modified_at) }}</span>
    </template>

    <template #row-actions="{ row }">
      <a-dropdown v-if="!row.is_dir || (!readonly && !row.readonly)" :trigger="['click']">
        <button
          type="button"
          class="more-action"
          :disabled="isDeleting(row.path)"
          aria-label="更多操作"
          @click.stop
        >
          <MoreHorizontal :size="16" />
        </button>
        <template #overlay>
          <a-menu>
            <a-menu-item v-if="!row.is_dir" key="download" @click="$emit('download-entry', row)">
              <span class="menu-item-content">
                <Download :size="14" />
                <span>下载</span>
              </span>
            </a-menu-item>
            <a-menu-item
              v-if="!readonly && !row.readonly"
              key="delete"
              danger
              @click="$emit('delete-entry', row)"
            >
              <span class="menu-item-content">
                <Trash2 :size="14" />
                <span>删除</span>
              </span>
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </template>
  </FileBrowserTable>
</template>

<script setup>
import { computed } from 'vue'
import { Download, ListChecks, MoreHorizontal, Trash2 } from '@lucide/vue'
import FileBrowserTable from '@/shared/ui/FileBrowserTable.vue'
import FileTypeIcon from '@/shared/ui/FileTypeIcon.vue'
import { formatFileSize, formatRelativeTime } from '@/shared/lib/file_utils'

const props = defineProps({
  entries: { type: Array, default: () => [] },
  currentPath: { type: String, default: '/' },
  selectedPath: { type: String, default: '' },
  selectedPaths: { type: Array, default: () => [] },
  deletingPaths: { type: Array, default: () => [] },
  selectionMode: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  readonly: { type: Boolean, default: false },
  breadcrumbItems: { type: Array, default: null },
  rootLabel: { type: String, default: '全部文件' },
  pagination: { type: Object, default: null }
})

const emit = defineEmits([
  'select-entry',
  'select-path',
  'breadcrumb-click',
  'update:selectedPaths',
  'update:selectionMode',
  'delete-selected',
  'delete-entry',
  'download-entry',
  'page-change'
])

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '大小', dataIndex: 'size', key: 'size', width: 86 },
  { title: '修改时间', dataIndex: 'modified_at', key: 'modified_at', width: 126 },
  { title: '操作', key: 'action', dataIndex: 'path', width: 58, align: 'center' }
]

const deletingPathSet = computed(() => new Set(props.deletingPaths))
const entryPathSet = computed(() => new Set(props.entries.map((entry) => entry.path)))
const readonlyPathSet = computed(
  () => new Set(props.entries.filter((entry) => entry.readonly).map((entry) => entry.path))
)
const normalizedCurrentPath = computed(() => (props.currentPath || '/').replace(/\/+$/, '') || '/')
const effectiveSelectionMode = computed(() => !props.readonly && props.selectionMode)
const entryCountText = computed(() => {
  if (props.pagination?.total !== undefined) {
    return `${props.pagination.total} 项`
  }
  return `${props.entries.length} 项`
})

const resolvedBreadcrumbItems = computed(() => {
  if (props.breadcrumbItems?.length) return props.breadcrumbItems

  const normalizedPath = normalizedCurrentPath.value
  if (normalizedPath === '/') {
    return [{ name: props.rootLabel, path: '/' }]
  }

  const segments = normalizedPath.split('/').filter(Boolean)
  return segments.reduce(
    (items, segment) => {
      const parentPath = items[items.length - 1].path
      const path = parentPath === '/' ? `/${segment}` : `${parentPath}/${segment}`
      items.push({ name: segment, path })
      return items
    },
    [{ name: props.rootLabel, path: '/' }]
  )
})

const tableSelection = computed(() => {
  if (!effectiveSelectionMode.value) return null

  return {
    selectedRowKeys: props.selectedPaths,
    getCheckboxProps: (row) => ({ disabled: row.readonly || isDeleting(row.path) }),
    onChange: (keys) => {
      emit(
        'update:selectedPaths',
        keys.filter((path) => entryPathSet.value.has(path) && !readonlyPathSet.value.has(path))
      )
    }
  }
})

const isDeleting = (path) => deletingPathSet.value.has(path)

const rowClassName = (entry) => (isDeleting(entry.path) ? 'is-deleting' : '')

const toggleSelectionMode = () => {
  if (props.readonly) return
  const nextMode = !props.selectionMode
  emit('update:selectionMode', nextMode)
  if (!nextMode) {
    emit('update:selectedPaths', [])
  }
}

const handleBreadcrumbClick = ({ item, index }) => {
  emit('breadcrumb-click', { item, index })
  emit('select-path', item.path)
}
</script>

<style scoped lang="less">
.workspace-file-list {
  min-width: 0;
  min-height: 0;
}

.workspace-file-list :deep(.file-browser-header) {
  min-height: 48px;
  padding: 0 16px;
}

.workspace-file-list :deep(.ant-table-thead > tr > th) {
  padding: 9px 12px;
  background: var(--gray-10);
  color: var(--gray-600);
  font-weight: 500;
}

.workspace-file-list :deep(.ant-table-tbody > tr > td) {
  padding: 9px 12px;
  border-bottom-color: var(--gray-100);
  transition: background-color 150ms ease, color 150ms ease;
}

.workspace-file-list :deep(.ant-table-tbody > tr:not(.ant-table-placeholder):hover > td) {
  background: var(--gray-50);
  color: var(--gray-1000);
}

.workspace-file-list :deep(.ant-table-tbody > tr.file-browser-row-selected > td),
.workspace-file-list :deep(.ant-table-tbody > tr.ant-table-row-selected > td) {
  background: var(--gray-100);
  color: var(--gray-1000);
}

.workspace-file-list :deep(.file-browser-row-clickable:focus-visible) {
  outline: 2px solid var(--gray-600);
  outline-offset: -2px;
}

.workspace-file-list :deep(.file-browser-breadcrumb-item) {
  color: var(--gray-600);

  &:hover:not(:disabled),
  &.active {
    color: var(--gray-1000);
  }
}

.entry-count {
  flex: 0 0 auto;
  color: var(--gray-500);
  font-size: 12px;
}

.name-cell {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  min-width: 0;
  gap: 8px;
  vertical-align: middle;
}

.entry-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  color: var(--gray-400);
  cursor: pointer;
  transition: background-color 150ms ease, color 150ms ease;

  &:hover:not(:disabled) {
    background: var(--gray-150);
    color: var(--gray-1000);
  }

  &:disabled {
    color: var(--gray-300);
    cursor: not-allowed;
  }
}

.workspace-file-list :deep(tr:hover) .more-action,
.workspace-file-list :deep(tr:focus-within) .more-action {
  color: var(--gray-700);
}

.more-action:focus-visible {
  outline: 2px solid var(--gray-700);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .more-action,
  .workspace-file-list :deep(.ant-table-tbody > tr > td) {
    transition: none;
  }
}

.menu-item-content {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>
