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
import { useThemeStore } from '@/stores/theme'

// CSS 变量解析工具函数
function getCSSVariable(variableName, element = document.documentElement) {
  return getComputedStyle(element).getPropertyValue(variableName).trim()
}

// theme store
const themeStore = useThemeStore()

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

  // 如果已存在图表实例，先销毁
  if (activityChart) {
    activityChart.dispose()
    activityChart = null
  }

  activityChart = echarts.init(activityChartRef.value)

  const option = {
    tooltip: {
      trigger: 'axis',
      backgroundColor: getCSSVariable('--gray-0'),
      borderColor: getCSSVariable('--gray-200'),
      borderWidth: 1,
      textStyle: {
        color: getCSSVariable('--gray-600')
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
      data: props.userStats.daily_active_users.map((item) => item.date),
      axisLine: {
        lineStyle: {
          color: getCSSVariable('--gray-200')
        }
      },
      axisLabel: {
        color: getCSSVariable('--gray-500')
      }
    },
    yAxis: {
      type: 'value',
      axisLine: {
        lineStyle: {
          color: getCSSVariable('--gray-200')
        }
      },
      axisLabel: {
        color: getCSSVariable('--gray-500')
      },
      splitLine: {
        lineStyle: {
          color: getCSSVariable('--gray-100')
        }
      }
    },
    series: [
      {
        name: '活跃用户数',
        type: 'line',
        data: props.userStats.daily_active_users.map((item) => item.active_users),
        smooth: true,
        lineStyle: {
          color: getCSSVariable('--main-color'),
          width: 3
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              {
                offset: 0,
                color: getCSSVariable('--main-500')
              },
              {
                offset: 1,
                color: getCSSVariable('--main-0')
              }
            ]
          }
        },
        itemStyle: {
          color: getCSSVariable('--main-color'),
          borderWidth: 2,
          borderColor: getCSSVariable('--gray-0')
        },
        emphasis: {
          itemStyle: {
            color: getCSSVariable('--main-color'),
            borderWidth: 3,
            borderColor: getCSSVariable('--gray-0'),
            shadowBlur: 10,
            shadowColor: getCSSVariable('--shadow-1')
          }
        }
      }
    ]
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
watch(
  () => props.userStats,
  () => {
    updateCharts()
  },
  { deep: true }
)

// 窗口大小变化时重新调整图表
const handleResize = () => {
  if (activityChart) activityChart.resize()
}

onMounted(() => {
  updateCharts()
  window.addEventListener('resize', handleResize)
})

// 监听主题变化，重新渲染图表
watch(
  () => themeStore.isDark,
  () => {
    if (props.userStats?.daily_active_users && activityChart) {
      nextTick(() => {
        initActivityChart()
      })
    }
  }
)

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
/* 紧凑型统计网格 */
.compact-stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 16px;

  .mini-stat-card {
    background-color: var(--gray-0);
    border: 1px solid var(--gray-100);
    border-radius: 6px;
    padding: 16px;
    text-align: center;
    transition: all 0.2s ease;

    &:hover {
      border-color: var(--gray-200);
    }

    .mini-stat-value {
      font-size: 20px;
      font-weight: 600;
      color: var(--gray-1000);
      line-height: 1.2;
      margin-bottom: 4px;
    }

    .mini-stat-label {
      font-size: 12px;
      color: var(--gray-600);
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.025em;
    }
  }
}

/* 紧凑型图表容器 */
.compact-chart-container {
  background-color: var(--gray-0);
  border: 1px solid var(--gray-100);
  border-radius: 6px;
  padding: 16px;
  height: 240px;
  transition: all 0.2s ease;

  &:hover {
    border-color: var(--gray-200);
  }

  .chart-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;

    .chart-title {
      font-size: 14px;
      font-weight: 600;
      color: var(--gray-1000);
    }

    .chart-subtitle {
      font-size: 11px;
      color: var(--gray-600);
      background-color: var(--gray-100);
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.025em;
    }
  }

  .compact-chart {
    height: 180px;
    width: 100%;
  }
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .compact-stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .compact-stats-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;

    .mini-stat-card {
      padding: 8px;

      .mini-stat-value {
        font-size: 16px;
      }

      .mini-stat-label {
        font-size: 10px;
      }
    }
  }

  .compact-chart-container {
    height: 180px;
    padding: 8px;

    .compact-chart {
      height: 130px;
    }

    .chart-header {
      margin-bottom: 4px;

      .chart-title {
        font-size: 11px;
      }

      .chart-subtitle {
        font-size: 9px;
      }
    }
  }
}
</style>
