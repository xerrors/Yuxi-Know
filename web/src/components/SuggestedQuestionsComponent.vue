<template>
  <div class="suggested-questions" v-if="showComponent">
    <div class="suggested-header">
      <Lightbulb size="14" class="header-icon" />
      <span class="header-text">猜你想问</span>
      <a-button
        class="refresh-btn"
        type="link"
        :icon="h(RefreshCw)"
        title="换一批"
        @click="handleRefresh"
        :disabled="loading"
        :loading="loading"
      />
    </div>

    <!-- Loading状态 -->
    <div class="loading-container" v-if="loading">
      <div class="loading-dots">
        <div class="dot"></div>
        <div class="dot"></div>
        <div class="dot"></div>
      </div>
      <span class="loading-text">正在生成问题...</span>
    </div>

    <!-- 正常显示的问题列表 -->
    <div class="questions-container" v-else-if="questions.length > 0">
      <div
        v-for="(question, index) in questions"
        :key="index"
        class="question-chip"
        @click="handleQuestionClick(question)"
        @mouseenter="hoveredQuestion = index"
        @mouseleave="hoveredQuestion = null"
      >
        <div class="question-text">
          {{ question }}
        </div>
        <ArrowUpRight
          size="10"
          class="arrow-icon"
          :class="{ visible: hoveredQuestion === index }"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, h, onUnmounted } from 'vue'
import { Lightbulb, ArrowUpRight, RefreshCw } from 'lucide-vue-next'
import { threadApi } from '@/apis/agent_api'

const props = defineProps({
  threadId: {
    type: String,
    default: null
  },
  show: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['question-click'])

const questions = ref([])
const loading = ref(false)
const hoveredQuestion = ref(null)
const pollingTimer = ref(null)

const showComponent = computed(() => {
  return props.show && props.threadId && (questions.value.length > 0 || loading.value)
})

// 停止轮询
const stopPolling = () => {
  if (pollingTimer.value) {
    clearTimeout(pollingTimer.value)
    pollingTimer.value = null
  }
}

// 开始轮询等待生成完成
const startPolling = () => {
  stopPolling()
  const poll = async () => {
    if (!props.threadId) return

    try {
      const res = await threadApi.getSuggestedQuestions(props.threadId)
      if (!res.is_generating) {
        // 生成完成，更新问题并停止轮询
        questions.value = res.questions || []
        loading.value = false
        stopPolling()
      } else {
        // 还在生成中，继续等待
        pollingTimer.value = setTimeout(poll, 2000)
      }
    } catch (error) {
      console.error('轮询建议问题失败:', error)
      loading.value = false
      stopPolling()
    }
  }
  pollingTimer.value = setTimeout(poll, 2000)
}

const fetchQuestions = async () => {
  if (!props.threadId) return

  loading.value = true
  try {
    const res = await threadApi.getSuggestedQuestions(props.threadId)
    questions.value = res.questions || []

    // 如果正在生成中，开始轮询
    if (res.is_generating) {
      loading.value = true
      startPolling()
    } else {
      loading.value = false
    }
  } catch (error) {
    console.error('获取建议问题失败:', error)
    questions.value = []
    loading.value = false
  }
}

const handleQuestionClick = (questionText) => {
  emit('question-click', questionText)
}

const handleRefresh = async () => {
  if (!props.threadId || loading.value) return

  loading.value = true
  try {
    const res = await threadApi.refreshSuggestedQuestions(props.threadId)
    questions.value = res.questions || []

    // 如果正在生成中，开始轮询
    if (res.is_generating) {
      startPolling()
    } else {
      loading.value = false
    }
  } catch (error) {
    console.error('刷新建议问题失败:', error)
    loading.value = false
  }
}

// 监听 threadId 变化
watch(
  () => props.threadId,
  (newThreadId) => {
    // 切换会话时，先停止之前的轮询
    stopPolling()
    if (newThreadId) {
      questions.value = []
      fetchQuestions()
    }
  },
  { immediate: true }
)

// 组件销毁时清理
onUnmounted(() => {
  stopPolling()
})

// 暴露刷新方法供父组件调用
defineExpose({
  refresh: fetchQuestions
})
</script>

<style lang="less" scoped>
.suggested-questions {
  margin: 12px 0 8px 0;
  padding: 8px 0;
  border-top: 1px solid var(--gray-100);
  animation: fadeInUp 0.3s ease-out;
}

.suggested-header {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
  font-size: 0.75rem;
  color: var(--gray-600);
  font-weight: 500;

  .header-icon {
    color: var(--main-500);
    flex-shrink: 0;
  }

  .header-text {
    font-size: 0.9rem;
    letter-spacing: 0.25px;
    font-weight: bold;
  }
}

.refresh-btn {
  color: var(--gray-600);
  transition: all 0.2s ease;
  border-radius: 6px;
  width: 20px;
  height: 20px;
  min-width: 20px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover {
    color: var(--main-500);
    background: var(--main-50);
    transform: rotate(90deg);
  }

  &:active {
    transform: scale(0.9) rotate(90deg);
  }
}

.loading-container {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  animation: fadeIn 0.3s ease-out;
}

.loading-dots {
  display: flex;
  gap: 3px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: var(--main-400);
  animation: dotPulse 1.5s infinite ease-in-out;
}

.dot:nth-child(1) {
  animation-delay: 0s;
}

.dot:nth-child(2) {
  animation-delay: 0.2s;
}

.dot:nth-child(3) {
  animation-delay: 0.4s;
}

.loading-text {
  font-size: 0.7rem;
  color: var(--gray-500);
}

.questions-container {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.question-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: var(--gray-50);
  border: 1px solid var(--gray-100);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
  color: var(--gray-700);
  transition: all 0.2s ease;
  user-select: none;
  max-width: 100%;
  box-sizing: border-box;

  &:hover {
    background: var(--main-25);
    border-color: var(--main-200);
    color: var(--main-700);
    transform: translateY(-1px);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }

  &:active {
    transform: translateY(0);
  }

  .question-text {
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .arrow-icon {
    opacity: 0;
    color: var(--main-500);
    transition: all 0.2s ease;
    transform: translateX(-1px);
    flex-shrink: 0;

    &.visible {
      opacity: 1;
      transform: translateX(0);
    }
  }
}

@media (max-width: 768px) {
  .suggested-questions {
    margin: 10px 0 6px 0;
    padding: 6px 0;
  }

  .questions-container {
    gap: 4px;
  }

  .question-chip {
    padding: 3px 6px;
    font-size: 0.75rem;
  }
}

@media (max-width: 520px) {
  .question-chip {
    .arrow-icon {
      display: none;
    }
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes dotPulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.7;
  }
  50% {
    transform: scale(1.2);
    opacity: 1;
  }
}
</style>