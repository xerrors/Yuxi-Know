<template>
  <DashboardChartCard class="call-stats" title="调用统计">
    <template #extra>
      <div class="call-actions">
        <div class="time-ranges" role="group" aria-label="统计范围">
          <button
            v-for="option in timeRangeOptions"
            :key="option.value"
            type="button"
            :aria-pressed="callTimeRange === option.value"
            :class="{ active: callTimeRange === option.value }"
            @click="switchTimeRange(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
        <span class="control-divider" aria-hidden="true"></span>
        <div class="call-views" role="group" aria-label="统计视图">
          <button
            v-for="option in dataTypeOptions"
            :key="option.value"
            type="button"
            :aria-pressed="callDataType === option.value"
            :class="{ active: callDataType === option.value }"
            @click="switchDataType(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
        <button
          type="button"
          class="stats-refresh"
          :disabled="callStatsLoading"
          :aria-label="refreshLabel"
          @click="loadCallStats"
        >
          <RefreshCw :size="14" :class="{ spinning: callStatsLoading }" aria-hidden="true" />
        </button>
      </div>
    </template>
    <template #summary>
      <div v-if="!callStatsError && !callStatsLoading" class="dashboard-card-metric-grid">
        <DashboardMetricCard
          :value="formatValueForDisplay(totalCount)"
          :label="isConversation ? '新增会话' : isTokenView ? 'Token 总量' : '调用总量'"
          compact
        />
        <DashboardMetricCard
          :value="formatValueForDisplay(averageCount)"
          :label="`${intervalLabel}均${isConversation ? '新增' : isTokenView ? ' Token' : '调用'}`"
          compact
        />
        <DashboardMetricCard
          :value="formatValueForDisplay(peakCount)"
          :label="`${intervalLabel}${isConversation ? '新增' : ''}峰值`"
          compact
        />
      </div>
    </template>
    <div v-if="callStatsError" class="call-state" role="status">
      {{ isConversation ? '会话统计暂不可用，请重试' : '调用统计暂不可用，请重试' }}
    </div>
    <div v-else-if="callStatsLoading" class="call-state" aria-label="正在加载统计"><a-spin /></div>
    <div v-else-if="!hasChartData" class="call-state">
      {{ isConversation ? '暂无会话数据' : '暂无调用数据' }}
    </div>
    <div
      v-else
      ref="callStatsChartRef"
      class="call-chart"
      :aria-label="isConversation ? '会话趋势柱状图' : '调用统计趋势'"
    ></div>
  </DashboardChartCard>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { RefreshCw } from '@lucide/vue'
import * as echarts from '@/modules/dashboard/model/dashboardCharts'
import { dashboardApi } from '@/apis/dashboard_api'
import { getColorByIndex, truncateLegend } from '@/shared/lib/chartColors'
import { useThemeStore } from '@/shared/model/theme'
import DashboardChartCard from './DashboardChartCard.vue'
import DashboardMetricCard from './DashboardMetricCard.vue'

const themeStore = useThemeStore()
const callStatsData = ref(null)
const callStatsLoading = ref(true)
const callStatsError = ref(false)
const callTimeRange = ref('14days')
const loadedRange = ref('14days')
const callDataType = ref('agents')
const timeRangeOptions = [
  { value: '14hours', label: '14小时' },
  { value: '14days', label: '14天' },
  { value: '14weeks', label: '14周' }
]
const dataTypeOptions = [
  { value: 'agents', label: '智能体' },
  { value: 'tools', label: '工具' },
  { value: 'tokens', label: 'Token' },
  { value: 'sessions', label: '会话' },
  { value: 'models', label: '模型' }
]
const isConversation = computed(() => callDataType.value === 'sessions')
const isTokenView = computed(() => callDataType.value === 'tokens')
const refreshLabel = computed(
  () => `${callStatsError.value ? '重试' : '刷新'}${isConversation.value ? '会话' : '调用'}统计`
)
const intervalLabel = computed(
  () => ({ '14hours': '小时', '14days': '日', '14weeks': '周' })[callTimeRange.value]
)
// 以当前图表区间计算摘要；工具接口的 total_count 是累计值，不能用于周期摘要。
const intervalCounts = computed(() =>
  (callStatsData.value?.data || []).map((day) =>
    isConversation.value
      ? day.data.new_threads
      : Object.values(day.data).reduce((sum, count) => sum + count, 0)
  )
)
const totalCount = computed(() => intervalCounts.value.reduce((sum, count) => sum + count, 0))
const averageCount = computed(() =>
  intervalCounts.value.length
    ? Number((totalCount.value / intervalCounts.value.length).toFixed(2))
    : 0
)
const peakCount = computed(() => Math.max(0, ...intervalCounts.value))
const hasChartData = computed(() =>
  (callStatsData.value?.data || []).some((day) => Object.values(day.data).some((count) => count > 0))
)
const callStatsChartRef = ref(null)
let callStatsChart = null
let resizeObserver = null
let hoveredSeriesName = null
let requestVersion = 0

