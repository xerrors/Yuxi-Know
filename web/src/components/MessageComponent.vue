<template>
  <div class="message-box" :class="[role, customClasses]">
    <!-- 用户消息 -->
    <p v-if="role === 'user' || role === 'sent'" class="message-text">{{ content }}</p>

    <!-- 助手消息 -->
    <div v-else-if="role === 'assistant' || role === 'received'" class="assistant-message">
      <!-- 推理过程 (ChatComponent特有) -->
      <div v-if="reasoningContent" class="reasoning-box">
        <a-collapse v-model:activeKey="reasoningActiveKey" :bordered="false">
          <template #expandIcon="{ isActive }">
            <caret-right-outlined :rotate="isActive ? 90 : 0" />
          </template>
          <a-collapse-panel key="show" :header="reasoningHeader" class="reasoning-header">
            <p class="reasoning-content">{{ reasoningContent }}</p>
          </a-collapse-panel>
        </a-collapse>
      </div>

      <!-- 加载中状态 -->
      <div v-if="isEmptyAndLoading" class="loading-dots">
        <div></div>
        <div></div>
        <div></div>
      </div>

      <!-- 检索中状态 (ChatComponent特有) -->
      <div v-else-if="status === 'searching' && isProcessing" class="searching-msg">
        <i>正在检索……</i>
      </div>

      <!-- 生成中状态 (ChatComponent特有) -->
      <div v-else-if="status === 'generating' && isProcessing" class="searching-msg">
        <i>正在生成……</i>
      </div>

      <!-- 消息内容 -->
      <div v-else-if="contentHtml" v-html="contentHtml" class="message-md"></div>

      <!-- 工具调用 (AgentView特有) -->
      <slot name="tool-calls"></slot>

      <!-- 引用组件 (ChatComponent特有) -->
      <slot name="refs"></slot>
    </div>

    <!-- 错误消息 -->
    <div v-else-if="status === 'error'" class="err-msg" @click="$emit('retry')">
      请求错误，请重试。{{ errorMessage }}
    </div>

    <!-- 自定义内容 -->
    <slot></slot>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { CaretRightOutlined } from '@ant-design/icons-vue';

const props = defineProps({
  // 消息角色：'user'|'assistant'|'sent'|'received'
  role: {
    type: String,
    required: true
  },
  // 消息内容
  content: {
    type: String,
    default: ''
  },
  // 已渲染的HTML内容
  contentHtml: {
    type: String,
    default: ''
  },
  // 推理内容 (ChatComponent使用)
  reasoningContent: {
    type: String,
    default: ''
  },
  // 消息状态
  status: {
    type: String,
    default: ''
  },
  // 是否正在处理中
  isProcessing: {
    type: Boolean,
    default: false
  },
  // 错误信息
  errorMessage: {
    type: String,
    default: ''
  },
  // 自定义类
  customClasses: {
    type: Object,
    default: () => ({})
  },
  // 推理框标题
  reasoningHeader: {
    type: String,
    default: '推理过程'
  }
});

const emit = defineEmits(['retry']);

// 推理面板展开状态
const reasoningActiveKey = ref(['show']);

// 计算属性：内容为空且正在加载
const isEmptyAndLoading = computed(() => {
  const isEmpty = !props.content || props.content.length === 0;
  const isLoading = props.status === 'init' ||
                    props.status === 'loading' ||
                    props.status === 'reasoning' ||
                    props.isProcessing;
  return isEmpty && isLoading;
});
</script>

