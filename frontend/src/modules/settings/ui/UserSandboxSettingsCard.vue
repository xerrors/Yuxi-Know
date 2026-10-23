<template>
  <section class="sandbox-settings" aria-label="Agent 环境">
    <div class="sandbox-heading">
      <div>
        <h3>Agent 环境</h3>
        <p>{{ ephemeral ? '每个任务独立临时环境，任务结束后销毁' : '所有对话共享此环境' }}</p>
      </div>
      <a-button
        class="sandbox-icon-button"
        type="text"
        :loading="loading"
        aria-label="刷新环境状态"
        @click="refresh"
      >
        <template #icon><RefreshCw :size="16" /></template>
      </a-button>
    </div>

    <div class="sandbox-overview">
      <div class="sandbox-state-row">
        <span class="sandbox-label">状态</span>
        <div class="sandbox-state-content" :title="stateTitle">
          <span
            class="sandbox-state-value"
            :class="`is-${statePresentation.tone}`"
            aria-live="polite"
          >
            <component :is="statePresentation.icon" :size="14" aria-hidden="true" />
            {{ statePresentation.label }}
          </span>
          <span v-if="timingText" class="sandbox-state-separator" aria-hidden="true">·</span>
          <span v-if="timingText" class="sandbox-timing">{{ timingText }}</span>
        </div>
        <ActionDropdown v-if="!ephemeral" v-model:open="menuOpen" :width="144">
          <template #trigger
            ><a-button
              class="sandbox-icon-button"
              type="text"
              :loading="rebuilding"
              aria-label="环境操作"
              aria-haspopup="menu"
              :aria-expanded="menuOpen"
              title="环境操作"
            >
              <template #icon><MoreHorizontal :size="16" /></template> </a-button
          ></template>
          <div role="menu">
            <button
              type="button"
              role="menuitem"
              class="config-dropdown-item sandbox-rebuild"
              :disabled="!status || status.busy || loading || rebuilding"
              :title="status?.busy ? '存在活动任务或待清理操作，暂不可重建' : undefined"
              @click="confirmRebuild"
            >
              重建环境
            </button>
          </div>
        </ActionDropdown>
      </div>
      <div v-if="!ephemeral" class="sandbox-disk" title="系统和主目录所在磁盘，不含共享工作区">
        <span class="sandbox-label">磁盘</span>
        <div class="sandbox-disk-content">
          <span v-if="diskUsage" title="上次手动查询的结果"
            >已用 {{ formatFileSize(diskUsage.used_bytes) }} · 可用
            {{ formatFileSize(diskUsage.available_bytes) }}</span
          >
          <span v-else class="sandbox-muted">尚未查询</span>
          <a-button
            class="sandbox-disk-action"
            type="link"
            size="small"
            :loading="diskLoading"
            :disabled="!['running', 'paused'].includes(status?.state)"
            :aria-label="diskUsage ? '刷新磁盘用量' : '查看磁盘用量'"
            @click="readDiskUsage"
            >{{ diskUsage ? '刷新' : '查看' }}</a-button
          >
          <span v-if="status?.state === 'paused'" class="sandbox-muted">查询时会恢复环境</span>
        </div>
      </div>
    </div>
    <p v-if="diskError" class="sandbox-description" role="alert">{{ diskError }}</p>
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <ul v-if="status?.active_runs?.length" class="sandbox-runs">
      <li v-for="run in status.active_runs" :key="run.id">
        <span>{{ run.status === 'cancel_requested' ? '取消处理中' : '任务处理中' }}</span>
        <RouterLink
          target="_blank"
          rel="noopener noreferrer"
          :to="{ name: 'AgentCompWithThreadId', params: { thread_id: run.thread_id } }"
          >查看对话</RouterLink
        >
      </li>
    </ul>
    <p v-if="status?.active_operations" class="sandbox-description">
      活动操作及待清理命令：{{ status.active_operations }} 项。
    </p>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import {
  CircleAlert,
  CircleDashed,
  CircleHelp,
  CirclePlay,
  LoaderCircle,
  Moon,
  MoreHorizontal,
  RefreshCw
} from '@lucide/vue'
import { sandboxApi } from '@/apis/sandbox_api'
import { formatSandboxDuration, sandboxTimingText } from '../model/sandboxTiming'
import { formatFileSize } from '@/shared/lib/file_utils'
import { formatFullDateTime } from '@/shared/lib/time'
import ActionDropdown from '@/shared/ui/ActionDropdown.vue'

const status = ref(null)
const error = ref('')
const loading = ref(false)
const rebuilding = ref(false)
const menuOpen = ref(false)
const diskUsage = ref(null)
const diskLoading = ref(false)
const diskError = ref('')
let diskVersion = 0
const clock = ref(Date.now())
const receivedAt = ref(clock.value)
let clockTimer
let refreshTimer
let refreshVersion = 0
const states = {
  not_created: { label: '未创建', icon: CircleDashed, tone: 'muted' },
  running: { label: '运行中', icon: CirclePlay, tone: 'success' },
  paused: { label: '已休眠', icon: Moon, tone: 'muted' },
  creating: { label: '创建中', icon: LoaderCircle, tone: 'pending' },
  rebuilding: { label: '重建中', icon: LoaderCircle, tone: 'pending' },
  resuming: { label: '恢复中', icon: LoaderCircle, tone: 'pending' },
  pausing: { label: '休眠处理中', icon: LoaderCircle, tone: 'pending' },
  failed: { label: '环境异常', icon: CircleAlert, tone: 'error' }
}
const statePresentation = computed(
  () =>
    states[status.value?.state] ||
    (loading.value
      ? { label: '读取中', icon: LoaderCircle, tone: 'muted' }
      : { label: '状态未知', icon: CircleHelp, tone: 'muted' })
)
const ephemeral = computed(() => status.value?.backend === 'container')
const stateTitle = computed(() => {
  const value = status.value
  if (ephemeral.value) return '任务首次执行命令时创建，任务结束后销毁'
  if (value?.state === 'paused' && value.paused_at)
    return `休眠于 ${formatFullDateTime(value.paused_at)}`
  if (value?.state === 'not_created') return '首次执行时自动创建'
  return value
    ? `空闲 ${formatSandboxDuration(value.idle_timeout_seconds)}自动休眠，执行时自动恢复`
    : ''
})
const timingText = computed(() => {
  if (ephemeral.value) return ''
  const serverTime = Date.parse(status.value?.server_time)
  return sandboxTimingText(status.value, serverTime + clock.value - receivedAt.value)
})

