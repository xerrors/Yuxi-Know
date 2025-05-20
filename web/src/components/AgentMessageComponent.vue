<template>
  <div class="message-box" :class="[message.type, customClasses]">
    <!-- 用户消息 -->
    <p v-if="message.type === 'human'" class="message-text">{{ message.content }}</p>

    <!-- 助手消息 -->
    <div v-else-if="message.type === 'ai'" class="assistant-message">
      <div v-if="message.reasoning_content" class="reasoning-box">
        <a-collapse v-model:activeKey="reasoningActiveKey" :bordered="false">
          <template #expandIcon="{ isActive }">
            <caret-right-outlined :rotate="isActive ? 90 : 0" />
          </template>
          <a-collapse-panel key="show" :header="message.status=='reasoning' ? '正在思考...' : '推理过程'" class="reasoning-header">
            <p class="reasoning-content">{{ message.reasoning_content.trim() }}</p>
          </a-collapse-panel>
        </a-collapse>
      </div>

      <!-- 消息内容 -->
      <!-- <div v-else-if="message.content" v-html="renderMarkdown(message)" class="message-md"></div> -->
      <MdPreview v-else-if="message.content" ref="editorRef"
        editorId="preview-only"
        previewTheme="github"
        :showCodeRowNumber="false"
        :modelValue="message.content"
        :key="message.id"
        class="message-md"/>

      <div v-else-if="message.reasoning_content"  class="empty-block"></div>

      <div v-if="message.tool_calls && Object.keys(message.tool_calls).length > 0" class="tool-calls-container">
        <div v-for="(toolCall, index) in message.tool_calls || {}" :key="index" class="tool-call-container">
          <div v-if="toolCall" class="tool-call-display" :class="{ 'is-collapsed': !expandedToolCalls.has(toolCall.id) }">
            <div class="tool-header" @click="toggleToolCall(toolCall.id)">
              <span v-if="!toolCall.tool_call_result">
                <LoadingOutlined /> &nbsp;
                <span>正在调用工具: </span>
                <span class="tool-name">{{ toolCall.name || toolCall.function.name }}</span>
              </span>
              <span v-else>
                <ThunderboltOutlined /> 工具 <span class="tool-name">{{ toolCall.name || toolCall.function.name }}</span> 执行完成
              </span>
            </div>
            <div class="tool-content" v-show="expandedToolCalls.has(toolCall.id)">
              <div class="tool-params" v-if="toolCall.args || toolCall.function.arguments">
                <div class="tool-params-header">
                  参数:
                </div>
                <div class="tool-params-content">
                  <pre>{{ toolCall.args || toolCall.function.arguments }}</pre>
                </div>
              </div>
              <div class="tool-params" v-if="toolCall.tool_call_result && toolCall.tool_call_result.content">
                <div class="tool-params-header">
                  执行结果
                </div>
                <div class="tool-params-content">{{ toolCall.tool_call_result.content }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="message.isStoppedByUser" class="retry-hint">
        你停止生成了本次回答
        <span class="retry-link" @click="emit('retryStoppedMessage', message.id)">重新编辑问题</span>
      </div>


      <div v-if="(message.role=='received' || message.role=='assistant') && message.status=='finished' && showRefs">
        <RefsComponent :message="message" :show-refs="showRefs" :is-latest-message="isLatestMessage" @retry="emit('retry')" @openRefs="emit('openRefs', $event)" />
      </div>
      <!-- 错误消息 -->
    </div>

    <div v-if="debugMode" class="status-info">{{ message }}</div>

    <!-- 自定义内容 -->
    <slot></slot>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { CaretRightOutlined, ThunderboltOutlined, LoadingOutlined } from '@ant-design/icons-vue';
import RefsComponent from '@/components/RefsComponent.vue'


import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css';

const props = defineProps({
  // 消息角色：'user'|'assistant'|'sent'|'received'
  message: {
    type: Object,
    required: true
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
  },
  debugMode: {
    type: Boolean,
    default: false
  },
  // 是否为最新消息
  isLatestMessage: {
    type: Boolean,
    default: false
  }
});

const editorRef = ref()

const emit = defineEmits(['retry', 'retryStoppedMessage', 'openRefs']);

// 推理面板展开状态
const reasoningActiveKey = ref(['show']);
const expandedToolCalls = ref(new Set()); // 展开的工具调用集合


// 计算属性：内容为空且正在加载
const isEmptyAndLoading = computed(() => {
  const isEmpty = !props.message.content || props.message.content.length === 0;
  const isLoading = props.message.status === 'init' && props.isProcessing
  return isEmpty && isLoading;
});

const toggleToolCall = (toolCallId) => {
  if (expandedToolCalls.value.has(toolCallId)) {
    expandedToolCalls.value.delete(toolCallId);
  } else {
    expandedToolCalls.value.add(toolCallId);
  }
};
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

  &.human, &.sent {
    max-width: 95%;
    color: white;
    background-color: var(--main-color);
    align-self: flex-end;
    border-radius: .5rem;
    padding: 0.5rem 1rem;
  }

  &.assistant, &.received, &.ai {
    color: initial;
    width: 100%;
    text-align: left;
    margin: 0;
    padding: 0px;
    background-color: transparent;
    border-radius: 0;
  }

  .message-text {
    max-width: 100%;
    margin-bottom: 0;
    white-space: pre-line;
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
    color: var(--gray-700);
    animation: colorPulse 1s infinite ease-in-out;
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
          color: var(--gray-800);

          pre {
            margin: 0;
          }
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

@keyframes colorPulse {
  0% { color: var(--gray-700); }
  50% { color: var(--gray-300); }
  100% { color: var(--gray-700); }
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

<style lang="less">
.message-md {
  margin: 8px 0;
}

.message-md .md-editor-preview-wrapper {
  color: var(--gray-900);
  max-width: 100%;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Noto Sans SC', 'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', 'Hiragino Sans GB', 'Source Han Sans CN', 'Courier New', monospace;

  #preview-only-preview {
    font-size: 15px;
  }

  h1, h2 {
    font-size: 1.2rem;
  }

  h3, h4 {
    font-size: 1.1rem;
  }

  h5, h6 {
    font-size: 1rem;
  }

  // li > p, ol > p, ul > p {
  //   margin: 0.25rem 0;
  // }

  // ol, ul {
  //   padding-left: 1rem;
  // }

  a {
    color: var(--main-700);
  }

  code {
    font-size: 13px;
    font-family: 'Menlo', 'Monaco', 'Consolas', 'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', 'Hiragino Sans GB', 'Source Han Sans CN', 'Courier New', monospace;
    line-height: 1.5;
    letter-spacing: 0.025em;
    tab-size: 4;
    -moz-tab-size: 4;
    background-color: var(--gray-100);
  }
}

.chat-box.font-smaller #preview-only-preview {
  font-size: 14px;

  h1, h2 {
    font-size: 1.1rem;
  }

  h3, h4 {
    font-size: 1rem;
  }
}

.chat-box.font-larger #preview-only-preview {
  font-size: 16px;

  h1, h2 {
    font-size: 1.3rem;
  }

  h3, h4 {
    font-size: 1.2rem;
  }

  h5, h6 {
    font-size: 1.1rem;
  }

  code {
    font-size: 14px;
  }
}
</style>