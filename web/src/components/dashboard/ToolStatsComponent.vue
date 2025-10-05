<template>
  <a-card title="工具调用监控" :loading="loading" class="dashboard-card">
    <!-- 工具调用概览 -->
    <div class="stats-overview">
      <a-row :gutter="16">
        <a-col :span="6">
          <a-statistic
            title="总调用次数"
            :value="toolStats?.total_calls || 0"
            :value-style="{ color: 'var(--chart-info)' }"
          />
        </a-col>
        <a-col :span="6">
          <a-statistic
            title="成功调用"
            :value="toolStats?.successful_calls || 0"
            :value-style="{ color: 'var(--chart-success)' }"
            suffix="次"
          />
        </a-col>
        <a-col :span="6">
          <a-statistic
            title="失败调用"
            :value="toolStats?.failed_calls || 0"
            :value-style="{ color: 'var(--chart-error)' }"
            suffix="次"
          />
        </a-col>
        <a-col :span="6">
          <a-statistic
            title="成功率"
            :value="toolStats?.success_rate || 0"
            suffix="%"
            :value-style="{
              color: (toolStats?.success_rate || 0) >= 90 ? 'var(--chart-success)' :
                     (toolStats?.success_rate || 0) >= 70 ? 'var(--chart-warning)' : 'var(--chart-error)'
            }"
          />
        </a-col>
      </a-row>
    </div>

    <!-- 最常用工具 -->
    <a-divider />
    <div class="chart-container">
      <h4>最常用工具 TOP 10</h4>
      <div ref="toolsChartRef" class="chart"></div>
    </div>

    <!-- 错误分析 -->
    <a-divider />
    <div class="error-analysis" v-if="hasErrorData">
      <h4>工具错误分析</h4>
      <a-row :gutter="16">
        <a-col :span="12">
          <a-table
            :columns="errorColumns"
            :data-source="errorData"
            size="small"
            :pagination="false"
            :scroll="{ y: 200 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'tool_name'">
                <a-tag color="blue">{{ record.tool_name }}</a-tag>
              </template>
              <template v-if="column.key === 'error_count'">
                <a-tag :color="record.error_count > 5 ? 'red' : 'orange'">
                  {{ record.error_count }}
                </a-tag>
              </template>
            </template>
          </a-table>
        </a-col>
        <a-col :span="12">
          <div class="chart-container">
            <h4>错误分布图</h4>
            <div ref="errorChartRef" class="chart-small"></div>
          </div>
        </a-col>
      </a-row>
    </div>
  </a-card>
</template>

<script setup>
import { ref, onMounted, watch, nextTick, computed } from 'vue'
import * as echarts from 'echarts'

// Props
const props = defineProps({
  toolStats: {
    type: Object,
    default: () => ({})
  },
  loading: {
    type: Boolean,
    default: false
  }
})

// Chart refs
const toolsChartRef = ref(null)
const errorChartRef = ref(null)
let toolsChart = null
let errorChart = null

// 错误分析相关
const errorColumns = [
  {
    title: '工具名称',
    dataIndex: 'tool_name',
    key: 'tool_name',
    width: '50%'
  },
  {
    title: '错误次数',
    dataIndex: 'error_count',
    key: 'error_count',
    width: '50%',
    sorter: (a, b) => a.error_count - b.error_count
  }
]

const hasErrorData = computed(() => {
  return props.toolStats?.tool_error_distribution &&
         Object.keys(props.toolStats.tool_error_distribution).length > 0
})

const errorData = computed(() => {
  if (!hasErrorData.value) return []

  return Object.entries(props.toolStats.tool_error_distribution)
    .map(([tool_name, error_count]) => ({ tool_name, error_count }))
    .sort((a, b) => b.error_count - a.error_count)
})

// 初始化最常用工具图表
const initToolsChart = () => {
  if (!toolsChartRef.value || !props.toolStats?.most_used_tools?.length) return

  toolsChart = echarts.init(toolsChartRef.value)

  const data = props.toolStats.most_used_tools.slice(0, 10) // 只显示前10个

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      },
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#e8e8e8',
      borderWidth: 1,
      textStyle: {
        color: '#666'
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '5%',
      containLabel: true
    },
    xAxis: {
      type: 'value',
      axisLine: {
        lineStyle: {
          color: '#e8e8e8'
        }
      },
      axisLabel: {
        color: '#666'
      },
      splitLine: {
        lineStyle: {
          color: '#f0f0f0'
        }
      }
    },
    yAxis: {
      type: 'category',
      data: data.map(item => item.tool_name),
      axisLine: {
        lineStyle: {
          color: '#e8e8e8'
        }
      },
      axisLabel: {
        color: '#666',
        interval: 0
      }
    },
    series: [{
      name: '调用次数',
      type: 'bar',
      data: data.map(item => item.count),
      itemStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 1,
          y2: 0,
          colorStops: [{
            offset: 0, color: '#3996ae'
          }, {
            offset: 1, color: '#5faec2'
          }]
        },
        borderRadius: [0, 4, 4, 0]
      },
      emphasis: {
        itemStyle: {
          color: '#24839a',
          shadowBlur: 10,
          shadowColor: 'rgba(57, 150, 174, 0.3)'
        }
      }
    }]
  }

  toolsChart.setOption(option)
}

// 初始化错误分布图
const initErrorChart = () => {
  if (!errorChartRef.value || !hasErrorData.value) return

  errorChart = echarts.init(errorChartRef.value)

  const data = errorData.value.slice(0, 5) // 只显示前5个

  const option = {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#e8e8e8',
      borderWidth: 1,
      textStyle: {
        color: '#666'
      },
      formatter: '{a} <br/>{b}: {c} ({d}%)'
    },
    series: [{
      name: '错误分布',
      type: 'pie',
      radius: ['30%', '70%'],
      center: ['50%', '60%'],
      data: data.map(item => ({
        name: item.tool_name,
        value: item.error_count
      })),
      itemStyle: {
        borderRadius: 6,
        borderColor: '#fff',
        borderWidth: 2
      },
      label: {
        show: true,
        formatter: '{b}: {c}'
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      },
      color: ['#3996ae', '#5faec2', '#82c3d6', '#a3d8e8', '#24839a']
    }]
  }

  errorChart.setOption(option)
}

// 更新图表
const updateCharts = () => {
  nextTick(() => {
    initToolsChart()
    if (hasErrorData.value) {
      initErrorChart()
    }
  })
}

// 监听数据变化
watch(() => props.toolStats, () => {
  updateCharts()
}, { deep: true })

// 窗口大小变化时重新调整图表
const handleResize = () => {
  if (toolsChart) toolsChart.resize()
  if (errorChart) errorChart.resize()
}

onMounted(() => {
  updateCharts()
  window.addEventListener('resize', handleResize)
})

// 组件卸载时清理
const cleanup = () => {
  window.removeEventListener('resize', handleResize)
  if (toolsChart) {
    toolsChart.dispose()
    toolsChart = null
  }
  if (errorChart) {
    errorChart.dispose()
    errorChart = null
  }
}

// 导出清理函数供父组件调用
defineExpose({
  cleanup
})
</script>

<style scoped lang="less">
@import '@/assets/css/dashboard.css';

// ToolStatsComponent 特有的样式
.error-analysis {
  h4 {
    margin-bottom: 16px;
    color: var(--gray-1000);
    font-weight: 500;
  }
}
</style>