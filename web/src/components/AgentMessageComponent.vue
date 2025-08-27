<template>
  <div class="message-box" :class="[message.type, customClasses]">
    <!-- 用户消息 -->
    <p v-if="message.type === 'human'" class="message-text">{{ message.content }}</p>

    <!-- 助手消息 -->
    <div v-else-if="message.type === 'ai'" class="assistant-message">
      <div v-if="parsedData.reasoning_content" class="reasoning-box">
        <a-collapse v-model:activeKey="reasoningActiveKey" :bordered="false">
          <template #expandIcon="{ isActive }">
            <caret-right-outlined :rotate="isActive ? 90 : 0" />
          </template>
          <a-collapse-panel key="show" :header="message.status=='reasoning' ? '正在思考...' : '推理过程'" class="reasoning-header">
            <p class="reasoning-content">{{ parsedData.reasoning_content }}</p>
          </a-collapse-panel>
        </a-collapse>
      </div>

      <!-- 消息内容 -->
      <MdPreview v-if="parsedData.content" ref="editorRef"
        editorId="preview-only"
        previewTheme="github"
        :showCodeRowNumber="false"
        :modelValue="parsedData.content"
        :key="message.id"
        class="message-md"/>

      <div v-else-if="parsedData.reasoning_content"  class="empty-block"></div>

      <div v-if="message.tool_calls && Object.keys(message.tool_calls).length > 0" class="tool-calls-container">
        <div v-for="(toolCall, index) in message.tool_calls || {}" :key="index" class="tool-call-container">
          <div v-if="toolCall" class="tool-call-display" :class="{ 'is-collapsed': !expandedToolCalls.has(toolCall.id) }">
            <div class="tool-header" @click="toggleToolCall(toolCall.id)">
              <span v-if="!toolCall.tool_call_result">
                <span><Loader size="16" class="tool-loader rotate tool-loading" /></span> &nbsp;
                <span>正在调用工具: </span>
                <span class="tool-name">{{ getToolNameByToolCall(toolCall) }}</span>
              </span>
              <span v-else>
                <span><CircleCheckBig size="16" class="tool-loader tool-success" /></span> &nbsp; 工具 <span class="tool-name">{{ getToolNameByToolCall(toolCall) }}</span> 执行完成
              </span>
            </div>
            <div class="tool-content" v-show="expandedToolCalls.has(toolCall.id)">
              <div class="tool-params" v-if="toolCall.args || toolCall.function.arguments">
                <div class="tool-params-content">
                  <strong>参数:</strong> {{ toolCall.args || toolCall.function.arguments }}
                </div>
              </div>
              <div class="tool-result" v-if="toolCall.tool_call_result && toolCall.tool_call_result.content">
                <div class="tool-result-content" :data-tool-call-id="toolCall.id">
                  <ToolResultRenderer
                    :tool-name="toolCall.name || toolCall.function.name"
                    :result-content="toolCall.tool_call_result.content"
                  />
                </div>
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
import { Loader, CircleCheckBig } from 'lucide-vue-next';
import { ToolResultRenderer } from '@/components/ToolCallingResult'
import { useAgentStore } from '@/stores/agent'
import { storeToRefs } from 'pinia'


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
const reasoningActiveKey = ref(['hide']);
const expandedToolCalls = ref(new Set()); // 展开的工具调用集合

// 引入智能体 store
const agentStore = useAgentStore();
const { availableTools } = storeToRefs(agentStore);

// 工具相关方法
const getToolNameByToolCall = (toolCall) => {
  const toolId = toolCall.name || toolCall.function.name;
  const toolsList = availableTools.value ? Object.values(availableTools.value) : [];
  const tool = toolsList.find(t => t.id === toolId);
  return tool ? tool.name : toolId;
};

