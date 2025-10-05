<template>
  <div class="dashboard-container">
    <!-- 顶部状态条 -->

    <!-- 现代化顶部统计栏 -->
    <div class="modern-stats-header">
      <StatusBar />
      <div class="stats-grid">
        <div class="stat-card primary">
          <div class="stat-icon">
            <MessageCircle class="icon" />
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ basicStats?.total_conversations || 0 }}</div>
            <div class="stat-label">总对话数</div>
            <div class="stat-trend" v-if="basicStats?.conversation_trend">
              <TrendingUp v-if="basicStats.conversation_trend > 0" class="trend-icon up" />
              <TrendingDown v-else-if="basicStats.conversation_trend < 0" class="trend-icon down" />
              <span class="trend-text">{{ Math.abs(basicStats.conversation_trend) }}%</span>
            </div>
          </div>
        </div>

        <div class="stat-card success">
          <div class="stat-icon">
            <Activity class="icon" />
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ basicStats?.active_conversations || 0 }}</div>
            <div class="stat-label">活跃对话</div>
          </div>
        </div>

        <div class="stat-card info">
          <div class="stat-icon">
            <Mail class="icon" />
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ basicStats?.total_messages || 0 }}</div>
            <div class="stat-label">总消息数</div>
          </div>
        </div>

        <div class="stat-card warning">
          <div class="stat-icon">
            <Users class="icon" />
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ basicStats?.total_users || 0 }}</div>
            <div class="stat-label">用户数</div>
          </div>
        </div>

        <div class="stat-card secondary">
          <div class="stat-icon">
            <BarChart3 class="icon" />
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ basicStats?.feedback_stats?.total_feedbacks || 0 }}</div>
            <div class="stat-label">总反馈数</div>
          </div>
        </div>

        <div class="stat-card" :class="getSatisfactionClass()">
          <div class="stat-icon">
            <Heart class="icon" />
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ basicStats?.feedback_stats?.satisfaction_rate || 0 }}%</div>
            <div class="stat-label">满意度</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Grid布局的主要内容区域 -->
    <div class="dashboard-grid">
      <!-- 调用统计模块 - 占据2x1网格（新增） -->
      <div class="grid-item call-stats">
        <a-card class="call-stats-section" title="调用统计" :loading="loading">
          <div class="placeholder-content">
            <div class="placeholder-icon">
              <BarChart3 class="icon" />
            </div>
            <div class="placeholder-text">调用统计模块</div>
            <div class="placeholder-subtitle">即将上线</div>
          </div>
        </a-card>
      </div>

      <!-- 用户活跃度分析 - 占据1x1网格 -->
      <div class="grid-item user-stats">
        <UserStatsComponent
          :user-stats="allStatsData?.users"
          :loading="loading"
          ref="userStatsRef"
        />
      </div>

      <!-- AI智能体分析 - 占据1x1网格 -->
      <div class="grid-item agent-stats">
        <AgentStatsComponent
          :agent-stats="allStatsData?.agents"
          :loading="loading"
          ref="agentStatsRef"
        />
      </div>

      <!-- 工具调用监控 - 占据1x1网格 -->
      <div class="grid-item tool-stats">
        <ToolStatsComponent
          :tool-stats="allStatsData?.tools"
          :loading="loading"
          ref="toolStatsRef"
        />
      </div>

      <!-- 知识库使用情况 - 占据1x1网格 -->
      <div class="grid-item knowledge-stats">
        <KnowledgeStatsComponent
          :knowledge-stats="allStatsData?.knowledge"
          :loading="loading"
          ref="knowledgeStatsRef"
        />
      </div>

      <!-- 对话记录 - 占据1x1网格 -->
      <div class="grid-item conversations">
        <a-card class="conversations-section" title="对话记录" :loading="loading">
          <template #extra>
            <a-space>
              <a-input
                v-model:value="filters.user_id"
                placeholder="用户ID"
                size="small"
                style="width: 120px"
                @change="handleFilterChange"
              />
              <a-select
                v-model:value="filters.status"
                placeholder="状态"
                size="small"
                style="width: 100px"
                @change="handleFilterChange"
              >
                <a-select-option value="active">活跃</a-select-option>
                <a-select-option value="deleted">已删除</a-select-option>
                <a-select-option value="all">全部</a-select-option>
              </a-select>
              <a-button size="small" @click="loadConversations" :loading="loading">
                刷新
              </a-button>
              <a-button size="small" type="primary" @click="showFeedbackList">
                反馈详情
              </a-button>
            </a-space>
          </template>

          <a-table
            :columns="conversationColumns"
            :data-source="conversations"
            :loading="loading"
            :pagination="conversationPagination"
            @change="handleTableChange"
            row-key="thread_id"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'title'">
                <a @click="handleViewDetail(record)" class="conversation-title">{{ record.title || '未命名对话' }}</a>
              </template>
              <template v-if="column.key === 'status'">
                <a-tag :color="record.status === 'active' ? 'green' : 'red'" size="small">
                  {{ record.status === 'active' ? '活跃' : '已删除' }}
                </a-tag>
              </template>
              <template v-if="column.key === 'updated_at'">
                <span class="time-text">{{ formatDate(record.updated_at) }}</span>
              </template>
              <template v-if="column.key === 'actions'">
                <a-button type="link" size="small" @click="handleViewDetail(record)">
                  详情
                </a-button>
              </template>
            </template>
          </a-table>
        </a-card>
      </div>
    </div>

    <!-- 反馈列表模态框 -->
    <a-modal
      v-model:open="feedbackModalVisible"
      title="用户反馈详情"
      width="1000px"
      :footer="null"
    >
      <a-space style="margin-bottom: 16px">
        <a-radio-group v-model:value="feedbackFilter" @change="loadFeedbacks">
          <a-radio-button value="all">全部</a-radio-button>
          <a-radio-button value="like">点赞</a-radio-button>
          <a-radio-button value="dislike">点踩</a-radio-button>
        </a-radio-group>
      </a-space>

      <a-table
        :columns="feedbackColumns"
        :data-source="feedbacks"
        :loading="loadingFeedbacks"
        :pagination="feedbackPagination"
        row-key="id"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'rating'">
            <a-tag :color="record.rating === 'like' ? 'green' : 'red'">
              <template #icon>
                <LikeOutlined v-if="record.rating === 'like'" />
                <DislikeOutlined v-else />
              </template>
              {{ record.rating === 'like' ? '点赞' : '点踩' }}
            </a-tag>
          </template>
          <template v-if="column.key === 'reason'">
            <span v-if="record.reason">{{ record.reason }}</span>
            <span v-else style="color: #999">-</span>
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatFullDate(record.created_at) }}
          </template>
        </template>
      </a-table>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import { LikeOutlined, DislikeOutlined } from '@ant-design/icons-vue'
