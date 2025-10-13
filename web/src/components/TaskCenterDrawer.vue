<template>
  <a-drawer
    :open="isOpen"
    :width="620"
    title="任务中心"
    placement="right"
    @close="handleClose"
  >
    <div class="task-center">
      <div class="task-toolbar">
        <div class="task-filter-group">
          <a-button-group>
            <a-button
              :type="isActiveFilter('all') ? 'primary' : 'default'"
              @click="setFilter('all')"
            >
              全部
              <span class="filter-count">{{ totalCount }}</span>
            </a-button>
            <a-button
              :type="isActiveFilter('active') ? 'primary' : 'default'"
              @click="setFilter('active')"
            >
              进行中
              <span class="filter-count">{{ inProgressCount }}</span>
            </a-button>
            <a-button
              :type="isActiveFilter('success') ? 'primary' : 'default'"
              @click="setFilter('success')"
            >
              已完成
              <span class="filter-count">{{ completedCount }}</span>
            </a-button>
            <a-button
              :type="isActiveFilter('failed') ? 'primary' : 'default'"
              @click="setFilter('failed')"
            >
              失败
              <span class="filter-count">{{ failedCount }}</span>
            </a-button>
          </a-button-group>
        </div>
        <div class="task-toolbar-actions">
          <a-button
            type="text"
            @click="handleRefresh"
            :loading="loadingState"
          >
            刷新
          </a-button>
        </div>
      </div>

      <a-alert
        v-if="lastErrorState"
        type="error"
        show-icon
        class="task-alert"
        :message="lastErrorState.message || '加载任务信息失败'"
      />

      <div v-if="hasTasks" class="task-list">
        <div
          v-for="task in filteredTasks"
          :key="task.id"
          class="task-card"
          :class="taskCardClasses(task)"
        >
          <div class="task-card-header">
            <div class="task-card-info">
              <div class="task-card-title">{{ task.name }}</div>
              <div class="task-card-subtitle">
                <span class="task-card-id">#{{ formatTaskId(task.id) }}</span>
                <span class="task-card-type">{{ taskTypeLabel(task.type) }}</span>
                <span class="task-card-id" v-if="getTaskDuration(task)">{{ getTaskDuration(task) }}</span>
              </div>
            </div>
            <a-tag :color="statusColor(task.status)" class="task-card-status">
              {{ statusLabel(task.status) }}

            </a-tag>
          </div>

          <div v-if="!isTaskCompleted(task)" class="task-card-progress">
            <a-progress
              :percent="Math.round(task.progress || 0)"
              :status="progressStatus(task.status)"
              stroke-width="6"
              />
            <span class="task-card-progress-value">{{ Math.round(task.progress || 0) }}%</span>
          </div>

          <div v-if="task.message && !isTaskCompleted(task)" class="task-card-message">
            {{ task.message }}
          </div>
          <div v-if="task.error" class="task-card-error">
            {{ task.error }}
          </div>

          <div class="task-card-footer">
            <div class="task-card-timestamps">
              <span v-if="task.started_at">开始: {{ formatTime(task.started_at, 'short') }}</span>
              <span v-if="task.completed_at">完成: {{ formatTime(task.completed_at, 'short') }}</span>
              <span v-if="!task.started_at">创建: {{ formatTime(task.created_at, 'short') }}</span>
            </div>
            <div class="task-card-actions">
              <a-button type="link" size="small" @click="handleDetail(task.id)">
                详情
              </a-button>
              <a-button
                type="link"
                size="small"
                danger
                :disabled="!canCancel(task)"
                @click="handleCancel(task.id)"
              >
                取消
              </a-button>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="task-empty">
        <div class="task-empty-icon">🗂️</div>
        <div class="task-empty-title">暂无任务</div>
        <div class="task-empty-subtitle">当你提交知识库导入或其他后台任务时，会在这里展示实时进度。</div>
      </div>
    </div>
  </a-drawer>
</template>

<script setup>
import { computed, h, onBeforeUnmount, watch, ref } from 'vue'
import { Modal } from 'ant-design-vue'
import { useTaskerStore } from '@/stores/tasker'
import { storeToRefs } from 'pinia'
import { ReloadOutlined } from '@ant-design/icons-vue'

const taskerStore = useTaskerStore()
const { isDrawerOpen, sortedTasks, loading, lastError } = storeToRefs(taskerStore)
const isOpen = isDrawerOpen

