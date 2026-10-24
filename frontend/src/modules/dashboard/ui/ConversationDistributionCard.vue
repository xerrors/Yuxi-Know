<template>
  <DashboardChartCard class="conversation-distribution conversation-agents" title="智能体会话分布">
    <template #extra>
      <div class="distribution-actions">
        <a-select
          v-model:value="timeRange"
          :options="rangeOptions"
          :dropdown-match-select-width="false"
          size="small"
          aria-label="智能体会话统计范围"
          @change="loadStats"
        />
        <button
          type="button"
          class="distribution-refresh"
          :disabled="loading"
          :aria-label="error ? '重试智能体会话分布' : '刷新智能体会话分布'"
          @click="loadStats"
        >
          <RefreshCw :size="14" aria-hidden="true" />
        </button>
      </div>
    </template>
    <template v-if="stats && !error && !loading" #summary>
      <div class="dashboard-card-metric-grid distribution-summary">
        <DashboardMetricCard
          :value="formatNumber(stats.agent_count)"
          label="有会话的智能体"
          compact
        />
        <DashboardMetricCard
          :value="formatNumber(stats.total_threads)"
          :label="timeRange === 'all' ? '累计会话' : '会话数'"
          compact
        />
        <DashboardMetricCard
          :value="stats.avg_messages_per_thread"
          label="平均消息数 / 会话"
          compact
        />
      </div>
    </template>
    <div v-if="loading" class="distribution-state" aria-label="正在加载智能体会话分布">
      <a-spin />
    </div>
    <div v-else-if="error" class="distribution-state" role="status">
      智能体会话分布暂不可用，请重试
    </div>
    <template v-else>
      <div class="distribution-caption">
        {{ timeRange === 'all' ? '按会话数排序 · 前 8 位' : '按所选范围内新建会话统计 · 前 8 位' }}
      </div>
      <ol v-if="rows.length" class="distribution-list" aria-label="智能体会话排行">
        <li v-for="row in rows" :key="row.agent_id">
          <div class="distribution-row">
            <span class="row-name" :title="row.agent_name">{{ row.agent_name }}</span>
            <span class="row-detail">平均 {{ row.avg_messages }} 条</span>
            <strong>{{ formatNumber(row.thread_count) }}<small> 会话</small></strong>
          </div>
          <div class="distribution-track">
            <span :style="{ width: `${(row.thread_count / maximum) * 100}%` }"></span>
          </div>
        </li>
      </ol>
      <div v-else class="distribution-state">暂无会话数据</div>
    </template>
  </DashboardChartCard>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RefreshCw } from '@lucide/vue'
import { dashboardApi } from '@/apis/dashboard_api'
import DashboardChartCard from './DashboardChartCard.vue'
import DashboardMetricCard from './DashboardMetricCard.vue'
import { formatNumber } from '@/modules/dashboard/model/dashboard'

const timeRange = ref('all')
const rangeOptions = [
  { value: 'all', label: '累计' },
  { value: '7days', label: '近7天' },
  { value: '30days', label: '近30天' },
  { value: '3months', label: '近3个月' }
]
const stats = ref(null)
const loading = ref(true)
const error = ref(false)
const rows = computed(() => (stats.value?.agent_distribution || []).slice(0, 8))
const maximum = computed(() => Math.max(1, ...rows.value.map((row) => row.thread_count)))
let requestVersion = 0

/** 范围切换时只投影最新响应，摘要和排行使用同一数据。 */
async function loadStats() {
  const version = ++requestVersion
  loading.value = true
  error.value = false
  try {
    const response = await dashboardApi.getAgentSessionDistribution(timeRange.value)
    if (version !== requestVersion) return
    stats.value = response
  } catch {
    if (version !== requestVersion) return
    stats.value = null
    error.value = true
  } finally {
    if (version === requestVersion) loading.value = false
  }
}
onMounted(loadStats)
onUnmounted(() => {
  requestVersion += 1
})
</script>

<style scoped>
.distribution-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.distribution-actions :deep(.ant-select) {
  /* 触发器保持紧凑的同时加宽下拉，避免「近30天」等选项被省略号截断 */
  min-width: 88px;
}
.distribution-refresh {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--gray-600);
  cursor: pointer;
}
.distribution-refresh:hover {
  background: var(--gray-100);
}
.distribution-refresh:focus-visible {
  outline: 2px solid var(--main-color);
  outline-offset: 2px;
}
.distribution-refresh:disabled {
  cursor: wait;
}

.distribution-caption {
  font-size: 12px;
  color: var(--gray-600);
}
.distribution-caption {
  padding: 4px 0 16px;
}
.distribution-summary :deep(.dashboard-metric-label) {
  white-space: normal;
}
.distribution-summary {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.distribution-list {
  display: grid;
  gap: 16px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.distribution-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 12px;
}
.row-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--gray-800);
}
.row-detail {
  color: var(--gray-600);
  white-space: nowrap;
}
.distribution-row strong {
  color: var(--gray-900);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.distribution-row small {
  font-size: 11px;
  color: var(--gray-600);
  font-weight: 400;
}
.distribution-track {
  height: 4px;
  margin-top: 7px;
  overflow: hidden;
  border-radius: 2px;
  background: var(--gray-100);
}
.distribution-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--main-color);
  opacity: 0.75;
}
.distribution-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  color: var(--gray-600);
}
</style>