import {
  MessageCircle,
  Activity,
  Mail,
  Users,
  BarChart3,
  Heart,
  TrendingUp,
  TrendingDown
} from 'lucide-vue-next'
import { dashboardApi } from '@/apis/dashboard_api'

// 导入子组件
import StatusBar from '@/components/StatusBar.vue'
import UserStatsComponent from '@/components/dashboard/UserStatsComponent.vue'
import ToolStatsComponent from '@/components/dashboard/ToolStatsComponent.vue'
import KnowledgeStatsComponent from '@/components/dashboard/KnowledgeStatsComponent.vue'
import AgentStatsComponent from '@/components/dashboard/AgentStatsComponent.vue'

// 统计数据 - 使用新的响应式结构
const basicStats = ref({})
const allStatsData = ref({
  users: null,
  tools: null,
  knowledge: null,
  agents: null
})

// 过滤器
const filters = reactive({
  user_id: '',
  agent_id: '',
  status: 'active',
})

// 对话列表
const conversations = ref([])
const loading = ref(false)

// 反馈相关
const feedbackModalVisible = ref(false)
const feedbacks = ref([])
const loadingFeedbacks = ref(false)
const feedbackFilter = ref('all')
const feedbackPagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
})

// 分页
const conversationPagination = reactive({
  current: 1,
  pageSize: 8,
  total: 0,
  showSizeChanger: false,
  showQuickJumper: false,
  showTotal: (total, range) => `${range[0]}-${range[1]} / ${total}`,
})

// 表格列定义
const conversationColumns = [
  {
    title: '对话标题',
    dataIndex: 'title',
    key: 'title',
    ellipsis: true,
  },
  {
    title: '用户',
    dataIndex: 'user_id',
    key: 'user_id',
    width: '80px',
    ellipsis: true,
  },
  {
    title: '消息数',
    dataIndex: 'message_count',
    key: 'message_count',
    width: '60px',
    align: 'center',
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: '70px',
    align: 'center',
  },
  {
    title: '更新时间',
    dataIndex: 'updated_at',
    key: 'updated_at',
    width: '120px',
  },
  {
    title: '操作',
    key: 'actions',
    width: '60px',
    align: 'center',
  },
]