const tasks = computed(() => sortedTasks.value)
const loadingState = computed(() => Boolean(loading.value))
const lastErrorState = computed(() => lastError.value)
const statusFilter = ref('all')

const filteredTasks = computed(() => {
  const list = tasks.value
  switch (statusFilter.value) {
    case 'active':
      return list.filter((task) => ACTIVE_CLASS_STATUSES.has(task.status))
    case 'success':
      return list.filter((task) => task.status === 'success')
    case 'failed':
      return list.filter((task) => FAILED_STATUSES.has(task.status))
    default:
      return list
  }
})

const hasTasks = computed(() => filteredTasks.value.length > 0)

const ACTIVE_CLASS_STATUSES = new Set(['pending', 'queued', 'running'])
const FAILED_STATUSES = new Set(['failed', 'cancelled'])
const TASK_TYPE_LABELS = {
  knowledge_ingest: '知识库导入',
  graph_task: '图谱处理',
  agent_job: '智能体任务'
}

function taskCardClasses(task) {
  return {
    'task-card--active': ACTIVE_CLASS_STATUSES.has(task.status),
    'task-card--success': task.status === 'success',
    'task-card--failed': task.status === 'failed'
  }
}

function taskTypeLabel(type) {
  if (!type) return '后台任务'
  return TASK_TYPE_LABELS[type] || type
}

function formatTaskId(id) {
  if (!id) return '--'
  return id.slice(0, 8)
}

watch(
  isOpen,
  (open) => {
    if (open) {
      taskerStore.loadTasks()
      taskerStore.startPolling()
    } else {
      taskerStore.stopPolling()
    }
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  taskerStore.stopPolling()
})

function handleClose() {
  taskerStore.closeDrawer()
}

function handleRefresh() {
  taskerStore.loadTasks()
}

function handleDetail(taskId) {
  const task = tasks.value.find(item => item.id === taskId)
  if (!task) {
    return
  }
  const detail = h('div', { class: 'task-detail' }, [
    h('p', [h('strong', '状态：'), statusLabel(task.status)]),
    h('p', [h('strong', '进度：'), `${Math.round(task.progress || 0)}%`]),
    h('p', [h('strong', '更新时间：'), formatTime(task.updated_at)]),
    h('p', [h('strong', '描述：'), task.message || '-']),
    h('p', [h('strong', '错误：'), task.error || '-'])
  ])
  Modal.info({
    title: task.name,
    width: 520,
    content: detail
  })
}

function handleCancel(taskId) {
  taskerStore.cancelTask(taskId)
}

function formatTime(value, format = 'full') {
  if (!value) return '-'
  try {
    const date = new Date(value)
    if (format === 'short') {
      const now = new Date()
      const diff = now - date
      const minutes = Math.floor(diff / 60000)
      const hours = Math.floor(diff / 3600000)
      const days = Math.floor(diff / 86400000)

      if (minutes < 1) return '刚刚'
      if (minutes < 60) return `${minutes}分钟前`
      if (hours < 24) return `${hours}小时前`
      if (days < 7) return `${days}天前`

      return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    }
    return date.toLocaleString()
  } catch {
    return value
  }
}

function getTaskDuration(task) {
  if (!task.started_at || !task.completed_at) return null
  try {
    const start = new Date(task.started_at)
    const end = new Date(task.completed_at)
    const diffMs = end - start
    const seconds = Math.floor(diffMs / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)

    if (hours > 0) {
      return `${hours}小时${minutes % 60}分钟`
    } else if (minutes > 0) {
      return `${minutes}分钟${seconds % 60}秒`
    } else if (seconds > 0) {
      return `${seconds}秒`
    } else {
      return `${diffMs}毫秒`
    }
  } catch {
    return null
  }
}

function isTaskCompleted(task) {
  return ['success', 'failed', 'cancelled'].includes(task.status)
}

function getCompletionIcon(status) {
  const icons = {
    success: '✓',
    failed: '✗',
    cancelled: '○'
  }
  return icons[status] || '?'
}

