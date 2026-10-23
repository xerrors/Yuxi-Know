<template>
  <div class="knowledge-file-summary">
    <a-dropdown
      v-if="attention.total"
      v-model:open="attentionOpen"
      :trigger="['click']"
      placement="bottomRight"
    >
      <button
        type="button"
        :class="['summary-trigger', `attention-${attention.tone}`, { 'is-open': attentionOpen }]"
        :aria-label="`需关注文件状态，${attention.total} 个文件`"
        aria-haspopup="menu"
        :aria-expanded="attentionOpen"
        @keydown.esc.stop="openPanel = null"
      >
        <CircleAlert :size="16" aria-hidden="true" />
        <span class="attention-total">{{ number(attention.total) }}</span>
      </button>
      <template #overlay>
        <section class="file-summary-panel file-attention-panel" aria-label="需关注文件">
          <header class="summary-panel-heading">
            <strong>需关注</strong>
            <span>选择状态查看文件</span>
          </header>
          <a-menu class="file-attention-menu" @click="selectAttention">
            <a-menu-item v-for="item in attention.rows" :key="item.status">
              <span class="attention-row">
                <span :class="['attention-label', `attention-${item.tone}`]">
                  <span class="status-dot" aria-hidden="true" />{{ item.label }}
                </span>
                <span class="attention-row-end">
                  <span>{{ number(item.count) }}</span>
                  <ChevronRight :size="14" aria-hidden="true" />
                </span>
              </span>
            </a-menu-item>
            <template v-if="canManage && (pendingParse || pendingIndex)">
              <a-menu-divider />
              <a-menu-item v-if="pendingParse" key="batch:parse" :disabled="busy">
                <span class="batch-action"><FileText :size="14" aria-hidden="true" />批量解析</span>
              </a-menu-item>
              <a-menu-item v-if="pendingIndex" key="batch:index" :disabled="busy">
                <span class="batch-action"><Database :size="14" aria-hidden="true" />批量入库</span>
              </a-menu-item>
            </template>
          </a-menu>
        </section>
      </template>
    </a-dropdown>
    <a-dropdown v-model:open="statsOpen" :trigger="['click']" placement="bottomRight">
      <button
        type="button"
        ref="statsTrigger"
        :class="['summary-trigger', 'file-count-trigger', { 'is-open': statsOpen }]"
        aria-label="查看文件统计"
        aria-haspopup="dialog"
        :aria-expanded="statsOpen"
        @keydown.esc.stop="closeStatistics"
      >
        <FileText :size="16" aria-hidden="true" />
        <span
          ><b>{{ number(stats.file_count) }}</b> 个文件</span
        >
        <ChevronDown :size="12" class="summary-chevron" aria-hidden="true" />
      </button>
      <template #overlay>
        <section
          class="file-summary-panel file-statistics"
          role="dialog"
          aria-label="文件统计"
          :aria-busy="refreshing"
          @keydown.esc.stop="closeStatistics"
        >
          <header class="summary-panel-heading">
            <strong>文件统计</strong>
            <span v-if="refreshing" role="status">刷新中…</span>
          </header>
          <dl>
            <div>
              <dt>文件大小</dt>
              <dd>{{ sizeText }}</dd>
            </div>
            <div>
              <dt>Chunks</dt>
              <dd>{{ number(stats.chunk_count) }}</dd>
            </div>
            <div>
              <dt>Tokens</dt>
              <dd>{{ number(stats.token_count) }}</dd>
            </div>
          </dl>
          <p class="statistics-note">Token 按已入库的有效分块统计</p>
        </section>
      </template>
    </a-dropdown>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ChevronDown, ChevronRight, CircleAlert, Database, FileText } from '@lucide/vue'
import { fileAttention } from '../model/fileSummary'

