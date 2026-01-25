<template>
  <div
    class="input-box"
    :class="[customClasses, { 'single-line': isSingleLine }]"
    @click="focusInput"
  >
    <div class="top-slot">
      <slot name="top"></slot>
    </div>

    <div class="expand-options" v-if="hasOptionsLeft">
      <a-popover
        v-model:open="optionsExpanded"
        placement="bottomLeft"
        trigger="click"
        :overlay-inner-style="{ padding: '4px' }"
      >
        <template #content>
          <slot name="options-left">
            <div class="no-options">没有配置 options</div>
          </slot>
        </template>
        <a-button type="text" class="expand-btn">
          <template #icon>
            <PlusOutlined :class="{ rotated: optionsExpanded }" />
          </template>
        </a-button>
      </a-popover>
      <slot name="actions-left"></slot>
    </div>

    <textarea
      ref="inputRef"
      class="user-input"
      :value="inputValue"
      @keydown="handleKeyPress"
      @input="handleInput"
      @focus="focusInput"
      :placeholder="placeholder"
      :disabled="disabled"
    />

    <div class="send-button-container">
      <slot name="actions-right"></slot>
      <a-tooltip :title="isLoading ? '停止回答' : ''">
        <a-button
          @click="handleSendOrStop"
          :disabled="sendButtonDisabled"
          type="link"
          class="send-button"
        >
          <template #icon>
            <component :is="getIcon" class="send-btn" />
          </template>
        </a-button>
      </a-tooltip>
    </div>

    <div class="bottom-slot">
      <slot name="bottom"></slot>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch, onBeforeUnmount, useSlots } from 'vue'
import {
  SendOutlined,
  ArrowUpOutlined,
  LoadingOutlined,
  PauseOutlined,
  PlusOutlined
} from '@ant-design/icons-vue'

const inputRef = ref(null)
const optionsExpanded = ref(false)
const singleLineHeight = ref(0) // Add this
// 用于防抖的定时器
const debounceTimer = ref(null)
const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '输入问题...'
  },
  isLoading: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  sendButtonDisabled: {
    type: Boolean,
    default: false
  },
  autoSize: {
    type: Object,
    default: () => ({ minRows: 2, maxRows: 6 })
  },
  sendIcon: {
    type: String,
    default: 'ArrowUpOutlined'
  },
  customClasses: {
    type: Object,
    default: () => ({})
  },
  forceMultiLine: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'send', 'keydown'])
const slots = useSlots()

// Update isSingleLine logic to respect forceMultiLine
const isSingleLineMode = ref(true)
const isSingleLine = computed(() => {
  if (props.forceMultiLine) return false
  return isSingleLineMode.value
})

const hasOptionsLeft = computed(() => {
  const slot = slots['options-left']
  if (!slot) {
    return false
  }
  const renderedNodes = slot()
  return Boolean(renderedNodes && renderedNodes.length)
})

const hasActionsLeft = computed(() => {
  const slot = slots['actions-left']
  if (!slot) {
    return false
  }
  const renderedNodes = slot()
  return Boolean(renderedNodes && renderedNodes.length)
})

// 图标映射
const iconComponents = {
  SendOutlined: SendOutlined,
  ArrowUpOutlined: ArrowUpOutlined,
  PauseOutlined: PauseOutlined
}

// 根据传入的图标名动态获取组件
const getIcon = computed(() => {
  if (props.isLoading) {
    return PauseOutlined
  }
  return iconComponents[props.sendIcon] || ArrowUpOutlined
})

// 创建本地引用以进行双向绑定
const inputValue = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// 处理键盘事件
const handleKeyPress = (e) => {
  emit('keydown', e)
}

// 处理输入事件
const handleInput = (e) => {
  const value = e.target.value
  emit('update:modelValue', value)
}

// 处理发送按钮点击
const handleSendOrStop = () => {
  emit('send')
}

// 用于存储固定的单行宽度基准
const singleLineWidth = ref(0)

