<template>
  <div class="dashboard-container">
    <!-- 统计卡片区域 -->
    <div class="stats-section">
      <a-card class="stat-card" :loading="loading">
        <a-statistic title="总对话数" :value="stats.total_conversations" />
      </a-card>
      <a-card class="stat-card" :loading="loading">
        <a-statistic title="活跃对话" :value="stats.active_conversations" />
      </a-card>
      <a-card class="stat-card" :loading="loading">
        <a-statistic title="总消息数" :value="stats.total_messages" />
      </a-card>
      <a-card class="stat-card" :loading="loading">
        <a-statistic title="用户数" :value="stats.total_users" />
      </a-card>
    </div>

    <!-- 用户反馈统计区域 -->
    <a-card class="feedback-section" title="用户反馈统计" :loading="loading">
      <a-row :gutter="16">
        <a-col :span="6">
          <a-statistic
            title="总反馈数"
            :value="stats.feedback_stats?.total_feedbacks || 0"
          />
        </a-col>
        <a-col :span="6">
          <a-statistic
            title="点赞数"
            :value="stats.feedback_stats?.like_count || 0"
            :value-style="{ color: '#3f8600' }"
          >
            <template #prefix>
              <LikeOutlined />
            </template>
          </a-statistic>
        </a-col>
        <a-col :span="6">
          <a-statistic
            title="点踩数"
            :value="stats.feedback_stats?.dislike_count || 0"
            :value-style="{ color: '#cf1322' }"
          >
            <template #prefix>
              <DislikeOutlined />
            </template>
          </a-statistic>
        </a-col>
        <a-col :span="6">
          <a-statistic
            title="满意度"
            :value="stats.feedback_stats?.satisfaction_rate || 0"
            suffix="%"
            :value-style="{ color: stats.feedback_stats?.satisfaction_rate >= 80 ? '#3f8600' : stats.feedback_stats?.satisfaction_rate >= 60 ? '#fa8c16' : '#cf1322' }"
          />
        </a-col>
      </a-row>
      <a-divider />
      <a-button type="primary" @click="showFeedbackList">查看反馈详情</a-button>
    </a-card>

    <!-- 过滤器区域 -->
    <a-card class="filter-section" title="筛选条件">
      <a-row :gutter="16">
        <a-col :span="6">
          <a-input
            v-model:value="filters.user_id"
            placeholder="用户ID"
            allow-clear
            @change="handleFilterChange"
          />
        </a-col>
        <a-col :span="6">
          <a-input
            v-model:value="filters.agent_id"
            placeholder="智能体ID"
            allow-clear
            @change="handleFilterChange"
          />
        </a-col>
        <a-col :span="6">
          <a-select
            v-model:value="filters.status"
            placeholder="状态"
            style="width: 100%"
            @change="handleFilterChange"
          >
            <a-select-option value="active">活跃</a-select-option>
            <a-select-option value="deleted">已删除</a-select-option>
            <a-select-option value="all">全部</a-select-option>
          </a-select>
        </a-col>
        <a-col :span="6">
          <a-button type="primary" @click="loadConversations" :loading="loading">
            刷新
          </a-button>
        </a-col>
      </a-row>
    </a-card>

    <!-- 对话列表区域 -->
    <a-card class="conversations-section" title="对话记录">
      <a-table
        :columns="columns"
        :data-source="conversations"
        :loading="loading"
        :pagination="pagination"
        @change="handleTableChange"
        row-key="thread_id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'title'">
            <a @click="handleViewDetail(record)">{{ record.title }}</a>
          </template>
          <template v-if="column.key === 'status'">
            <a-tag :color="record.status === 'active' ? 'green' : 'red'">
              {{ record.status }}
            </a-tag>
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>
          <template v-if="column.key === 'updated_at'">
            {{ formatDate(record.updated_at) }}
          </template>
          <template v-if="column.key === 'actions'">
            <a-button type="link" size="small" @click="handleViewDetail(record)">
              查看详情
            </a-button>
          </template>
        </template>
      </a-table>
    </a-card>

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
            {{ formatDate(record.created_at) }}
          </template>
        </template>
      </a-table>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { LikeOutlined, DislikeOutlined } from '@ant-design/icons-vue'
import { dashboardApi } from '@/apis/dashboard_api'

// 统计数据
const stats = reactive({
  total_conversations: 0,
  active_conversations: 0,
  total_messages: 0,
  total_users: 0,
  feedback_stats: {
    total_feedbacks: 0,
    like_count: 0,
    dislike_count: 0,
    satisfaction_rate: 0,
    recent_feedbacks_24h: 0,
  },
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
const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showQuickJumper: true,
  pageSizeOptions: ['10', '20', '50', '100'],
})

// 表格列定义
const columns = [
  {
    title: '标题',
    dataIndex: 'title',
    key: 'title',
    width: '20%',
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
    title: '消息数',
    dataIndex: 'message_count',
    key: 'message_count',
    width: '8%',
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: '8%',
  },
  {
    title: '创建时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: '15%',
  },
  {
    title: '更新时间',
    dataIndex: 'updated_at',
    key: 'updated_at',
    width: '15%',
  },
  {
    title: '操作',
    key: 'actions',
    width: '10%',
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

// 加载统计数据
const loadStats = async () => {
  try {
    const response = await dashboardApi.getStats()
    Object.assign(stats, response)
  } catch (error) {
    console.error('加载统计数据失败:', error)
    message.error('加载统计数据失败')
  }
}

// 加载对话列表
const loadConversations = async () => {
  loading.value = true
  try {
    const params = {
      user_id: filters.user_id || undefined,
      agent_id: filters.agent_id || undefined,
      status: filters.status,
      limit: pagination.pageSize,
      offset: (pagination.current - 1) * pagination.pageSize,
    }

    const response = await dashboardApi.getConversations(params)
    conversations.value = response
    // Note: 由于后端没有返回总数，这里暂时设置为当前数据长度
    // 如果需要精确分页，需要后端返回 total count
  } catch (error) {
    console.error('加载对话列表失败:', error)
    message.error('加载对话列表失败')
  } finally {
    loading.value = false
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
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  loadConversations()
}

// 格式化日期
const formatDate = (dateString) => {
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

// 初始化
onMounted(() => {
  loadStats()
  loadConversations()
})
</script>

<style scoped lang="less">
.dashboard-container {
  padding: 24px;
  background-color: var(--bg-color);
  min-height: calc(100vh - 64px);
}

.stats-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background-color: var(--card-bg-color);
  border-radius: 8px;
  transition: all 0.3s ease;

  &:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }
}

.filter-section {
  margin-bottom: 24px;
  background-color: var(--card-bg-color);
  border-radius: 8px;
}

.feedback-section {
  margin-bottom: 24px;
  background-color: var(--card-bg-color);
  border-radius: 8px;
}

.conversations-section {
  background-color: var(--card-bg-color);
  border-radius: 8px;
}

:deep(.ant-table) {
  background-color: transparent;
}

:deep(.ant-table-thead > tr > th) {
  background-color: var(--hover-bg-color);
  border-bottom: 1px solid var(--border-color);
}

:deep(.ant-table-tbody > tr > td) {
  border-bottom: 1px solid var(--border-color);
}

:deep(.ant-table-tbody > tr:hover > td) {
  background-color: var(--hover-bg-color);
}
</style>