const props = defineProps({
  stats: { type: Object, default: () => ({}) },
  canManage: Boolean,
  busy: Boolean,
  refreshing: Boolean
})
const emit = defineEmits(['filter', 'parse-pending', 'index-pending', 'refresh'])
const statsTrigger = ref(null)
const openPanel = ref(null)
/** 关闭统计并归还工具栏焦点。 */
function closeStatistics() {
  openPanel.value = null
  statsTrigger.value?.focus()
}
const attentionOpen = computed({
  get: () => openPanel.value === 'attention',
  set: (open) => {
    if (open) openPanel.value = 'attention'
    else if (openPanel.value === 'attention') openPanel.value = null
  }
})
const statsOpen = computed({
  get: () => openPanel.value === 'stats',
  set: (open) => {
    if (open && openPanel.value !== 'stats') {
      openPanel.value = 'stats'
      emit('refresh')
    } else if (!open && openPanel.value === 'stats') openPanel.value = null
  }
})
const attention = computed(() => fileAttention(props.stats))
const pendingParse = computed(() => Number(props.stats.pending_parse_count || 0))
const pendingIndex = computed(() => Number(props.stats.pending_index_count || 0))
const number = (value) => Number(value || 0).toLocaleString('zh-CN')
const sizeText = computed(() => {
  let size = Number(props.stats.total_size || 0)
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${Number(size.toFixed(2))} ${units[unit]}`
})
/** 状态只改变筛选；批量动作保留独立菜单项。 */
function selectAttention({ key }) {
  openPanel.value = null
  if (key === 'batch:parse') emit('parse-pending')
  else if (key === 'batch:index') emit('index-pending')
  else emit('filter', key)
}
</script>

<style scoped lang="less">
.knowledge-file-summary {
  display: flex;
  align-items: center;
  gap: 8px;
}
.summary-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: var(--gray-25);
  color: var(--color-text-secondary);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  transition:
    background 0.15s,
    border-color 0.15s;
  &:hover,
  &.is-open {
    background: var(--gray-100);
    border-color: var(--gray-150);
  }
  &:focus-visible {
    outline: 2px solid var(--main-color);
    outline-offset: 2px;
  }
}
.file-count-trigger {
  white-space: nowrap;
  b {
    color: var(--color-text);
    font-weight: 600;
  }
}
.summary-chevron {
  color: var(--color-text-tertiary);
}
.attention-total {
  font-weight: 600;
}
.attention-error {
  color: var(--color-error-700);
}
.attention-warning {
  color: var(--color-warning-900);
}
.attention-info {
  color: var(--color-info-700);
}
.summary-trigger.attention-error {
  background: var(--color-error-50);
  &:hover,
  &.is-open {
    border-color: var(--color-error-100);
  }
}
.summary-trigger.attention-warning {
  background: var(--color-warning-50);
  &:hover,
  &.is-open {
    border-color: var(--color-warning-100);
  }
}
.summary-trigger.attention-info {
  background: var(--color-info-50);
  &:hover,
  &.is-open {
    border-color: var(--color-info-100);
  }
}
.file-summary-panel {
  width: 248px;
  max-width: calc(100vw - 32px);
  padding: 8px 4px 4px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  background: var(--gray-0);
  box-shadow: var(--shadow-popover);
  .summary-panel-heading {
    padding: 4px 10px 10px;
  }
  :deep(.file-attention-menu) {
    box-shadow: none;
    background: transparent;
    padding: 0;
  }
}
.summary-panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 28px;
  strong {
    color: var(--color-text);
    font-size: 13px;
    font-weight: 600;
  }
  > span {
    color: var(--color-text-secondary);
    font-size: 12px;
  }
}
.attention-row,
.attention-label,
.attention-row-end,
.batch-action {
  display: flex;
  align-items: center;
  gap: 8px;
}
.attention-row {
  justify-content: space-between;
  padding: 3px 0;
  font-size: 13px;
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.attention-row-end {
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}
.batch-action {
  padding: 2px 0;
  color: inherit;
  font-size: 12px;
}
.file-statistics {
  color: var(--color-text);
  dl {
    margin: 0;
  }
  dl > div {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 24px;
    padding: 8px 10px;
  }
  dt {
    color: var(--color-text-secondary);
    font-size: 13px;
  }
  dd {
    margin: 0;
    font-size: 13px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }
}
.statistics-note {
  margin: 4px 10px;
  padding: 8px 0 4px;
  border-top: 1px solid var(--gray-100);
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-secondary);
}
@media (prefers-reduced-motion: reduce) {
  .summary-trigger {
    transition: none;
  }
}
</style>
