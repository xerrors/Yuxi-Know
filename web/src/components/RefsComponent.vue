<template>
  <div class="refs" v-if="showRefs">
    <div class="tags">
      <!-- 反馈 -->
      <span
        class="item btn"
        :class="{ disabled: feedbackState.hasSubmitted }"
        @click="likeThisResponse(msg)"
        :title="feedbackState.hasSubmitted && feedbackState.rating === 'like' ? '已点赞' : '点赞'"
      >
        <ThumbsUp size="12" :fill="feedbackState.rating === 'like' ? 'currentColor' : 'none'" />
      </span>
      <span
        class="item btn"
        :class="{ disabled: feedbackState.hasSubmitted }"
        @click="dislikeThisResponse(msg)"
        :title="
          feedbackState.hasSubmitted && feedbackState.rating === 'dislike' ? '已点踩' : '点踩'
        "
      >
        <ThumbsDown
          size="12"
          :fill="feedbackState.rating === 'dislike' ? 'currentColor' : 'none'"
        />
      </span>
      <!-- 模型名称 -->
      <span v-if="showKey('model') && getModelName(msg)" class="item" @click="console.log(msg)">
        <Bot size="12" /> {{ getModelName(msg) }}
      </span>
      <!-- 复制 -->
      <span v-if="showKey('copy')" class="item btn" @click="copyText(msg.content)" title="复制">
        <Check v-if="isCopied" size="12" />
        <Copy v-else size="12" />
      </span>

      <!-- 重试 -->
      <span
        v-if="showKey('regenerate')"
        class="item btn"
        @click="regenerateMessage()"
        title="重新生成"
        ><RotateCcw size="12" />
      </span>
    </div>
  </div>

  <!-- Dislike reason modal -->
  <a-modal
    v-model:open="dislikeModalVisible"
    title="请告诉我们不满意的原因"
    @ok="submitDislikeFeedback"
    @cancel="cancelDislike"
    :confirmLoading="submittingFeedback"
    okText="提交"
    cancelText="取消"
  >
    <a-textarea
      v-model:value="dislikeReason"
      :rows="4"
      placeholder="您的反馈将帮助我们改进服务（可选）"
      :maxlength="500"
      show-count
    />
  </a-modal>
</template>

<script setup>
import { ref, computed, reactive, watch } from 'vue'
import { useClipboard } from '@vueuse/core'
import { message } from 'ant-design-vue'
import { ThumbsUp, ThumbsDown, Bot, Copy, Check, RotateCcw } from 'lucide-vue-next'
import { agentApi } from '@/apis'

const emit = defineEmits(['retry', 'openRefs'])
const props = defineProps({
  message: Object,
  showRefs: {
    type: [Array, Boolean],
    default: () => false
  },
  isLatestMessage: {
    type: Boolean,
    default: false
  }
})

const msg = ref(props.message)

// Feedback state
const feedbackState = reactive({
  hasSubmitted: false,
  rating: null, // 'like' or 'dislike'
  reason: null
})

// 初始化反馈状态 - 从 message.feedback 读取历史反馈
const initFeedbackState = () => {
  if (msg.value?.feedback) {
    feedbackState.hasSubmitted = true
    feedbackState.rating = msg.value.feedback.rating
    feedbackState.reason = msg.value.feedback.reason
  } else {
    feedbackState.hasSubmitted = false
    feedbackState.rating = null
    feedbackState.reason = null
  }
}

// 监听 message prop 变化 (用于切换对话时更新状态)
watch(
  () => props.message,
  () => {
    msg.value = props.message
    initFeedbackState()
  },
  { immediate: true }
)

// Modal state for dislike
const dislikeModalVisible = ref(false)
const dislikeReason = ref('')
const submittingFeedback = ref(false)

// 使用 useClipboard 实现复制功能
const { copy, isSupported } = useClipboard()

const showKey = (key) => {
  if (props.showRefs === true) {
    return true
  }
  return props.showRefs.includes(key)
}

// 复制状态
const isCopied = ref(false)

