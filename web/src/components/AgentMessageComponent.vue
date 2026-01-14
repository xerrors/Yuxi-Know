<template>
  <div
    v-if="message.message_type === 'multimodal_image' && message.image_content"
    class="message-image"
  >
    <img :src="`data:image/jpeg;base64,${message.image_content}`" alt="用户上传的图片" />
  </div>
  <div class="message-box" :class="[message.type, customClasses]">
    <!-- 用户消息 -->
    <div
      v-if="message.type === 'human'"
      class="message-copy-btn human-copy"
      @click="copyToClipboard(message.content)"
      :class="{ 'is-copied': isCopied }"
    >
      <Check v-if="isCopied" size="14" />
      <Copy v-else size="14" />
    </div>
    <p v-if="message.type === 'human'" class="message-text">{{ message.content }}</p>

    <p v-else-if="message.type === 'system'" class="message-text-system">{{ message.content }}</p>

    <!-- 助手消息 -->
    <div v-else-if="message.type === 'ai'" class="assistant-message">
      <div v-if="parsedData.reasoning_content" class="reasoning-box">
        <a-collapse v-model:activeKey="reasoningActiveKey" :bordered="false">
          <template #expandIcon="{ isActive }">
            <caret-right-outlined :rotate="isActive ? 90 : 0" />
          </template>
          <a-collapse-panel
            key="show"
            :header="message.status == 'reasoning' ? '正在思考...' : '推理过程'"
            class="reasoning-header"
          >
            <p class="reasoning-content">{{ parsedData.reasoning_content }}</p>
          </a-collapse-panel>
        </a-collapse>
      </div>

      <!-- 消息内容 -->
      <MdPreview
        v-if="parsedData.content"
        ref="editorRef"
        editorId="preview-only"
        :theme="theme"
        previewTheme="github"
        :showCodeRowNumber="false"
        :modelValue="parsedData.content"
        :key="message.id"
        class="message-md"
      />

      <div v-else-if="parsedData.reasoning_content" class="empty-block"></div>

      <!-- 错误提示块 -->
      <div v-if="displayError" class="error-hint">
        <span v-if="getErrorMessage">{{ getErrorMessage }}</span>
        <span v-else-if="message.error_type === 'interrupted'">回答生成已中断</span>
        <span v-else-if="message.error_type === 'unexpect'">生成过程中出现异常</span>
        <span v-else-if="message.error_type === 'content_guard_blocked'"
          >检测到敏感内容，已中断输出</span
        >
        <span v-else>{{ message.error_type || '未知错误' }}</span>
      </div>

      <div v-if="validToolCalls && validToolCalls.length > 0" class="tool-calls-container">
        <div
          v-for="(toolCall, index) in validToolCalls"
          :key="toolCall.id || index"
          class="tool-call-container"
        >
          <ToolCallRenderer :tool-call="toolCall" />
        </div>
      </div>

      <div v-if="message.isStoppedByUser" class="retry-hint">
        你停止生成了本次回答
        <span class="retry-link" @click="emit('retryStoppedMessage', message.id)"
          >重新编辑问题</span
        >
      </div>

      <div
        v-if="
          (message.role == 'received' || message.role == 'assistant') &&
          message.status == 'finished' &&
          showRefs
        "
      >
        <RefsComponent
          :message="message"
          :show-refs="showRefs"
          :is-latest-message="isLatestMessage"
          @retry="emit('retry')"
          @openRefs="emit('openRefs', $event)"
        />
      </div>
      <!-- 错误消息 -->
    </div>

    <div v-if="infoStore.debugMode" class="status-info">{{ message }}</div>

    <!-- 自定义内容 -->
    <slot></slot>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { CaretRightOutlined, ThunderboltOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import RefsComponent from '@/components/RefsComponent.vue'
import { Copy, Check } from 'lucide-vue-next'
import { ToolCallRenderer } from '@/components/ToolCallingResult'
import { useAgentStore } from '@/stores/agent'
import { useInfoStore } from '@/stores/info'
import { useThemeStore } from '@/stores/theme'
import { storeToRefs } from 'pinia'

import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'

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
  // 是否为最新消息
  isLatestMessage: {
    type: Boolean,
    default: false
  },
  // 是否显示调试信息 (已废弃，使用 infoStore.debugMode)
  debugMode: {
    type: Boolean,
    default: false
  }
})

const editorRef = ref()

const emit = defineEmits(['retry', 'retryStoppedMessage', 'openRefs'])

// 复制状态
const isCopied = ref(false)