// 反馈表格列定义
const feedbackColumns = [
  {
    title: '反馈类型',
    key: 'rating',
    width: '10%',
  },
  {
    title: '用户ID',
    dataIndex: 'user_id',
    key: 'user_id',
    width: '12%',
  },
  {
    title: '智能体ID',
    dataIndex: 'agent_id',
    key: 'agent_id',
    width: '12%',
  },
  {
    title: '对话标题',
    dataIndex: 'conversation_title',
    key: 'conversation_title',
    width: '15%',
  },
  {
    title: '消息内容',
    dataIndex: 'message_content',
    key: 'message_content',
    width: '25%',
  },
  {
    title: '反馈原因',
    key: 'reason',
    width: '16%',
  },
  {
    title: '时间',
    key: 'created_at',
    width: '10%',
  },
]

// 子组件引用
const userStatsRef = ref(null)
const toolStatsRef = ref(null)
const knowledgeStatsRef = ref(null)
const agentStatsRef = ref(null)

// 加载统计数据 - 使用并行API调用
const loadAllStats = async () => {
  loading.value = true
  try {
    // 使用并行API调用获取所有统计数据
    const response = await dashboardApi.getAllStats()

    // 更新基础统计数据
    basicStats.value = response.basic

    // 更新详细统计数据
    allStatsData.value = {
      users: response.users,
      tools: response.tools,
      knowledge: response.knowledge,
      agents: response.agents
    }

    console.log('Dashboard 数据加载完成:', response)
    message.success('数据加载成功')
  } catch (error) {
    console.error('加载统计数据失败:', error)
    message.error('加载统计数据失败')

    // 如果并行请求失败，尝试单独加载基础数据
    try {
      const basicResponse = await dashboardApi.getStats()
      basicStats.value = basicResponse
      message.warning('详细数据加载失败，仅显示基础统计')
    } catch (basicError) {
      console.error('加载基础统计数据也失败:', basicError)
      message.error('无法加载任何统计数据')
    }
  } finally {
    loading.value = false
  }
}

// 保留原有的loadStats函数以兼容旧代码
const loadStats = loadAllStats

// 加载对话列表
const loadConversations = async () => {
  try {
    const params = {
      user_id: filters.user_id || undefined,
      agent_id: filters.agent_id || undefined,
      status: filters.status,
      limit: conversationPagination.pageSize,
      offset: (conversationPagination.current - 1) * conversationPagination.pageSize,
    }

    const response = await dashboardApi.getConversations(params)
    conversations.value = response
    // Note: 由于后端没有返回总数，这里暂时设置为当前数据长度
    conversationPagination.total = response.length
  } catch (error) {
    console.error('加载对话列表失败:', error)
    message.error('加载对话列表失败')
  }
}

// 获取满意度等级样式
const getSatisfactionClass = () => {
  const rate = basicStats.value?.feedback_stats?.satisfaction_rate || 0
  if (rate >= 80) return 'high'
  if (rate >= 60) return 'medium'
  return 'low'
}

// 日期格式化
const formatDate = (dateString) => {
  if (!dateString) return '-'
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now - date
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } else if (diffDays === 1) {
    return '昨天'
  } else if (diffDays < 7) {
    return `${diffDays}天前`
  } else {
    return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
  }
}

// 查看对话详情
const handleViewDetail = async (record) => {
  try {
    loading.value = true
    const detail = await dashboardApi.getConversationDetail(record.thread_id)

    console.log('========================================')
    console.log('=== 数据库原始数据 ===')
    console.log('========================================')
    console.log('完整对话数据（JSON）:')
    console.log(JSON.stringify(detail, null, 2))
    console.log('\n')
    console.log('完整对话数据（对象）:')
    console.log(detail)
    console.log('========================================')

    message.success('数据库原始数据已输出到控制台')
  } catch (error) {
    console.error('获取对话详情失败:', error)
    message.error('获取对话详情失败')
  } finally {
    loading.value = false
  }
}

// 处理过滤器变化
const handleFilterChange = () => {
  pagination.current = 1
  loadConversations()
}

// 处理表格变化
const handleTableChange = (pag) => {
  conversationPagination.current = pag.current
  conversationPagination.pageSize = pag.pageSize
  loadConversations()
}

