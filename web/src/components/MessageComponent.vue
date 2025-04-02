<template>
  <div class="message-box" :class="[message.role, customClasses]">
    <!-- 用户消息 -->
    <p v-if="message.role === 'user' || message.role === 'sent'" class="message-text">{{ message.content }}</p>

    <!-- 助手消息 -->
    <div v-else-if="message.role === 'assistant' || message.role === 'received'" class="assistant-message">
      <!-- 推理过程 (ChatComponent特有) -->
      <div v-if="message.reasoning_content" class="reasoning-box">
        <a-collapse v-model:activeKey="reasoningActiveKey" :bordered="false">
          <template #expandIcon="{ isActive }">
            <caret-right-outlined :rotate="isActive ? 90 : 0" />
          </template>
          <a-collapse-panel key="show" :header="message.status=='reasoning' ? '正在思考...' : '推理过程'" class="reasoning-header">
            <p class="reasoning-content">{{ message.reasoning_content }}</p>
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
      <div v-else-if="message.status === 'searching' && isProcessing" class="searching-msg">
        <i>正在检索……</i>
      </div>

      <!-- 生成中状态 (ChatComponent特有) -->
      <div v-else-if="message.status === 'generating' && isProcessing" class="searching-msg">
        <i>正在生成……</i>
      </div>

      <div v-else-if="message.status === 'error'" class="err-msg" @click="$emit('retry')">
        请求错误，请重试。{{ message.message }}
      </div>

      <!-- 消息内容 -->
      <div v-else-if="message.content" v-html="renderMarkdown(message)" class="message-md"></div>

      <div v-if="message.isStoppedByUser" class="retry-hint">
        你停止生成了本次回答
        <span class="retry-link" @click="emit('retryStoppedMessage', message.id)">重新编辑问题</span>
      </div>

      <!-- 工具调用 (AgentView特有) -->
      <slot name="tool-calls"></slot>

      <div v-if="(message.role=='received' || message.role=='assistant') && message.status=='finished' && showRefs">
        <RefsComponent :message="message" :show-refs="showRefs" @retry="emit('retry')" />
      </div>
      <!-- 错误消息 -->
    </div>

    <!-- 自定义内容 -->
    <slot></slot>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { CaretRightOutlined } from '@ant-design/icons-vue';
import RefsComponent from '@/components/RefsComponent.vue'

import { Marked } from 'marked';
import { markedHighlight } from 'marked-highlight';
import hljs from 'highlight.js';
import 'highlight.js/styles/github.css';


const props = defineProps({
  // 消息角色：'user'|'assistant'|'sent'|'received'
  message: {
    type: Object,
    required: true
  },
  // 已渲染的HTML内容
  contentHtml: {
    type: String,
    default: ''
  },
  // 是否正在处理中
  isProcessing: {
    type: Boolean,
    default: false
  },
  // 自定义类
  customClasses: {
    type: Object,
    default: () => ({})
  },
  // 是否显示推理过程
  showRefs: {
    type: [Array, Boolean],
    default: () => false
  }
});

const statusDefination = {
  init: '初始化',
  loading: '加载中',
  reasoning: '推理中',
  generating: '生成中',
  error: '错误'
}

const emit = defineEmits(['retry', 'retryStoppedMessage']);

// 推理面板展开状态
const reasoningActiveKey = ref(['show']);


const renderMarkdown = (msg) => {
  if (!msg.content) return '';

  if (msg.status === 'loading') {
    return marked.parse(msg.content + '🟢')
  } else {
    return marked.parse(msg.content)
  }
}


const marked = new Marked(
  {
    gfm: true,
    breaks: true,
    tables: true,
  },
  markedHighlight({
    langPrefix: 'hljs language-',
    highlight(code) {
      return hljs.highlightAuto(code).value;
    }
  })
);

// 计算属性：内容为空且正在加载
const isEmptyAndLoading = computed(() => {
  const isEmpty = !props.message.content || props.message.content.length === 0;
  const isLoading = props.message.status === 'init'
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
  word-wrap: break-word;
  font-size: 15px;
  line-height: 24px;
  box-sizing: border-box;
  color: black;
  max-width: 100%;
  position: relative;
  letter-spacing: .25px;

  &.user, &.sent {
    max-width: 95%;
    color: white;
    background-color: var(--main-color);
    // background-color: var(--main-color);
    // background: linear-gradient(90deg, var(--main-light-1) 10.79%, var(--main-color) 87.08%);
    align-self: flex-end;
    border-radius: .5rem;
    padding: 0.5rem 1rem;
  }

  &.assistant, &.received {
    color: initial;
    width: 100%;
    text-align: left;
    margin: 0 0 16px 0;
    padding: 0px;
    background-color: transparent;
    border-radius: 0;
  }

  .message-text {
    max-width: 100%;
    margin-bottom: 0;
    white-space: pre-line;
  }

  .message-md {
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
    color: #d15252;
    border: 1px solid #f19999;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    text-align: left;
    background: #fffbfb;
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

    .reasoning-content {
      font-size: 13px;
      color: var(--gray-800);
      white-space: pre-wrap;
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

.retry-hint {
  margin-top: 8px;
  padding: 8px 16px;
  color: #666;
  font-size: 14px;
  text-align: left;
}

.retry-link {
  color: #1890ff;
  cursor: pointer;
  margin-left: 4px;

  &:hover {
    text-decoration: underline;
  }
}

.ant-btn-icon-only {
  &:has(.anticon-stop) {
    background-color: #ff4d4f !important;

    &:hover {
      background-color: #ff7875 !important;
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