/** 从当前主题读取图表色值。 */
function getCSSVariable(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

/** Token 以百万为单位，其他计数保留接口精度。 */
function formatValueForDisplay(value) {
  if (isTokenView.value) {
    const million = (value ?? 0) / 1_000_000
    return `${million.toFixed(Math.abs(million) >= 100 ? 0 : Math.abs(million) >= 10 ? 1 : 2)}M`
  }
  return (value ?? 0).toLocaleString()
}

/** 视图变化时使上一请求失效，避免迟到数据覆盖当前口径。 */
function switchDataType(value) {
  if (callDataType.value === value) return
  requestVersion += 1
  callDataType.value = value
  loadCallStats()
}

/** 所有图表 Tab 使用同一组十四个时间区间。 */
function switchTimeRange(value) {
  if (callTimeRange.value === value) return
  callTimeRange.value = value
  loadCallStats()
}

/** 只接受当前视图和周期的响应。 */
async function loadCallStats() {
  const version = ++requestVersion
  const range = callTimeRange.value
  callStatsLoading.value = true
  callStatsError.value = false
  try {
    const response = await dashboardApi.getCallTimeseries(callDataType.value, range)
    if (version !== requestVersion) return
    loadedRange.value = range
    callStatsData.value = response
  } catch {
    if (version !== requestVersion) return
    callStatsData.value = null
    callStatsError.value = true
  } finally {
    if (version === requestVersion) callStatsLoading.value = false
  }
}

/** 绘制当前调用序列，零宽容器由尺寸观察器恢复。 */
function renderCallStatsChart() {
  callStatsChart?.dispose()
  callStatsChart = null
  const container = callStatsChartRef.value
  if (!container?.clientWidth || !callStatsData.value) return
  callStatsChart = echarts.init(container)
  hoveredSeriesName = null
  const data = callStatsData.value.data || []
  const categories = callStatsData.value.categories || []

  const xAxisData = data.map((item) => {
    const date = item.date
    if (loadedRange.value === '14hours') {
      return date.split(' ')[1]
    } else if (loadedRange.value === '14weeks') {
      return `第${date.split('-')[1]}周`
    } else {
      return date.split('-').slice(1).join('-')
    }
  })

  const agentNames = callStatsData.value.agent_names || {}

  const resolveCategoryLabel = (cat) => {
    if (isConversation.value)
      return { new_threads: '新增会话', active_threads: '活跃会话' }[cat] || cat
    if (cat === 'None') return '未知模型'
    return agentNames[cat] || cat
  }

  const series = categories.map((category, index) => ({
    name: resolveCategoryLabel(category),
    type: 'bar',
    stack: isConversation.value ? undefined : 'total',
    emphasis: { focus: 'series' },
    data: data.map((item) => item.data[category] || 0),
    itemStyle: {
      color: getColorByIndex(index),
      borderRadius: 0
    }
  }))

  const option = {
    grid: {
      left: '3%',
      right: '4%',
      top: '5%' /* 减少顶部留白 */,
      bottom: 50 /* 减少底部留白，从60减少到50 */,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLine: { lineStyle: { color: getCSSVariable('--gray-200') } },
      axisTick: { show: false },
      axisLabel: { color: getCSSVariable('--gray-500'), fontSize: 12 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: getCSSVariable('--gray-500'),
        fontSize: 12,
        formatter: (value) => (isTokenView.value ? formatValueForDisplay(value) : value)
      },
      splitLine: { lineStyle: { color: getCSSVariable('--gray-100') } }
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: getCSSVariable('--gray-0'),
      borderColor: getCSSVariable('--gray-200'),
      borderWidth: 1,
      textStyle: { color: getCSSVariable('--gray-600'), fontSize: 12 },
      formatter: (params) => {
        if (!params?.length) return ''
        const visibleParams = params.filter((param) => Number(param.value) !== 0)
        if (!visibleParams.length) return ''
        let total = 0
        let result = `${visibleParams[0].name}<br/>`
        visibleParams.forEach((param) => {
          total += param.value
          const truncatedName = truncateLegend(param.seriesName)
          const isHovered = param.seriesName === hoveredSeriesName
          const itemStyle = isHovered ? 'font-weight:700;color:var(--gray-900)' : ''
          result += `<span style="display:inline-block;margin-right:5px;border-radius:10px;width:10px;height:10px;background-color:${param.color}"></span>`
          result += `<span style="${itemStyle}">${truncatedName}: ${formatValueForDisplay(param.value)}</span><br/>`
        })
        const labelMap = {
          models: '模型调用',
          agents: '智能体调用',
          tokens: 'Token消耗',
          tools: '工具调用',
          sessions: '会话趋势'
        }
        const formattedTotal = formatValueForDisplay(total)
        return `<div style="font-weight:bold;margin-bottom:5px">${labelMap[callDataType.value]}</div>${result}${isConversation.value ? '' : `<strong>总计: ${formattedTotal}</strong>`}`
      }
    },
    legend: {
      type: 'scroll',
      data: categories.map(resolveCategoryLabel),
      bottom: 5 /* 调整图例位置，从0改为5 */,
      textStyle: { color: getCSSVariable('--gray-500'), fontSize: 12 },
      itemWidth: 14,
      itemHeight: 14,
      formatter: (name) => truncateLegend(name),
      pageIconSize: 12,
      pageIconColor: getCSSVariable('--gray-500'),
      pageIconInactiveColor: getCSSVariable('--gray-300'),
      pageTextStyle: { color: getCSSVariable('--gray-500') }
    },
    series
  }

  callStatsChart.setOption(option)
  callStatsChart.on('mouseover', (event) => {
    hoveredSeriesName = event?.seriesName || null
  })
  callStatsChart.on('mouseout', () => {
    hoveredSeriesName = null
  })
}

/** 同步侧栏、网格与 Tab 切换后的实际尺寸。 */
function resizeCharts() {
  if (!callStatsChartRef.value?.clientWidth) return
  if (callStatsChart) callStatsChart.resize()
  else renderCallStatsChart()
}

/** 释放图表及观察器，并拒绝离开后的请求回写。 */
function cleanup() {
  requestVersion += 1
  resizeObserver?.disconnect()
  callStatsChart?.dispose()
  callStatsChart = null
}
watch(
  [callStatsChartRef, callStatsData, callDataType, () => themeStore.isDark],
  async () => {
    await nextTick()
    resizeObserver?.disconnect()
    if (callStatsChartRef.value) {
      resizeObserver = new ResizeObserver(resizeCharts)
      resizeObserver.observe(callStatsChartRef.value)
    }
    renderCallStatsChart()
  },
  { flush: 'post' }
)
onMounted(loadCallStats)
onUnmounted(cleanup)
defineExpose({ cleanup, resizeCharts })
</script>

<style scoped>
.call-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}
.time-ranges,
.call-views {
  display: flex;
  align-items: center;
  gap: 4px;
}
.time-ranges button,
.call-views button {
  padding: 4px 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--gray-500);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.time-ranges button:hover,
.call-views button:hover {
  background: var(--gray-100);
  color: var(--gray-900);
}
.time-ranges button.active,
.call-views button.active {
  background: var(--main-600);
  color: var(--gray-0);
}
.time-ranges button:focus-visible,
.call-views button:focus-visible,
.stats-refresh:focus-visible {
  outline: 2px solid var(--main-color);
  outline-offset: 2px;
}
.control-divider {
  width: 1px;
  height: 16px;
  background: var(--gray-200);
}
:deep(.ant-card-head-wrapper) {
  flex-wrap: wrap;
  gap: 8px;
  padding-block: 12px;
}
:deep(.ant-card-head-title) {
  flex: none;
  overflow: visible;
}
:deep(.ant-card-extra) {
  max-width: 100%;
  margin-left: auto;
}
.stats-refresh {
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
.stats-refresh:hover {
  background: var(--gray-100);
}
.stats-refresh:disabled {
  cursor: wait;
}
.call-chart {
  width: 100%;
  height: 286px;
}
.call-state {
  display: grid;
  place-items: center;
  min-height: 286px;
  color: var(--gray-600);
}
.spinning {
  animation: spin 1.2s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .spinning {
    animation: none;
  }
}
</style>