// 格式化完整日期
const formatFullDate = (dateString) => {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// 显示反馈列表
const showFeedbackList = () => {
  feedbackModalVisible.value = true
  loadFeedbacks()
}

// 加载反馈列表
const loadFeedbacks = async () => {
  loadingFeedbacks.value = true
  try {
    const params = {
      rating: feedbackFilter.value === 'all' ? undefined : feedbackFilter.value,
      limit: feedbackPagination.pageSize,
      offset: (feedbackPagination.current - 1) * feedbackPagination.pageSize,
    }

    const response = await dashboardApi.getFeedbacks(params)
    feedbacks.value = response
  } catch (error) {
    console.error('加载反馈列表失败:', error)
    message.error('加载反馈列表失败')
  } finally {
    loadingFeedbacks.value = false
  }
}

// 清理函数 - 清理所有子组件的图表实例
const cleanupCharts = () => {
  if (userStatsRef.value?.cleanup) userStatsRef.value.cleanup()
  if (toolStatsRef.value?.cleanup) toolStatsRef.value.cleanup()
  if (knowledgeStatsRef.value?.cleanup) knowledgeStatsRef.value.cleanup()
  if (agentStatsRef.value?.cleanup) agentStatsRef.value.cleanup()
}

// 初始化
onMounted(() => {
  loadAllStats()
  loadConversations()
})

// 组件卸载时清理图表
onUnmounted(() => {
  cleanupCharts()
})
</script>

<style scoped lang="less">
@import '@/assets/css/dashboard.css';

.dashboard-container {
  // padding: 0 24px 24px 24px;
  background-color: var(--gray-25);
  min-height: calc(100vh - 64px);
  overflow-x: hidden;
}

// Dashboard 特有的统计栏样式
.modern-stats-header {
  margin-top: 8px;

  .stats-grid {
    display: grid;
    padding: 16px;
    grid-template-columns: repeat(6, 1fr);
    gap: 16px;

    .stat-card {
      background: var(--gray-0);
      border-radius: 8px;
      padding: 20px;
      border: 1px solid var(--gray-200);
      transition: all 0.2s ease;
      display: flex;
      flex-direction: row;
      align-items: center;
      text-align: left;
      min-height: 80px;
      justify-content: flex-start;

      &:hover {
        border-color: var(--gray-300);
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
      }

      &.primary {
        .stat-icon {
          background-color: #eff6ff;
          color: #2563eb;
        }
      }

      &.success {
        .stat-icon {
          background-color: #f0fdf4;
          color: #16a34a;
        }
      }

      &.info {
        .stat-icon {
          background-color: #f0f9ff;
          color: #0284c7;
        }
      }

      &.warning {
        .stat-icon {
          background-color: #fffbeb;
          color: #d97706;
        }
      }

      &.secondary {
        .stat-icon {
          background-color: #faf5ff;
          color: #9333ea;
        }
      }

      &.satisfaction-high {
        .stat-icon {
          background-color: #f0fdf4;
          color: #16a34a;
        }
      }

      &.satisfaction-medium {
        .stat-icon {
          background-color: #fffbeb;
          color: #d97706;
        }
      }

      &.satisfaction-low {
        .stat-icon {
          background-color: #fef2f2;
          color: #dc2626;
        }
      }

      .stat-icon {
        width: 44px;
        height: 44px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-right: 16px;
        flex-shrink: 0;

        .icon {
          width: 20px;
          height: 20px;
        }
      }

      .stat-content {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: flex-start;

        .stat-value {
          font-size: 24px;
          font-weight: 700;
          color: var(--gray-1000);
          line-height: 1.1;
          margin-bottom: 4px;
        }

        .stat-label {
          font-size: 13px;
          color: var(--gray-600);
          font-weight: 500;
          margin-bottom: 8px;
        }

        .stat-trend {
          display: flex;
          align-items: center;
          gap: 4px;
          margin-top: 4px;

          .trend-icon {
            width: 14px;
            height: 14px;

            &.up {
              color: #16a34a;
            }

            &.down {
              color: #dc2626;
            }
          }

          .trend-text {
            font-size: 12px;
            font-weight: 500;
            color: var(--gray-600);
          }
        }
      }
    }
  }
}


// Dashboard 特有的网格布局
.dashboard-grid {
  display: grid;
  padding: 16px;
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: auto auto;
  gap: 16px;
  margin-bottom: 24px;
  min-height: 600px;

  .grid-item {
    border-radius: 8px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    min-height: 300px;
    background-color: transparent;
    border: none;
    transition: all 0.2s ease;

    &:hover {
      .conversations-section,
      .call-stats-section {
        border-color: var(--gray-300);
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
      }
    }

    // 大页面布局：第一行 2x1 + 1x1，第二行 3x1x1
    &.call-stats {
      grid-column: 1 / 3;
      grid-row: 1 / 2;
      min-height: 400px;
    }

    &.user-stats {
      grid-column: 3 / 4;
      grid-row: 1 / 2;
      min-height: 400px;
    }

    &.agent-stats {
      grid-column: 1 / 2;
      grid-row: 2 / 3;
      min-height: 350px;
    }

    &.tool-stats {
      grid-column: 2 / 3;
      grid-row: 2 / 3;
      min-height: 350px;
    }

    &.knowledge-stats {
      grid-column: 3 / 4;
      grid-row: 2 / 3;
      min-height: 350px;
    }

    &.conversations {
      grid-column: 1 / 4;
      grid-row: 3 / 4;
      min-height: 300px;
    }
  }
}

// Dashboard 特有的卡片样式
.conversations-section,
.call-stats-section {
  background-color: var(--gray-0);
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  transition: all 0.2s ease;
  box-shadow: none;

  &:hover {
    background-color: var(--gray-25);
    border-color: var(--gray-300);
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
  }

  :deep(.ant-card-head) {
    border-bottom: 1px solid var(--gray-200);
    min-height: 56px;
    padding: 0 20px;
    background-color: var(--gray-0);

    .ant-card-head-title {
      font-size: 16px;
      font-weight: 600;
      color: var(--gray-1000);
    }
  }

  :deep(.ant-card-body) {
    padding: 16px 20px;
    background-color: var(--gray-0);
  }

  :deep(.ant-card-extra) {
    .ant-space {
      gap: 8px;
    }
  }
}

// Dashboard 特有的占位符样式
.placeholder-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--gray-600);

  .placeholder-icon {
    width: 64px;
    height: 64px;
    background-color: var(--gray-100);
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 16px;

    .icon {
      width: 32px;
      height: 32px;
      color: var(--gray-500);
    }
  }

  .placeholder-text {
    font-size: 18px;
    font-weight: 600;
    color: var(--gray-800);
    margin-bottom: 8px;
  }

  .placeholder-subtitle {
    font-size: 14px;
    color: var(--gray-600);
  }
}

