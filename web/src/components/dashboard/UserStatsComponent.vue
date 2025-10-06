<template>
  <a-card title="用户活跃度分析" :loading="loading" class="dashboard-card">
    <!-- 紧凑型用户统计概览 -->
    <div class="compact-stats-grid">
      <div class="mini-stat-card">
        <div class="mini-stat-value">{{ userStats?.total_users || 0 }}</div>
        <div class="mini-stat-label">总用户</div>
      </div>
      <div class="mini-stat-card">
        <div class="mini-stat-value">{{ userStats?.active_users_24h || 0 }}</div>
        <div class="mini-stat-label">24h活跃</div>
      </div>
      <div class="mini-stat-card">
        <div class="mini-stat-value">{{ userStats?.active_users_30d || 0 }}</div>
        <div class="mini-stat-label">30天活跃</div>
      </div>
    </div>

    <!-- 图表区域 - 更紧凑 -->
    <div class="compact-chart-container">
      <div class="chart-header">
        <span class="chart-title">活跃度趋势</span>
        <span class="chart-subtitle">最近7天</span>
      </div>
      <div ref="activityChartRef" class="compact-chart"></div>
    </div>
  </a-card>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { dashboardApi } from '@/apis/dashboard_api'

// Props
const props = defineProps({
  userStats: {
    type: Object,
    default: () => ({})
  },
  loading: {
    type: Boolean,
    default: false
  }
})

// Chart refs
const activityChartRef = ref(null)
let activityChart = null

// 初始化活跃度趋势图
const initActivityChart = () => {
  if (!activityChartRef.value || !props.userStats?.daily_active_users) return

  activityChart = echarts.init(activityChartRef.value)

  const option = {
    tooltip: {
      trigger: 'axis',
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
      top: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: props.userStats.daily_active_users.map(item => item.date),
      axisLine: {
        lineStyle: {
          color: '#e8e8e8'
        }
      },
      axisLabel: {
        color: '#666'
      }
    },
    yAxis: {
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
    series: [{
      name: '活跃用户数',
      type: 'line',
      data: props.userStats.daily_active_users.map(item => item.active_users),
      smooth: true,
      lineStyle: {
        color: '#3996ae',
        width: 3
      },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [{
            offset: 0, color: 'rgba(57, 150, 174, 0.3)'
          }, {
            offset: 1, color: 'rgba(57, 150, 174, 0.05)'
          }]
        }
      },
      itemStyle: {
        color: '#3996ae',
        borderWidth: 2,
        borderColor: '#fff'
      },
      emphasis: {
        itemStyle: {
          color: '#24839a',
          borderWidth: 3,
          borderColor: '#fff',
          shadowBlur: 10,
          shadowColor: 'rgba(57, 150, 174, 0.5)'
        }
      }
    }]
  }

  activityChart.setOption(option)
}


// 更新图表
const updateCharts = () => {
  nextTick(() => {
    initActivityChart()
  })
}

// 监听数据变化
watch(() => props.userStats, () => {
  updateCharts()
}, { deep: true })

// 窗口大小变化时重新调整图表
const handleResize = () => {
  if (activityChart) activityChart.resize()
}

onMounted(() => {
  updateCharts()
  window.addEventListener('resize', handleResize)
})

// 组件卸载时清理
const cleanup = () => {
  window.removeEventListener('resize', handleResize)
  if (activityChart) {
    activityChart.dispose()
    activityChart = null
  }
}

// 导出清理函数供父组件调用
defineExpose({
  cleanup
})
</script>

<style scoped lang="less">

// UserStatsComponent 特有的样式
.compact-chart-container {
  .chart-header {
    .chart-title {
      color: var(--chart-primary);
    }
  }
}
</style>