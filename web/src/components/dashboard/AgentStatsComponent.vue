<template>
  <a-card title="AI智能体分析" :loading="loading" class="dashboard-card">
    <!-- 智能体概览 -->
    <div class="stats-overview">
      <a-row :gutter="16">
        <a-col :span="8">
          <a-statistic
            title="智能体总数"
            :value="agentStats?.total_agents || 0"
            :value-style="{ color: 'var(--color-info-500)' }"
            suffix="个"
          />
        </a-col>
        <a-col :span="8">
          <a-statistic
            title="总对话数"
            :value="totalConversations"
            :value-style="{ color: 'var(--color-accent-500)' }"
            suffix="次"
          />
        </a-col>
        <a-col :span="8">
          <a-statistic
            title="工具调用总数"
            :value="totalToolUsage"
            :value-style="{ color: 'var(--color-warning-500)' }"
            suffix="次"
          />
        </a-col>
      </a-row>
    </div>

    <a-divider />

    <!-- 图表区域 -->
    <a-row :gutter="24">
      <!-- 对话数和工具调用数分布 -->
      <a-col :span="24">
        <div class="chart-container">
          <h4>对话/工具调用分布 (TOP 3)</h4>
          <div ref="conversationToolChartRef" class="chart"></div>
        </div>
      </a-col>
    </a-row>

    <!-- 表现排行榜 -->
    <a-divider />
    <div class="top-performers">
      <h4>表现最佳智能体 TOP 5</h4>
      <a-table
        :columns="performerColumns"
        :data-source="topPerformers"
        size="small"
        :pagination="false"
      >
        <template #bodyCell="{ column, record, index }">
          <template v-if="column.key === 'rank'">
            <div class="rank-display">
              <span v-if="index < 3" class="rank-medal">
                {{ index === 0 ? '🥇' : index === 1 ? '🥈' : '🥉' }}
              </span>
              <span v-else class="rank-number">{{ index + 1 }}</span>
            </div>
          </template>
          <template v-if="column.key === 'agent_id'">
            <a-tag color="blue">{{ record.agent_id }}</a-tag>
          </template>
          <template v-if="column.key === 'satisfaction_rate'">
            <a-statistic
              :value="record.satisfaction_rate"
              suffix="%"
              :value-style="{
                color:
                  record.satisfaction_rate >= 80
                    ? 'var(--color-success-500)'
                    : record.satisfaction_rate >= 60
                      ? 'var(--color-warning-500)'
                      : 'var(--color-error-500)',
                fontSize: '14px'
              }"
            />
          </template>
          <template v-if="column.key === 'conversation_count'">
            <span class="metric-value">{{ record.conversation_count }}</span>
          </template>
        </template>
      </a-table>
    </div>
  </a-card>
</template>

<script setup>
import { ref, onMounted, watch, nextTick, computed } from 'vue'
import * as echarts from 'echarts'
import { getColorByIndex } from '@/utils/chartColors'
import { useThemeStore } from '@/stores/theme'

// CSS 变量解析工具函数
function getCSSVariable(variableName, element = document.documentElement) {
  return getComputedStyle(element).getPropertyValue(variableName).trim()
}

// theme store
const themeStore = useThemeStore()

// Props
const props = defineProps({
  agentStats: {
    type: Object,
    default: () => ({})
  },
  loading: {
    type: Boolean,
    default: false
  }
})

// Chart refs
const conversationToolChartRef = ref(null)
let conversationToolChart = null

// 表格列定义
const performerColumns = [
  {
    title: '排名',
    key: 'rank',
    width: '80px',
    align: 'center'
  },
  {
    title: '智能体ID',
    key: 'agent_id',
    width: '30%'
  },
  {
    title: '满意度',
    key: 'satisfaction_rate',
    width: '25%',
    align: 'center'
  },
  {
    title: '对话数',
    key: 'conversation_count',
    width: '20%',
    align: 'center'
  }
]

// 计算属性
const totalConversations = computed(() => {
  const conversationCounts = props.agentStats?.agent_conversation_counts || []
  return conversationCounts.reduce((sum, item) => sum + item.conversation_count, 0)
})

const totalToolUsage = computed(() => {
  const toolUsage = props.agentStats?.agent_tool_usage || []
  return toolUsage.reduce((sum, item) => sum + item.tool_usage_count, 0)
})

const topPerformers = computed(() => {
  return props.agentStats?.top_performing_agents || []
})