function statusLabel(status) {
  const map = {
    pending: '等待中',
    queued: '已排队',
    running: '进行中',
    success: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return map[status] || status
}

function statusColor(status) {
  const map = {
    pending: 'blue',
    queued: 'blue',
    running: 'processing',
    success: 'green',
    failed: 'red',
    cancelled: 'gray'
  }
  return map[status] || 'default'
}

function progressStatus(status) {
  if (status === 'failed') return 'exception'
  if (status === 'cancelled') return 'normal'
  return 'active'
}

function canCancel(task) {
  return ['pending', 'running', 'queued'].includes(task.status) && !task.cancel_requested
}

const inProgressCount = computed(
  () => tasks.value.filter((task) => ACTIVE_CLASS_STATUSES.has(task.status)).length
)
const completedCount = computed(() => tasks.value.filter((task) => task.status === 'success').length)
const failedCount = computed(
  () => tasks.value.filter((task) => FAILED_STATUSES.has(task.status)).length
)
const totalCount = computed(() => tasks.value.length)

function setFilter(value) {
  statusFilter.value = value
}

function isActiveFilter(value) {
  return statusFilter.value === value
}
</script>
<style scoped lang="less">
.task-center {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
}

.task-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
  flex-wrap: wrap;
}

.task-filter-group {
  flex-shrink: 0;
}

.task-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.task-filter-group :deep(.ant-btn) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.filter-count {
  margin-left: 2px;
  font-size: 12px;
  color: #94a3b8;
}

.task-toolbar-actions :deep(.ant-btn) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 10px;
}

.task-alert {
  margin-bottom: 4px;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-card {
  background: #ffffff;
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  padding: 16px 18px;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 12px;
  // box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.task-card:hover {
  border-color: rgba(59, 130, 246, 0.3);
}

.task-card--active {
  background: linear-gradient(to bottom, #ffffff, #fbfcff);
}

.task-card--success {
  background: linear-gradient(to bottom, #ffffff, #f7fff9);
}

.task-card--failed {
  background: linear-gradient(to bottom, #ffffff, #fffcfc);
}

.task-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.task-card-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.task-card-title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.3;
  // word-break: break-word;
  text-overflow: ellipsis;
  white-space: nowrap;
  overflow: hidden;
}

.task-card-subtitle {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #64748b;
}

.task-card-id {
  letter-spacing: 0.04em;
}

.task-card-type {
  padding: 0 8px;
  border-radius: 999px;
  background-color: rgba(15, 23, 42, 0.06);
  color: #475569;
  line-height: 20px;
}

.task-card-status {
  margin-top: 2px;
}

.task-card-progress {
  display: flex;
  align-items: center;
  gap: 12px;
}

.task-card-progress :deep(.ant-progress) {
  flex: 1;
}

.task-card-progress-value {
  font-size: 12px;
  font-weight: 500;
  color: #475569;
  width: 48px;
  text-align: right;
}

.task-card-message,
.task-card-error {
  font-size: 13px;
  line-height: 1.45;
  border-radius: 10px;
  padding: 10px 12px;
}

.task-card-message {
  background: rgba(15, 23, 42, 0.03);
  color: #475569;
}

.task-card-error {
  background: rgba(248, 113, 113, 0.12);
  color: #b91c1c;
}

.task-card-footer {
  margin-top: 2px;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
}

.task-card-timestamps {
  display: flex;
  flex-direction: row;
  gap: 6px;
  font-size: 12px;
  color: #94a3b8;
}

.task-card-actions {
  display: flex;
  gap: 6px;
}

.task-card-completion {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.02);
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.completion-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
}

.completion-badge--success {
  color: #16a34a;
}

.completion-badge--success .completion-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #dcfce7;
  font-size: 14px;
}

.completion-badge--failed {
  color: #dc2626;
}

.completion-badge--failed .completion-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #fee2e2;
  font-size: 14px;
}

.completion-badge--cancelled {
  color: #6b7280;
}

.completion-badge--cancelled .completion-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #f3f4f6;
  font-size: 14px;
}

.task-duration {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #64748b;
}

.duration-label {
  font-weight: 500;
}

.duration-value {
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-weight: 600;
  color: #475569;
}

.task-empty {
  margin-top: 32px;
  padding: 40px 30px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.03);
  border: 1px dashed rgba(148, 163, 184, 0.4);
  text-align: center;
  color: #475569;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.task-empty-icon {
  font-size: 28px;
}

.task-empty-title {
  font-size: 16px;
  font-weight: 600;
}

.task-empty-subtitle {
  font-size: 13px;
  max-width: 320px;
  line-height: 1.5;
  color: #94a3b8;
}
</style>
