<template>
  <!-- 反馈列表模态框 -->
  <a-modal
    v-model:open="modalVisible"
    title="用户反馈详情"
    width="1200px"
    :footer="null"
  >
      <a-space style="margin-bottom: 16px">
        <a-segmented
          v-model:value="feedbackFilter"
          :options="feedbackOptions"
          @change="loadFeedbacks"
        />
      </a-space>

      <!-- 卡片列表 -->
      <div v-if="loadingFeedbacks" class="loading-container">
        <a-spin size="large" />
      </div>

      <div v-else class="feedback-cards-container">
        <div
          v-for="feedback in feedbacks"
          :key="feedback.id"
          class="feedback-card"
        >
          <!-- 卡片头部：用户信息和反馈类型 -->
          <div class="card-header">
            <div class="user-info">
              <a-avatar
                :src="feedback.avatar"
                :size="32"
                class="user-avatar"
              >
                {{ feedback.username ? feedback.username.charAt(0).toUpperCase() : 'U' }}
              </a-avatar>
              <div class="user-details">
                <div class="username">{{ feedback.username || '未知用户' }}</div>
              </div>
            </div>
            <a-tag :color="feedback.rating === 'like' ? 'green' : 'red'" class="rating-tag" size="small">
              <template #icon>
                <LikeOutlined v-if="feedback.rating === 'like'" />
                <DislikeOutlined v-else />
              </template>
              {{ feedback.rating === 'like' ? '点赞' : '点踩' }}
            </a-tag>
          </div>

          <!-- 卡片内容：消息内容和对话信息 -->
          <div class="card-content">
            <div class="message-section">
              <div class="message-content">{{ feedback.message_content }}</div>
            </div>

            <div class="conversation-section">
              <div class="conversation-info">
                <div class="info-item">
                  <span class="label">智能体:</span>
                  <span class="value">{{ feedback.agent_id }}</span>
                </div>
                <div class="info-item" v-if="feedback.conversation_title">
                  <span class="label">对话:</span>
                  <span class="value">{{ feedback.conversation_title }}</span>
                </div>
              </div>
            </div>

            <!-- 反馈原因 -->
            <div v-if="feedback.reason" class="reason-section">
              <div class="reason-content">{{ feedback.reason }}</div>
            </div>
          </div>

          <!-- 卡片底部：时间信息 -->
          <div class="card-footer">
            <div class="time-info">
              <ClockCircleOutlined />
              <span>{{ formatFullDate(feedback.created_at) }}</span>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="feedbacks.length === 0" class="empty-state">
          <a-empty description="暂无反馈数据" />
        </div>
      </div>

    </a-modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { LikeOutlined, DislikeOutlined, ClockCircleOutlined } from '@ant-design/icons-vue'
import { dashboardApi } from '@/apis/dashboard_api'
import { formatFullDateTime } from '@/utils/time'

// Props
const props = defineProps({
  agentId: {
    type: String,
    default: null
  }
})

// 模态框状态
const modalVisible = ref(false)

// 反馈相关数据
const feedbacks = ref([])
const loadingFeedbacks = ref(false)
const feedbackFilter = ref('all')
const feedbackOptions = [
  { label: '全部', value: 'all' },
  { label: '点赞', value: 'like' },
  { label: '点踩', value: 'dislike' }
]

// 显示模态框
const show = () => {
  modalVisible.value = true
  loadFeedbacks()
}

// 暴露方法给父组件
defineExpose({ show })

// 加载反馈列表
const loadFeedbacks = async () => {
  loadingFeedbacks.value = true
  try {
    const params = {
      rating: feedbackFilter.value === 'all' ? undefined : feedbackFilter.value,
      agent_id: props.agentId || undefined,
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

// 格式化完整日期
const formatFullDate = (dateString) => formatFullDateTime(dateString)

// 监听 agentId 变化，重新加载数据
watch(() => props.agentId, () => {
  if (modalVisible.value) {
    loadFeedbacks()
  }
})
</script>

<style scoped lang="less">
// 加载状态
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px 0;
}

// 卡片容器 - 自适应多列布局
.feedback-cards-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  max-height: 600px;
  overflow-y: auto;
  padding-right: 8px;

  // 滚动条样式
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb {
    background: #c1c1c1;
    border-radius: 3px;

    &:hover {
      background: #a8a8a8;
    }
  }
}

// 反馈卡片 - 紧凑设计
.feedback-card {
  background: white;
  border: 1px solid var(--gray-100);
  border-radius: 8px;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;

  &:hover {
    border-color: var(--main-color);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
}

// 卡片头部 - 紧凑
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--gray-100);
  background: #fafafa;
  border-radius: 8px 8px 0 0;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-avatar {
  flex-shrink: 0;
}

.user-details {
  .username {
    font-weight: 500;
    color: var(--gray-900);
    font-size: 13px;
    line-height: 1.2;
  }
}

.rating-tag {
  font-weight: 500;
  font-size: 11px;
}

// 卡片内容 - 紧凑
.card-content {
  padding: 16px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message-section {
  flex: 1;
}

.message-content {
  background: #f8f9fa;
  padding: 10px;
  border-radius: 6px;
  // border-left: 3px solid var(--main-color);
  font-size: 13px;
  line-height: 1.4;
  color: var(--gray-800);
  word-break: break-word;
}

.conversation-section {
  margin: 0;
}

.conversation-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-item {
  display: flex;
  align-items: center;
  font-size: 12px;

  .label {
    color: var(--gray-600);
    margin-right: 6px;
    min-width: 50px;
    font-weight: 500;
  }

  .value {
    color: var(--gray-800);
    font-weight: 400;
    word-break: break-all;
  }
}

.reason-section {
  margin: 0;
}

.reason-content {
  background: #fff7e6;
  padding: 10px;
  border-radius: 6px;
  border-left: 3px solid #faad14;
  font-size: 13px;
  line-height: 1.4;
  color: var(--gray-800);
  word-break: break-word;
}

// 卡片底部 - 紧凑
.card-footer {
  padding: 8px 16px;
  border-top: 1px solid var(--gray-100);
  background: #fafafa;
  border-radius: 0 0 8px 8px;
}

.time-info {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--gray-500);
}

// 空状态
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 60px 0;
}


// 响应式设计
@media (max-width: 768px) {
  .feedback-cards-container {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .feedback-card {
    margin-bottom: 0;
  }

  .card-header {
    padding: 10px 12px;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .card-content {
    padding: 12px;
    gap: 10px;
  }

  .conversation-info {
    .info-item {
      flex-direction: column;
      align-items: flex-start;
      gap: 2px;

      .label {
        min-width: auto;
        margin-right: 0;
      }
    }
  }

  .card-footer {
    padding: 6px 12px;
  }
}

@media (max-width: 480px) {
  .feedback-cards-container {
    gap: 8px;
  }

  .card-header {
    padding: 8px 10px;
  }

  .card-content {
    padding: 10px;
    gap: 8px;
  }

  .message-content,
  .reason-content {
    padding: 8px;
    font-size: 12px;
  }

  .info-item {
    font-size: 11px;
  }
}
</style>