function updateStatus(value) {
  if (status.value && value.generation !== status.value.generation) {
    clearDiskUsage()
  }
  receivedAt.value = clock.value = Date.now()
  status.value = value
  error.value = value.error || ''
}

function clearDiskUsage() {
  diskVersion++
  diskUsage.value = null
  diskLoading.value = false
  diskError.value = ''
}

async function refresh() {
  const version = ++refreshVersion
  loading.value = true
  error.value = ''
  try {
    const value = await sandboxApi.get()
    if (version === refreshVersion) updateStatus(value)
  } catch (failure) {
    if (version === refreshVersion) {
      status.value = null
      clearDiskUsage()
      error.value = failure.message || '环境状态读取失败'
    }
  } finally {
    if (version === refreshVersion) loading.value = false
  }
}

async function readDiskUsage() {
  const version = ++diskVersion
  diskLoading.value = true
  diskError.value = ''
  try {
    const value = await sandboxApi.diskUsage()
    if (version === diskVersion) diskUsage.value = value
  } catch (failure) {
    if (version === diskVersion) {
      diskUsage.value = null
      diskError.value = failure.message || '磁盘用量读取失败，请重试'
    }
  } finally {
    if (version === diskVersion) {
      diskLoading.value = false
      await refresh()
    }
  }
}

async function confirmRebuild() {
  menuOpen.value = false
  await refresh()
  if (!status.value || status.value.busy) return
  Modal.confirm({
    title: '确认重建运行环境',
    content: '重建将清除已安装软件及用户主目录中的文件与配置。工作区文件与技能将保留。',
    okText: '确认重建',
    cancelText: '取消',
    okButtonProps: { danger: true },
    async onOk() {
      rebuilding.value = true
      try {
        const value = await sandboxApi.rebuild()
        refreshVersion++
        loading.value = false
        updateStatus(value)
        message.success('运行环境重建完成')
      } catch (failure) {
        message.error(failure.message || '环境重建失败，请刷新状态后重试')
        await refresh()
      } finally {
        rebuilding.value = false
      }
    }
  })
}

onMounted(() => {
  refresh()
  clockTimer = setInterval(() => {
    clock.value = Date.now()
  }, 1000)
  refreshTimer = setInterval(() => {
    if (!loading.value && !rebuilding.value) refresh()
  }, 15000)
})
onUnmounted(() => {
  refreshVersion++
  diskVersion++
  clearInterval(clockTimer)
  clearInterval(refreshTimer)
})
defineExpose({ refresh })
</script>

<style scoped>
.sandbox-settings {
  margin-bottom: 28px;
}
.sandbox-heading,
.sandbox-state-row,
.sandbox-disk,
.sandbox-runs li {
  display: flex;
  align-items: center;
  gap: 12px;
}
.sandbox-heading {
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}
.sandbox-heading h3 {
  margin: 0;
  color: var(--color-text);
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}
.sandbox-heading p,
.sandbox-description {
  margin: 6px 0 0;
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 20px;
}
.sandbox-overview {
  margin-bottom: 12px;
  font-size: 14px;
  line-height: 22px;
}
.sandbox-label {
  width: 36px;
  flex-shrink: 0;
  color: var(--color-text-secondary);
}
.sandbox-state-content {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  color: var(--color-text-secondary);
}
.sandbox-disk-content {
  color: var(--color-text);
}
.sandbox-state-value {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}
.sandbox-state-value.is-success {
  color: var(--color-success-900);
}
.sandbox-state-value.is-pending {
  color: var(--color-info-900);
}
.sandbox-state-separator {
  flex-shrink: 0;
}
.sandbox-timing {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sandbox-state-value.is-error {
  color: var(--color-error-700);
}
.sandbox-disk {
  min-height: 32px;
}
.sandbox-disk-content {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  column-gap: 6px;
  min-width: 0;
}
.sandbox-muted {
  color: var(--color-text-secondary);
}
.sandbox-disk-action {
  height: 32px;
  padding: 0;
  font: inherit;
}
.sandbox-icon-button {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.sandbox-rebuild {
  color: var(--color-error-700);
}
.sandbox-rebuild:disabled {
  color: var(--color-text-secondary);
  cursor: not-allowed;
}
.sandbox-description,
.sandbox-settings > :deep(.ant-alert) {
  margin-bottom: 12px;
}
.sandbox-runs {
  margin: 0 0 12px;
  padding: 0;
  list-style: none;
  font-size: 12px;
}
.sandbox-runs li {
  justify-content: space-between;
  padding: 6px 0;
}
</style>
