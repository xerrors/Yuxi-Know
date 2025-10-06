<template>
  <a-card title="AI智能体分析" :loading="loading" class="dashboard-card">
    <!-- 智能体概览 -->
    <div class="stats-overview">
      <a-row :gutter="16">
        <a-col :span="6">
          <a-statistic
            title="智能体总数"
            :value="agentStats?.total_agents || 0"
            :value-style="{ color: 'var(--chart-info)' }"
            suffix="个"
          />
        </a-col>
        <a-col :span="6">
          <a-statistic
            title="平均满意度"
            :value="averageSatisfaction"
            suffix="%"
            :value-style="{
              color: averageSatisfaction >= 80 ? 'var(--chart-success)' :
                     averageSatisfaction >= 60 ? 'var(--chart-warning)' : 'var(--chart-error)'
            }"
          />
        </a-col>
        <a-col :span="6">
          <a-statistic
            title="总对话数"
            :value="totalConversations"
            :value-style="{ color: 'var(--chart-secondary)' }"
            suffix="次"
          />
        </a-col>
        <a-col :span="6">
          <a-statistic
            title="工具调用总数"
            :value="totalToolUsage"
            :value-style="{ color: 'var(--chart-warning)' }"
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
          <h4>智能体对话数与工具调用数分布</h4>
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
          <template v-if="column.key === 'score'">
            <a-progress
              :percent="record.score"
              size="small"
              :stroke-color="getScoreColor(record.score)"
              :show-info="true"
              :format="(percent) => `${percent}分`"
            />
          </template>
          <template v-if="column.key === 'satisfaction_rate'">
            <a-statistic
              :value="record.satisfaction_rate"
              suffix="%"
              :value-style="{
                color: record.satisfaction_rate >= 80 ? 'var(--chart-success)' :
                       record.satisfaction_rate >= 60 ? 'var(--chart-warning)' : 'var(--chart-error)',
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
    width: '25%'
  },
  {
    title: '综合评分',
    key: 'score',
    width: '20%'
  },
  {
    title: '满意度',
    key: 'satisfaction_rate',
    width: '20%',
    align: 'center'
  },
  {
    title: '对话数',
    key: 'conversation_count',
    width: '15%',
    align: 'center'
  }
]

// 计算属性
const averageSatisfaction = computed(() => {
  const satisfactionRates = props.agentStats?.agent_satisfaction_rates || []
  if (satisfactionRates.length === 0) return 0

  const total = satisfactionRates.reduce((sum, item) => sum + item.satisfaction_rate, 0)
  return Math.round(total / satisfactionRates.length)
})

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

// 颜色辅助函数
const getScoreColor = (score) => {
  if (score >= 80) return '#3996ae'
  if (score >= 60) return '#82c3d6'
  return '#a3d8e8'
}


// 初始化对话数和工具调用数合并图表
const initConversationToolChart = () => {
  if (!conversationToolChartRef.value ||
      (!props.agentStats?.agent_conversation_counts?.length &&
       !props.agentStats?.agent_tool_usage?.length)) return

  conversationToolChart = echarts.init(conversationToolChartRef.value)

  const conversationData = props.agentStats.agent_conversation_counts || []
  const toolData = props.agentStats.agent_tool_usage || []

  // 获取所有智能体ID
  const allAgentIds = [...new Set([
    ...conversationData.map(item => item.agent_id),
    ...toolData.map(item => item.agent_id)
  ])]

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
    legend: {
      data: ['对话数', '工具调用数'],
      top: '5%',
      textStyle: {
        color: '#666'
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: allAgentIds,
      axisLine: {
        lineStyle: {
          color: '#e8e8e8'
        }
      },
      axisLabel: {
        color: '#666',
        interval: 0,
        rotate: 45
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
    series: [
      {
        name: '对话数',
        type: 'bar',
        data: allAgentIds.map(agentId => {
          const item = conversationData.find(d => d.agent_id === agentId)
          return item ? item.conversation_count : 0
        }),
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [{
              offset: 0, color: '#3996ae'
            }, {
              offset: 1, color: '#5faec2'
            }]
          },
          borderRadius: [4, 4, 0, 0]
        },
        emphasis: {
          itemStyle: {
            color: '#24839a',
            shadowBlur: 10,
            shadowColor: 'rgba(57, 150, 174, 0.3)'
          }
        }
      },
      {
        name: '工具调用数',
        type: 'bar',
        data: allAgentIds.map(agentId => {
          const item = toolData.find(d => d.agent_id === agentId)
          return item ? item.tool_usage_count : 0
        }),
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [{
              offset: 0, color: '#82c3d6'
            }, {
              offset: 1, color: '#a3d8e8'
            }]
          },
          borderRadius: [4, 4, 0, 0]
        },
        emphasis: {
          itemStyle: {
            color: '#5faec2',
            shadowBlur: 10,
            shadowColor: 'rgba(130, 195, 214, 0.3)'
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
watch(() => props.agentStats, () => {
  updateCharts()
}, { deep: true })

// 窗口大小变化时重新调整图表
const handleResize = () => {
  if (conversationToolChart) conversationToolChart.resize()
}

onMounted(() => {
  updateCharts()
  window.addEventListener('resize', handleResize)
})

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
@import '@/assets/css/dashboard.css';

// AgentStatsComponent 特有的样式
.top-performers, .metrics-comparison {
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
</style>