const copyToClipboard = async (text) => {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      // 降级处理：使用传统的 execCommand 方法
      const textArea = document.createElement('textarea')
      textArea.value = text
      textArea.style.position = 'fixed'
      textArea.style.left = '-999999px'
      textArea.style.top = '-999999px'
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()
      const successful = document.execCommand('copy')
      document.body.removeChild(textArea)
      if (!successful) throw new Error('execCommand failed')
    }
    isCopied.value = true
    setTimeout(() => {
      isCopied.value = false
    }, 2000)
  } catch (err) {
    console.error('Failed to copy: ', err)
  }
}

// 推理面板展开状态
const reasoningActiveKey = ref(['hide'])

// 错误消息处理
const displayError = computed(() => {
  // 简化错误判断：只检查明确的错误类型标识
  return !!(props.message.error_type || props.message.extra_metadata?.error_type)
})

const getErrorMessage = computed(() => {
  // 优先使用直接的 error_message 字段
  if (props.message.error_message) {
    return props.message.error_message
  }

  // 其次从 extra_metadata 中获取具体的错误信息
  if (props.message.extra_metadata?.error_message) {
    return props.message.extra_metadata.error_message
  }

  // 对于已知的错误类型，返回默认提示
  switch (props.message.error_type) {
    case 'interrupted':
      return '回答生成已中断'
    case 'content_guard_blocked':
      return '检测到敏感内容，已中断输出'
    case 'unexpect':
      return '生成过程中出现异常'
    case 'agent_error':
      return '智能体获取失败'
    default:
      return null
  }
})

// 引入智能体 store
const agentStore = useAgentStore()
const infoStore = useInfoStore()
const themeStore = useThemeStore()

// 主题设置 - 根据系统主题动态切换
const theme = computed(() => (themeStore.isDark ? 'dark' : 'light'))

// 过滤有效的工具调用
const validToolCalls = computed(() => {
  if (!props.message.tool_calls || !Array.isArray(props.message.tool_calls)) {
    return []
  }

  return props.message.tool_calls.filter((toolCall) => {
    // 过滤掉无效的工具调用
    return (
      toolCall &&
      (toolCall.id || toolCall.name) &&
      (toolCall.args !== undefined ||
        toolCall.function?.arguments !== undefined ||
        toolCall.tool_call_result !== undefined)
    )
  })
})