// 检查行数
const checkLineCount = () => {
  if (!inputRef.value || singleLineHeight.value === 0) {
    return
  }
  const textarea = inputRef.value
  const content = inputValue.value

  // 主要判断依据：内容是否包含换行符
  const hasNewlines = content.includes('\n')

  // 辅助判断：内容是否超出单行宽度（使用固定的单行宽度基准）
  let contentExceedsWidth = false
  if (!hasNewlines && content.trim() && singleLineWidth.value > 0) {
    // 使用固定的单行宽度作为测量基准，避免因模式切换导致的宽度变化
    const measureDiv = document.createElement('div')
    measureDiv.style.cssText = `
      position: absolute;
      visibility: hidden;
      white-space: nowrap;
      font-family: ${getComputedStyle(textarea).fontFamily};
      font-size: ${getComputedStyle(textarea).fontSize};
      line-height: ${getComputedStyle(textarea).lineHeight};
      padding: 0;
      border: none;
      width: ${singleLineWidth.value}px;
    `
    measureDiv.textContent = content
    document.body.appendChild(measureDiv)

    // 检查内容是否会换行（基于固定的单行宽度）
    contentExceedsWidth = measureDiv.scrollWidth > measureDiv.clientWidth
    document.body.removeChild(measureDiv)
  }

  const shouldBeMultiLine = hasNewlines || contentExceedsWidth
  isSingleLineMode.value = !shouldBeMultiLine

  // 根据模式调整高度
  if (shouldBeMultiLine || props.forceMultiLine) {
    // 多行模式：让textarea自适应内容高度
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.max(textarea.scrollHeight, singleLineHeight.value)}px`
  } else {
    // 单行模式：清除内联样式，让CSS控制高度
    textarea.style.height = ''
  }
}

// 聚焦输入框
const focusInput = () => {
  if (inputRef.value && !props.disabled) {
    inputRef.value.focus()
  }
}

// 监听输入值变化
watch(inputValue, () => {
  nextTick(() => {
    checkLineCount()
  })
})

// 监听输入框尺寸变化
/* const observeTextareaResize = () => {
  if (inputRef.value) {
    const textarea = inputRef.value;
    if (textarea) {
      // 创建 ResizeObserver 来监听文本域尺寸变化
      const resizeObserver = new ResizeObserver(() => {
        checkLineCount();
      });
      resizeObserver.observe(textarea);

      // 在组件卸载时断开观察器
      onBeforeUnmount(() => {
        resizeObserver.disconnect();
      });
    }
  }
}; */

// Wait for component to mount before setting up onStartTyping
onMounted(() => {
  // console.log('Component mounted');
  nextTick(() => {
    if (inputRef.value) {
      // 记录单行模式下的高度和宽度基准
      singleLineHeight.value = inputRef.value.clientHeight
      singleLineWidth.value = inputRef.value.clientWidth
      checkLineCount()
      inputRef.value.focus()
    }
  })
  // observeTextareaResize();
})

// 组件卸载时清除定时器
onBeforeUnmount(() => {
  if (debounceTimer.value) {
    clearTimeout(debounceTimer.value)
  }
})

// 公开方法供父组件调用
defineExpose({
  focus: () => inputRef.value?.focus(),
  closeOptions: () => {
    optionsExpanded.value = false
  }
})
</script>

<style lang="less" scoped>
.input-box {
  display: grid;
  width: 100%;
  margin: 0 auto;
  border: 1px solid var(--gray-150);
  border-radius: 0.8rem;
  box-shadow: 0 2px 8px var(--shadow-1);
  transition: all 0.3s ease;
  gap: 0px;

  /* Default: Multi-line layout with top/bottom slots */
  padding: 0.8rem 0.75rem 0.6rem 0.75rem;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto auto;
  grid-template-areas:
    'top top'
    'input input'
    'options send';

  .top-slot {
    display: flex;
    grid-area: top;
  }

  .expand-options {
    grid-area: options;
    justify-self: start;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .user-input {
    grid-area: input;
  }

  .send-button-container {
    grid-area: send;
    justify-self: end;
  }

  .bottom-slot {
    grid-column: 1 / -1;
  }

  // &:focus-within {
  //   border-color: var(--main-500);
  //   background: var(--gray-0);
  //   box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  // }

  &.single-line {
    padding: 0.75rem 0.75rem;
    grid-template-columns: auto 1fr auto;
    grid-template-rows: auto 1fr auto;
    grid-template-areas:
      'top top top'
      'options input send'
      'bottom bottom bottom';
    align-items: center;
    gap: 0px;

    .user-input {
      min-height: 24px;
      height: 24px; /* Fix height for single line */
      align-self: center;
      white-space: nowrap;
      overflow: hidden;
      margin-bottom: 0rem;
    }

    .expand-options,
    .send-button-container {
      align-self: center;
    }

    .expand-options {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .top-slot {
      grid-area: top;
    }

    .bottom-slot {
      grid-area: bottom;
    }
  }
}

.expand-options {
  grid-area: options;
  display: flex;
  align-items: center;
}

.user-input {
  grid-area: input;
  width: 100%;
  padding: 0;
  background-color: transparent;
  border: none;
  margin: 0;
  margin-bottom: 0.5rem;
  color: var(--gray-1000);
  font-size: 15px;
  outline: none;
  resize: none;
  line-height: 1.5;
  font-family: inherit;
  min-height: 44px; /* Default min-height for multi-line */
  max-height: 200px;

  &:focus {
    outline: none;
    box-shadow: none;
  }

  &::placeholder {
    color: var(--gray-400);
  }
}

.send-button-container {
  grid-area: send;
  display: flex;
  align-items: center;
  justify-content: center;
}

.expand-btn {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--gray-600);
  transition: all 0.2s ease;
  border: 1px solid transparent;
  background-color: transparent;

  &:hover {
    color: var(--main-color);
  }

  &:active {
    color: var(--main-color);
    transform: scale(0.95);
  }

  .anticon {
    font-size: 14px;
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);

    &.rotated {
      transform: rotate(45deg);
    }
  }
}

// Popover 选项样式
.popover-options {
  min-width: 160px;
  max-width: 200px;
  padding: 4px;

  .no-options {
    color: var(--gray-500);
    font-size: 12px;
    text-align: center;
    padding: 12px 8px;
  }

  :deep(.opt-item) {
    border-radius: 8px;
    padding: 6px 10px;
    cursor: pointer;
    font-size: 12px;
    color: var(--gray-700);
    transition: all 0.2s ease;
    margin: 2px;
    display: inline-block;

    &:hover {
      background-color: var(--main-10);
      color: var(--main-600);
    }

    &.active {
      color: var(--main-600);
      background-color: var(--main-10);
    }
  }
}

.send-button.ant-btn-icon-only {
  height: 32px;
  width: 32px;
  cursor: pointer;
  background-color: var(--main-500);
  border-radius: 50%;
  border: none;
  transition: all 0.2s ease;
  box-shadow: 0 2px 6px var(--shadow-2);
  color: var(--gray-0);
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;

  &:hover {
    background-color: var(--main-color);
    box-shadow: 0 4px 8px var(--shadow-3);
    color: var(--gray-0);
  }

  &:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px var(--shadow-2);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }
}

@media (max-width: 520px) {
  .input-box {
    border-radius: 15px;
    padding: 0.625rem 0.875rem;
  }
}
</style>