// Dashboard 特有的对话记录样式
.conversations-section {
  .conversation-title {
    color: var(--main-500);
    text-decoration: none;
    font-weight: 500;
    font-size: 13px;
    transition: color 0.2s ease;

    &:hover {
      color: var(--main-600);
      text-decoration: underline;
    }
  }

  .time-text {
    color: var(--gray-600);
    font-size: 12px;
  }
}

// Dashboard 特有的响应式设计
@media (max-width: 1200px) {
  .modern-stats-header {
    .stats-grid {
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }
  }

  .dashboard-grid {
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto auto auto;
    gap: 16px;

    .grid-item {
      // 小页面布局：第一行 2x1，第二行和第三行各是 2x1x1
      &.call-stats {
        grid-column: 1 / 3;
        grid-row: 1 / 2;
        min-height: 350px;
      }

      &.user-stats {
        grid-column: 1 / 2;
        grid-row: 2 / 3;
        min-height: 300px;
      }

      &.agent-stats {
        grid-column: 2 / 3;
        grid-row: 2 / 3;
        min-height: 300px;
      }

      &.tool-stats {
        grid-column: 1 / 2;
        grid-row: 3 / 4;
        min-height: 300px;
      }

      &.knowledge-stats {
        grid-column: 2 / 3;
        grid-row: 3 / 4;
        min-height: 300px;
      }

      &.conversations {
        grid-column: 1 / 3;
        grid-row: 4 / 5;
        min-height: 300px;
      }
    }
  }
}

@media (max-width: 768px) {
  .dashboard-container {
    padding: 16px;
  }

  .modern-stats-header {
    .stats-grid {
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }

    .stat-card {
      padding: 16px;
      min-height: 80px;

      .stat-icon {
        width: 36px;
        height: 36px;
        margin-right: 12px;

        .icon {
          width: 18px;
          height: 18px;
        }
      }

      .stat-content {
        .stat-value {
          font-size: 20px;
        }

        .stat-label {
          font-size: 12px;
        }
      }
    }
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
    gap: 12px;

    .grid-item {
      &.call-stats,
      &.agent-stats,
      &.user-stats,
      &.tool-stats,
      &.knowledge-stats,
      &.conversations {
        grid-column: 1 / 2;
        grid-row: auto;
        min-height: 300px;
      }
    }
  }

  .placeholder-content {
    height: 150px;

    .placeholder-icon {
      width: 48px;
      height: 48px;
      margin-bottom: 12px;

      .icon {
        width: 24px;
        height: 24px;
      }
    }

    .placeholder-text {
      font-size: 16px;
    }

    .placeholder-subtitle {
      font-size: 12px;
    }
  }
}
</style>