const parsedData = computed(() => {
  // Start with default values from the prop to avoid mutation.
  let content = props.message.content.trim() || ''
  let reasoning_content = props.message.additional_kwargs?.reasoning_content || ''

  if (reasoning_content) {
    return {
      content,
      reasoning_content
    }
  }

  // Regex to find <think>...</think> or an unclosed <think>... at the end of the string.
  const thinkRegex = /<think>(.*?)<\/think>|<think>(.*?)$/s
  const thinkMatch = content.match(thinkRegex)

  if (thinkMatch) {
    // The captured reasoning is in either group 1 (closed tag) or 2 (unclosed tag).
    reasoning_content = (thinkMatch[1] || thinkMatch[2] || '').trim()
    // Remove the entire matched <think> block from the original content.
    content = content.replace(thinkMatch[0], '').trim()
  }

  return {
    content,
    reasoning_content
  }
})
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
  color: var(--gray-10000);
  max-width: 100%;
  position: relative;
  letter-spacing: 0.25px;

  &.human,
  &.sent {
    max-width: 95%;
    color: var(--gray-1000);
    background-color: var(--main-50);
    align-self: flex-end;
    border-radius: 0.5rem;
    padding: 0.5rem 1rem;
  }

  &.assistant,
  &.received,
  &.ai {
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

  .message-copy-btn {
    cursor: pointer;
    color: var(--gray-400);
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    flex-shrink: 0;

    &:hover {
      color: var(--main-color);
    }

    &.is-copied {
      color: var(--color-success-500);
      opacity: 1;
    }

    &.human-copy {
      position: absolute;
      left: -28px;
      bottom: 8px;
    }
  }

  &:hover {
    .message-copy-btn {
      opacity: 1;
    }
  }

  .message-text-system {
    max-width: 100%;
    margin-bottom: 0;
    white-space: pre-line;
    color: var(--gray-600);
    font-style: italic;
    font-size: 14px;
    padding: 8px 12px;
    background-color: var(--gray-50);
    border-left: 3px solid var(--gray-300);
    border-radius: 4px;
  }

  .err-msg {
    color: var(--color-error-500);
    border: 1px solid currentColor;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    text-align: left;
    background: var(--color-error-50);
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
    border: 1px solid var(--gray-150);
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

  .error-hint {
    margin: 10px 0;
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    background-color: var(--color-error-50);
    // border: 1px solid #f87171;
    color: var(--color-error-500);
    span {
      line-height: 1.5;
    }
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
    outline: 1px solid var(--gray-150);
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
        color: var(--color-success-500);
      }

      .tool-loader.tool-error {
        color: var(--color-error-500);
      }

      .tool-loader.tool-loading {
        color: var(--color-info-500);
      }

      .tool-expand-icon {
        margin-left: auto;
        color: var(--gray-400);
        display: flex;
        align-items: center;
      }
    }

    .tool-content {
      transition: all 0.3s ease;

      .tool-params {
        padding: 8px 12px;
        background-color: var(--gray-25);
        border-bottom: 1px solid var(--gray-150);

        .tool-params-content {
          margin: 0;
          font-size: 12px;
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
  color: var(--gray-600);
  font-size: 14px;
  text-align: left;
}

.retry-link {
  color: var(--color-info-500);
  cursor: pointer;
  margin-left: 4px;

  &:hover {
    text-decoration: underline;
  }
}

.ant-btn-icon-only {
  &:has(.anticon-stop) {
    background-color: var(--color-error-500) !important;

    &:hover {
      background-color: var(--color-error-100) !important;
    }
  }
}

@keyframes colorPulse {
  0% {
    color: var(--gray-700);
  }
  50% {
    color: var(--gray-300);
  }
  100% {
    color: var(--gray-700);
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

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

// 多模态消息样式
.message-image {
  border-radius: 12px;
  overflow: hidden;
  margin-left: auto;
  // max-height: 200px;
  border: 1px solid rgba(255, 255, 255, 0.2);

  img {
    max-width: 100%;
    max-height: 200px;
    object-fit: contain;
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
  font-family:
    -apple-system, BlinkMacSystemFont, 'Noto Sans SC', 'PingFang SC', 'Noto Sans SC',
    'Microsoft YaHei', 'Hiragino Sans GB', 'Source Han Sans CN', 'Courier New', monospace;

  #preview-only-preview {
    font-size: 1rem;
    line-height: 1.75;
    color: var(--gray-1000);
  }

  h1,
  h2 {
    font-size: 1.2rem;
  }

  h3,
  h4 {
    font-size: 1.1rem;
  }

  h5,
  h6 {
    font-size: 1rem;
  }

  strong {
    font-weight: 500;
  }

  li > p,
  ol > p,
  ul > p {
    margin: 0.25rem 0;
  }

  ul li::marker,
  ol li::marker {
    color: var(--main-bright);
  }

  ul,
  ol {
    padding-left: 1.625rem;
  }

  cite {
    font-size: 12px;
    color: var(--gray-800);
    font-style: normal;
    background-color: var(--gray-200);
    border-radius: 4px;
    outline: 2px solid var(--gray-200);
    padding: 0rem 0.25rem;
    margin-left: 4px;
    cursor: pointer;
    user-select: none;
    position: relative;

    &:hover::after {
      content: attr(source);
      position: absolute;
      bottom: calc(100% + 6px);
      left: 50%;
      transform: translateX(-50%);
      padding: 8px 12px;
      background-color: #222;
      color: #fff;
      font-size: 13px;
      line-height: 1.5;
      border-radius: 6px;
      min-width: 100px;
      max-width: 400px;
      width: max-content;
      white-space: normal;
      word-break: break-word;
      z-index: 1000;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
      pointer-events: none;
      text-align: center;
    }

    &:hover::before {
      content: '';
      position: absolute;
      bottom: 100%;
      left: 50%;
      transform: translateX(-50%);
      border: 5px solid transparent;
      border-top-color: var(--gray-900);
      z-index: 1000;
    }
  }

  a {
    color: var(--main-700);
  }

  .md-editor-code {
    border: var(--gray-50);
    border-radius: 8px;

    .md-editor-code-head {
      background-color: var(--gray-50);
      z-index: 1;

      .md-editor-collapse-tips {
        color: var(--gray-400);
      }
    }
  }

  code {
    font-size: 13px;
    font-family:
      'Menlo', 'Monaco', 'Consolas', 'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei',
      'Hiragino Sans GB', 'Source Han Sans CN', 'Courier New', monospace;
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
    margin: 2em 0;
    font-size: 15px;
    display: table;
    outline: 1px solid var(--gray-100);
    outline-offset: 14px;
    border-radius: 12px;

    thead tr th {
      padding-top: 0;
    }

    thead th,
    tbody th {
      border: none;
      border-bottom: 1px solid var(--gray-200);
    }

    tbody tr:last-child td {
      border-bottom: 1px solid var(--gray-200);
      border: none;
      padding-bottom: 0;
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

  h1,
  h2 {
    font-size: 1.1rem;
  }

  h3,
  h4 {
    font-size: 1rem;
  }
}

:deep(.chat-box.font-larger #preview-only-preview) {
  font-size: 16px;

  h1,
  h2 {
    font-size: 1.3rem;
  }

  h3,
  h4 {
    font-size: 1.2rem;
  }

  h5,
  h6 {
    font-size: 1.1rem;
  }

  code {
    font-size: 14px;
  }
}
</style>