// 定义 copy 方法
const copyText = async (text) => {
  if (isSupported) {
    try {
      await copy(text)
      message.success('文本已复制到剪贴板')
      isCopied.value = true
      setTimeout(() => {
        isCopied.value = false
      }, 2000)
    } catch (error) {
      console.error('复制失败:', error)
      message.error('复制失败，请手动复制')
    }
  } else {
    console.warn('浏览器不支持自动复制')
    message.warning('浏览器不支持自动复制，请手动复制')
  }
}

const showRefs = computed(() => {
  // 如果只是为了显示模型信息，不需要检查状态
  if (props.showRefs && Array.isArray(props.showRefs) && props.showRefs.includes('model')) {
    return true
  }
  // 原有的逻辑
  return (
    (msg.value.role == 'received' || msg.value.role == 'assistant') &&
    msg.value.status == 'finished'
  )
})

// 添加重新生成方法
const regenerateMessage = () => {
  emit('retry')
}

// 获取模型名称
const getModelName = (msg) => {
  // 优先检查 response_metadata.model_name
  if (msg.response_metadata?.model_name) {
    return msg.response_metadata.model_name
  }
  // 兼容旧格式 meta.server_model_name
  if (msg.meta?.server_model_name) {
    return msg.meta.server_model_name
  }
  return null
}
// Handle like action
const likeThisResponse = async (msg) => {
  if (feedbackState.hasSubmitted) {
    message.info('您已经提交过反馈了')
    return
  }

  if (!msg?.id) {
    message.error('无法提交反馈：消息ID不存在')
    console.error('Message object:', msg)
    return
  }

  try {
    submittingFeedback.value = true
    await agentApi.submitMessageFeedback(msg.id, 'like', null)

    feedbackState.hasSubmitted = true
    feedbackState.rating = 'like'

    message.success('感谢您的反馈！')
  } catch (error) {
    console.error('Failed to submit like feedback:', error)
    if (error.message?.includes('already submitted')) {
      message.info('您已经提交过反馈了')
      feedbackState.hasSubmitted = true
    } else {
      message.error('提交反馈失败，请稍后重试')
    }
  } finally {
    submittingFeedback.value = false
  }
}

// Handle dislike action
const dislikeThisResponse = async (msg) => {
  if (feedbackState.hasSubmitted) {
    message.info('您已经提交过反馈了')
    return
  }

  if (!msg?.id) {
    message.error('无法提交反馈：消息ID不存在')
    console.error('Message object:', msg)
    return
  }

  // Open modal to get reason
  dislikeModalVisible.value = true
}

// Submit dislike feedback with reason
const submitDislikeFeedback = async () => {
  try {
    submittingFeedback.value = true
    await agentApi.submitMessageFeedback(msg.value.id, 'dislike', dislikeReason.value || null)

    feedbackState.hasSubmitted = true
    feedbackState.rating = 'dislike'
    feedbackState.reason = dislikeReason.value

    dislikeModalVisible.value = false
    dislikeReason.value = ''

    message.success('感谢您的反馈！')
  } catch (error) {
    console.error('Failed to submit dislike feedback:', error)
    if (error.message?.includes('already submitted')) {
      message.info('您已经提交过反馈了')
      feedbackState.hasSubmitted = true
      dislikeModalVisible.value = false
    } else {
      message.error('提交反馈失败，请稍后重试')
    }
  } finally {
    submittingFeedback.value = false
  }
}

// Cancel dislike modal
const cancelDislike = () => {
  dislikeModalVisible.value = false
  dislikeReason.value = ''
}
</script>

<style lang="less" scoped>
.refs {
  display: flex;
  margin-bottom: 20px;
  margin-top: 10px;
  color: var(--gray-500);
  font-size: 13px;
  gap: 10px;

  .item {
    background: var(--gray-50);
    color: var(--gray-700);
    padding: 6px 8px;
    border-radius: 8px;
    font-size: 13px;
    user-select: none;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    line-height: 1;

    &.btn {
      cursor: pointer;
      &:hover {
        background: var(--gray-100);
      }
      &:active {
        background: var(--gray-200);
      }

      // Disabled state - when feedback has been submitted
      &.disabled {
        &:hover {
          background: var(--gray-50);
        }
      }
    }
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }
}
</style>