const parsedData = computed(() => {
  // Start with default values from the prop to avoid mutation.
  let content = props.message.content.trim() || '';
  let reasoning_content = props.message.additional_kwargs?.reasoning_content || '';

  // Regex to find <think>...</think> or an unclosed <think>... at the end of the string.
  const thinkRegex = /<think>(.*?)<\/think>|<think>(.*?)$/s;
  const thinkMatch = content.match(thinkRegex);

  if (thinkMatch) {
    // The captured reasoning is in either group 1 (closed tag) or 2 (unclosed tag).
    reasoning_content = (thinkMatch[1] || thinkMatch[2] || '').trim();
    // Remove the entire matched <think> block from the original content.
    content = content.replace(thinkMatch[0], '').trim();
  }

  return {
    content,
    reasoning_content,
  };
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
    border: 1px solid var(--gray-200);
    background-color: var(--gray-25);
    overflow: hidden;
    transition: all 0.2s ease;

    :deep(.ant-collapse) {
      background-color: transparent;
      border: none;

      .ant-collapse-item {
        border: none;

        .ant-collapse-header {
          padding: 8px 12px;
          // background-color: var(--gray-100);
          font-size: 14px;
          font-weight: 500;
          color: var(--gray-700);
          transition: all 0.2s ease;

          .ant-collapse-expand-icon {
            color: var(--gray-400);
          }
        }

        .ant-collapse-content {
          border: none;
          background-color: transparent;

          .ant-collapse-content-box {
            padding: 16px;
            background-color: var(--gray-25);
          }
        }
      }
    }

    .reasoning-content {
      font-size: 13px;
      color: var(--gray-800);
      white-space: pre-wrap;
      margin: 0;
      line-height: 1.6;
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
    background-color: var(--gray-25);
    outline: 1px solid var(--gray-200);
    border-radius: 8px;
    overflow: hidden;
    transition: all 0.2s ease;

    .tool-header {
      padding: 8px 12px;
      // background-color: var(--gray-100);
      font-size: 14px;
      font-weight: 500;
      color: var(--gray-800);
      border-bottom: 1px solid var(--gray-100);
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      user-select: none;
      position: relative;
      transition: color 0.2s ease;
      align-items: center;

      .anticon {
        color: var(--main-color);
        font-size: 16px;
      }

      .tool-name {
        font-weight: 600;
        color: var(--main-700);
      }

      span {
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .tool-loader {
        margin-top: 2px;
        color: var(--main-700);
      }

      .tool-loader.rotate {
        animation: rotate 2s linear infinite;
      }

      .tool-loader.tool-success {
        color: var(--color-success);
      }

      .tool-loader.tool-error {
        color: var(--color-error);
      }

      .tool-loader.tool-loading {
        color: var(--color-info);
      }
    }

    .tool-content {
      transition: all 0.3s ease;

      .tool-params {
        padding: 10px 16px;
        background-color: var(--gray-25);
        border-bottom: 1px solid var(--gray-150);

        .tool-params-header {
          // unused
          background-color: var(--gray-100);
          font-size: 13px;
          color: var(--gray-800);
          margin-bottom: 8px;
          font-weight: 500;
        }

        .tool-params-content {
          margin: 0;
          font-size: 13px;
          overflow-x: auto;
          color: var(--gray-700);
          line-height: 1.5;

          pre {
            margin: 0;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
          }
        }
      }

      .tool-result {
        padding: 0;
        background-color: transparent;

        .tool-result-header {
          padding: 12px 16px;
          background-color: var(--gray-100);
          font-size: 12px;
          color: var(--gray-700);
          font-weight: 500;
          border-bottom: 1px solid var(--gray-200);
        }

        .tool-result-content {
          padding: 0;
          background-color: transparent;
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

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>

<style lang="less" scoped>
:deep(.message-md) {
  margin: 8px 0;
}

:deep(.message-md .md-editor-preview-wrapper) {
  max-width: 100%;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Noto Sans SC', 'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', 'Hiragino Sans GB', 'Source Han Sans CN', 'Courier New', monospace;

  #preview-only-preview {
    font-size: 1rem;
    line-height: 1.75;
    color: var(--gray-1000);
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

  strong {
    font-weight: 500;
  }

  li > p, ol > p, ul > p {
    margin: 0.25rem 0;
  }

  ul li::marker,
  ol li::marker {
    color: var(--main-bright);
  }

  ul, ol {
    padding-left: 1.625rem;
  }

  cite {
    font-size: 12px;
    color: var(--gray-700);
    font-style: normal;
    background-color: var(--gray-200);
    border-radius: 4px;
    outline: 2px solid var(--gray-200);
  }

  a {
    color: var(--main-700);
  }

  .md-editor-code {
    border: var(--gray-50);
    border-radius: 8px;

    .md-editor-code-head {
      background-color: var(--gray-50);

      .md-editor-collapse-tips {
        color: var(--gray-400);
      }
    }
  }

  code {
    font-size: 13px;
    font-family: 'Menlo', 'Monaco', 'Consolas', 'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', 'Hiragino Sans GB', 'Source Han Sans CN', 'Courier New', monospace;
    line-height: 1.5;
    letter-spacing: 0.025em;
    tab-size: 4;
    -moz-tab-size: 4;
    background-color: var(--gray-25);
  }

  p:last-child {
    margin-bottom: 0;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
    font-size: 16px;
    display: table;


    thead th,
    tbody th {
      border: none;
      border-bottom: 1.5px solid var(--gray-400);
    }

    tbody tr:last-child td {
      border-bottom: 1.5px solid var(--gray-300);
      border: none;
    }
  }

  th,
  td {
    padding: 0.5rem 0rem;
    text-align: left;
    border: none;
  }

  td {
    border-bottom: 1px solid var(--gray-100);
    color: var(--gray-800);
  }

  th {
    font-weight: 600;
    color: var(--gray-800);
  }

  tr {
    background-color: var(--gray-0);
  }

  // tbody tr:last-child td {
  //   border-bottom: none;
  // }
}

:deep(.chat-box.font-smaller #preview-only-preview) {
  font-size: 14px;

  h1, h2 {
    font-size: 1.1rem;
  }

  h3, h4 {
    font-size: 1rem;
  }
}

:deep(.chat-box.font-larger #preview-only-preview) {
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