// 初始化对话数和工具调用数合并图表
const initConversationToolChart = () => {
  if (
    !conversationToolChartRef.value ||
    (!props.agentStats?.agent_conversation_counts?.length &&
      !props.agentStats?.agent_tool_usage?.length)
  )
    return

  // 如果已存在图表实例，先销毁
  if (conversationToolChart) {
    conversationToolChart.dispose()
    conversationToolChart = null
  }

  conversationToolChart = echarts.init(conversationToolChartRef.value)

  const conversationData = props.agentStats.agent_conversation_counts || []
  const toolData = props.agentStats.agent_tool_usage || []

  // 获取所有智能体ID并按对话数+工具调用数排序，取前3个
  const allAgentStats = {}

  // 统计每个智能体的总数据量（对话数 + 工具调用数）
  conversationData.forEach((item) => {
    if (!allAgentStats[item.agent_id]) {
      allAgentStats[item.agent_id] = { conversation: 0, tool: 0, total: 0 }
    }
    allAgentStats[item.agent_id].conversation = item.conversation_count
    allAgentStats[item.agent_id].total += item.conversation_count
  })

  toolData.forEach((item) => {
    if (!allAgentStats[item.agent_id]) {
      allAgentStats[item.agent_id] = { conversation: 0, tool: 0, total: 0 }
    }
    allAgentStats[item.agent_id].tool = item.tool_usage_count
    allAgentStats[item.agent_id].total += item.tool_usage_count
  })

  // 按总数据量降序排序，取前3个
  const topAgentIds = Object.entries(allAgentStats)
    .sort(([, a], [, b]) => b.total - a.total)
    .slice(0, 3)
    .map(([agentId]) => agentId)

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
    legend: {
      data: ['对话数', '工具调用数'],
      right: '0%',
      top: '0%',
      orient: 'horizontal',
      textStyle: {
        color: getCSSVariable('--gray-500')
      }
    },
    grid: {
      left: '3%',
      right: '15%',
      bottom: '3%',
      top: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: topAgentIds,
      axisLine: {
        lineStyle: {
          color: getCSSVariable('--gray-200')
        }
      },
      axisLabel: {
        color: getCSSVariable('--gray-500'),
        interval: 0
        // rotate: 45
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
          color: getCSSVariable('--gray-150')
        }
      }
    },
    series: [
      {
        name: '对话数',
        type: 'bar',
        data: topAgentIds.map((agentId) => {
          const item = conversationData.find((d) => d.agent_id === agentId)
          return item ? item.conversation_count : 0
        }),
        itemStyle: {
          color: getColorByIndex(0),
          borderRadius: [4, 4, 0, 0]
        },
        emphasis: {
          itemStyle: {
            color: getColorByIndex(0),
            shadowBlur: 10,
            shadowColor: getCSSVariable('--color-info-50')
          }
        }
      },
      {
        name: '工具调用数',
        type: 'bar',
        data: topAgentIds.map((agentId) => {
          const item = toolData.find((d) => d.agent_id === agentId)
          return item ? item.tool_usage_count : 0
        }),
        itemStyle: {
          color: getColorByIndex(1),
          borderRadius: [4, 4, 0, 0]
        },
        emphasis: {
          itemStyle: {
            color: getColorByIndex(1),
            shadowBlur: 10,
            shadowColor: getCSSVariable('--color-info-50')
          }
        }
      }
    ]
  }

  conversationToolChart.setOption(option)
}

// 更新图表
const updateCharts = () => {
  nextTick(() => {
    initConversationToolChart()
  })
}

// 监听数据变化
watch(
  () => props.agentStats,
  () => {
    updateCharts()
  },
  { deep: true }
)

// 窗口大小变化时重新调整图表
const handleResize = () => {
  if (conversationToolChart) conversationToolChart.resize()
}

onMounted(() => {
  updateCharts()
  window.addEventListener('resize', handleResize)
})

// 监听主题变化，重新渲染图表
watch(
  () => themeStore.isDark,
  () => {
    if (props.agentStats && conversationToolChart) {
      nextTick(() => {
        updateCharts()
      })
    }
  }
)

// 组件卸载时清理
const cleanup = () => {
  window.removeEventListener('resize', handleResize)
  if (conversationToolChart) {
    conversationToolChart.dispose()
    conversationToolChart = null
  }
}

// 导出清理函数供父组件调用
defineExpose({
  cleanup
})
</script>

<style scoped lang="less">
/* 指标值样式 */
.metric-value {
  font-weight: 500;
  color: var(--gray-1000);
  font-size: 14px;
}

/* 排名显示样式 */
.rank-display {
  display: flex;
  align-items: center;
  justify-content: center;

  .rank-medal {
    font-size: 20px;
  }

  .rank-number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    background-color: var(--gray-100);
    border-radius: 50%;
    font-size: 12px;
    font-weight: 600;
    color: var(--gray-600);
    border: 1px solid var(--gray-200);
  }
}

// AgentStatsComponent 特有的样式
.top-performers,
.metrics-comparison {
  h4 {
    margin-bottom: 16px;
    font-weight: 600;
    color: var(--gray-1000);
    font-size: 16px;
  }

  h5 {
    margin-bottom: 12px;
    color: var(--gray-600);
    font-weight: 500;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
}

:deep(.ant-progress-bg) {
  transition: all 0.3s ease;
}

:deep(.ant-statistic-content-value) {
  font-weight: bold !important;
}
</style>