<style lang="less" scoped>
.message-box {
  display: inline-block;
  border-radius: 1.5rem;
  margin: 0.8rem 0;
  padding: 0.625rem 1.25rem;
  user-select: text;
  word-break: break-word;
  font-size: 15px;
  font-weight: 400;
  box-sizing: border-box;
  color: black;
  max-width: 100%;
  position: relative;

  &.user, &.sent {
    line-height: 24px;
    max-width: 95%;
    color: white;
    background-color: var(--main-color);
    // background: linear-gradient(90deg, var(--main-light-1) 10.79%, var(--main-color) 87.08%);
    align-self: flex-end;
    border-radius: 1.5rem;
    padding: 0.625rem 1.25rem;
  }

  &.assistant, &.received {
    color: initial;
    width: 100%;
    text-align: left;
    word-wrap: break-word;
    margin: 0 0 16px 0;
    padding: 16px 0 0 0;
    text-align: justify;
    background-color: transparent;
    border-radius: 0;
  }

  .message-text {
    max-width: 100%;
    word-wrap: break-word;
    margin-bottom: 0;
    white-space: pre-line;
  }

  .message-md {
    word-wrap: break-word;
    margin-bottom: 0;

    :deep(code) {
      padding: 2px 4px;
      border-radius: 4px;
      background-color: var(--gray-100);
    }

    :deep(pre) {
      padding: 12px;
      border-radius: 8px;
      background-color: var(--gray-100);
      overflow-x: auto;

      code {
        padding: 0;
        background-color: transparent;
      }
    }
  }

  .err-msg {
    color: #eb8080;
    border: 1px solid #eb8080;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    text-align: left;
    background: #FFF5F5;
    margin-bottom: 10px;
    cursor: pointer;
  }

  .searching-msg {
    color: var(--gray-500);
    animation: colorPulse 2s infinite;
  }

  .reasoning-box {
    margin-top: 10px;
    margin-bottom: 15px;
    border-radius: 8px;
    border: 1px solid var(--main-light-3);
    overflow: hidden;

    :deep(.ant-collapse) {
      background: white;
      border: none;
    }

    :deep(.ant-collapse-item) {
      border: none;
    }

    :deep(.ant-collapse-header) {
      padding: 8px 12px;
      background-color: var(--main-50);
      font-size: 13px;
      color: var(--main-700);
      border-bottom: 1px solid var(--main-light-3);
    }

    .reasoning-content {
      padding: 10px 12px;
      font-size: 13px;
      color: var(--gray-700);
      white-space: pre-wrap;
      max-height: 200px;
      overflow-y: auto;
      background-color: white;
      margin: 0;
    }
  }

  .assistant-message {
    width: 100%;
  }

  .status-info {
    display: block;
    background-color: var(--gray-50);
    color: var(--gray-700);
    padding: 10px;
    border-radius: 8px;
    margin-bottom: 10px;
    font-size: 12px;
    font-family: monospace;
    max-height: 200px;
    overflow-y: auto;
  }

  :deep(.tool-calls-container) {
    width: 100%;
    margin-top: 10px;

    .tool-call-container {
      margin-bottom: 10px;

      &:last-child {
        margin-bottom: 0;
      }
    }
  }

  :deep(.tool-call-display) {
    background-color: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 4px rgba(60, 60, 60, 0.05);
    animation: fadeInUp 0.3s ease-out;

    .tool-header {
      padding: 10px 12px;
      background-color: var(--gray-100);
      font-size: 14px;
      font-weight: 500;
      color: var(--gray-800);
      border-bottom: 1px solid var(--gray-200);
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      user-select: none;
      position: relative;

      .anticon {
        color: var(--main-600);
      }

      .step-badge {
        margin-left: auto;
        background-color: var(--gray-200);
        color: var(--gray-700);
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
      }
    }

    .tool-content {
      transition: all 0.3s ease;
      .tool-params {
        padding: 10px 12px;
        background-color: var(--gray-50);

        .tool-params-header {
          background-color: var(--gray-100);
          font-size: 13px;
          color: var(--gray-800);
        }

        .tool-params-content {
          margin: 0;
          font-size: 13px;
          background-color: var(--gray-100);
          border-radius: 4px;
          padding: 8px;
          overflow-x: auto;
        }
      }
    }

    &.is-collapsed {
      .tool-header {
        border-bottom: none;
      }
    }
  }
}

.loading-dots {
  display: inline-flex;
  align-items: center;
  justify-content: center;

  div {
    width: 8px;
    height: 8px;
    margin: 0 4px;
    background-color: var(--gray-700);
    border-radius: 50%;
    opacity: 0.3;
    animation: pulse 0.5s infinite ease-in-out both;

    &:nth-child(1) {
      animation-delay: -0.32s;
    }

    &:nth-child(2) {
      animation-delay: -0.16s;
    }
  }
}

@keyframes colorPulse {
  0% { color: var(--gray-700); }
  50% { color: var(--gray-300); }
  100% { color: var(--gray-700); }
}

@keyframes pulse {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.3;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>