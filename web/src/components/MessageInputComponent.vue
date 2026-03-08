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
      @keyup="handleKeyUp"
      @input="handleInput"
      @focus="focusInput"
      :placeholder="placeholder"
      :disabled="disabled"
    />

    <!-- @ 提及选择弹窗 -->
    <div
      v-if="mentionPopupVisible"
      ref="mentionDropdownRef"
      class="mention-dropdown-wrapper"
      :style="mentionDropdownStyle"
    >
      <div class="mention-popup">
        <!-- 文件列表 -->
        <div v-if="mentionItems.files.length > 0" class="mention-group">
          <div class="mention-group-title">文件</div>
          <div
            v-for="(item, index) in mentionItems.files"
            :key="'file-' + item.value"
            :class="['mention-item', { active: isItemSelected('file', index) }]"
            @click="insertMention(item)"
          >
            {{ item.label }}
          </div>
        </div>

        <!-- 知识库列表 -->
        <div v-if="mentionItems.knowledgeBases.length > 0" class="mention-group">
          <div class="mention-group-title">知识库</div>
          <div
            v-for="(item, index) in mentionItems.knowledgeBases"
            :key="'kb-' + item.value"
            :class="['mention-item', { active: isItemSelected('knowledge', index) }]"
            @click="insertMention(item)"
          >
            {{ item.label }}
          </div>
        </div>

        <!-- MCP 列表 -->
        <div v-if="mentionItems.mcps.length > 0" class="mention-group">
          <div class="mention-group-title">MCP</div>
          <div
            v-for="(item, index) in mentionItems.mcps"
            :key="'mcp-' + item.value"
            :class="['mention-item', { active: isItemSelected('mcp', index) }]"
            @click="insertMention(item)"
          >
            {{ item.label }}
          </div>
        </div>

        <!-- 无结果 -->
        <div v-if="!hasAnyItems" class="mention-empty">暂无可引用的项</div>
      </div>
    </div>

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
import {
  ref,
  computed,
  onMounted,
  nextTick,
  watch,
  onBeforeUnmount,
  useSlots,
  onUnmounted
} from 'vue'
import {
  SendOutlined,
  ArrowUpOutlined,
  LoadingOutlined,
  PauseOutlined,
  PlusOutlined
} from '@ant-design/icons-vue'

// 点击外部关闭下拉框
const mentionDropdownRef = ref(null)
const closeMentionPopup = (e) => {
  if (!mentionPopupVisible.value) return
  if (inputRef.value?.contains(e.target)) return
  if (mentionDropdownRef.value?.contains(e.target)) return
  mentionPopupVisible.value = false
}

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
  },
  mention: {
    type: Object,
    default: () => null
  }
})

const emit = defineEmits(['update:modelValue', 'send', 'keydown'])
const slots = useSlots()

// @ 提及功能是否启用
const mentionEnabled = computed(() => {
  if (!props.mention) return false
  const { files, knowledgeBases, mcps } = props.mention
  return (
    (Array.isArray(files) && files.length > 0) ||
    (Array.isArray(knowledgeBases) && knowledgeBases.length > 0) ||
    (Array.isArray(mcps) && mcps.length > 0)
  )
})

// 检测是否在 @ 触发位置
const checkMentionTrigger = (textarea) => {
  console.log(
    '[Mention] checkMentionTrigger called, textarea:',
    !!textarea,
    'mentionEnabled:',
    mentionEnabled.value
  )
  if (!textarea || !mentionEnabled.value) return false

  const cursorPos = textarea.selectionStart
  const textBeforeCursor = inputValue.value.slice(0, cursorPos)
  console.log('[Mention] textBeforeCursor:', JSON.stringify(textBeforeCursor))

  // 检查是否以 @ 结尾（刚输入 @）或 @ 后有内容
  const atMatch = textBeforeCursor.match(/@(\S*)$/)
  console.log('[Mention] atMatch:', atMatch)
  if (atMatch) {
    mentionQuery.value = atMatch[1]
    mentionPopupVisible.value = true
    mentionSelectedIndex.value = 0
    updateMentionItems(mentionQuery.value)
    console.log('[Mention] popup should be visible now')
    return true
  }

  mentionPopupVisible.value = false
  return false
}

// 更新提及候选项
const updateMentionItems = (query = '') => {
  if (!props.mention) {
    mentionItems.value = { files: [], knowledgeBases: [], mcps: [] }
    return
  }

  const lowerQuery = query.toLowerCase()
  const { files = [], knowledgeBases = [], mcps = [] } = props.mention

  const filter = (list) =>
    list.filter((item) => {
      const label = item.path || item.name || ''
      return label.toLowerCase().includes(lowerQuery)
    })

  mentionItems.value = {
    files: filter(files).map((f) => ({
      value: f.path,
      label: f.path.split('/').pop() || f.path,
      type: 'file',
      description: f.path
    })),
    knowledgeBases: filter(knowledgeBases).map((kb) => ({
      value: kb.name,
      label: kb.name,
      type: 'knowledge',
      description: kb.db_id
    })),
    mcps: filter(mcps).map((m) => ({
      value: m.name,
      label: m.name,
      type: 'mcp',
      description: m.description || ''
    }))
  }
}

// 检查项是否被选中
const isItemSelected = (type, index) => {
  if (mentionSelectedIndex.value < 0) return false

  const filesLen = mentionItems.value.files.length
  const kbLen = mentionItems.value.knowledgeBases.length

  if (type === 'file') {
    return mentionSelectedIndex.value === index
  } else if (type === 'knowledge') {
    return mentionSelectedIndex.value === filesLen + index
  } else {
    return mentionSelectedIndex.value === filesLen + kbLen + index
  }
}

// 是否有任何候选项
const hasAnyItems = computed(() => {
  const items = mentionItems.value
  return items.files.length > 0 || items.knowledgeBases.length > 0 || items.mcps.length > 0
})

// 获取弹出框位置
const mentionDropdownStyle = computed(() => {
  if (!inputRef.value) return {}

  const textarea = inputRef.value
  const rect = textarea.getBoundingClientRect()
  const parentRect = textarea.parentElement.getBoundingClientRect()

  return {
    position: 'absolute',
    bottom: `${parentRect.bottom - rect.top + 4}px`,
    left: `${rect.left - parentRect.left}px`,
    zIndex: 1000
  }
})
const insertMention = (item) => {
  if (!inputRef.value) return

  const textarea = inputRef.value
  const cursorPos = textarea.selectionStart
  const textBeforeCursor = inputValue.value.slice(0, cursorPos)

  // 移除 @ 及后面的查询内容，插入完整的提及项
  const newTextBefore = textBeforeCursor.replace(/@(\S*)$/, `@${item.value} `)
  const textAfterCursor = inputValue.value.slice(cursorPos)

  const newValue = newTextBefore + textAfterCursor
  emit('update:modelValue', newValue)

  // 重置光标位置到插入内容之后
  nextTick(() => {
    const newCursorPos = newTextBefore.length
    textarea.setSelectionRange(newCursorPos, newCursorPos)
    textarea.focus()
  })

  mentionPopupVisible.value = false
  mentionQuery.value = ''
}

// 滚动到选中项
const scrollToItem = (index) => {
  nextTick(() => {
    const popup = mentionDropdownRef.value?.querySelector('.mention-popup')
    if (!popup) return

    // 查找所有 mention-item 元素
    const items = popup.querySelectorAll('.mention-item')
    const selectedItem = items[index]

    if (selectedItem) {
      // 检查元素是否在可视区域内
      const popupRect = popup.getBoundingClientRect()
      const itemRect = selectedItem.getBoundingClientRect()

      if (itemRect.bottom > popupRect.bottom) {
        selectedItem.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      } else if (itemRect.top < popupRect.top) {
        selectedItem.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      }
    }
  })
}

// 处理键盘导航
const handleMentionNavigation = (e) => {
  if (!mentionPopupVisible.value) return

  const allItems = [
    ...mentionItems.value.files,
    ...mentionItems.value.knowledgeBases,
    ...mentionItems.value.mcps
  ]

  const total = allItems.length
  if (total === 0) return

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    mentionSelectedIndex.value = (mentionSelectedIndex.value + 1) % total
    scrollToItem(mentionSelectedIndex.value)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    mentionSelectedIndex.value = (mentionSelectedIndex.value - 1 + total) % total
    scrollToItem(mentionSelectedIndex.value)
  } else if (e.key === 'Enter' || e.key === 'Tab') {
    if (mentionSelectedIndex.value >= 0 && mentionSelectedIndex.value < total) {
      e.preventDefault()
      insertMention(allItems[mentionSelectedIndex.value])
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    mentionPopupVisible.value = false
  }
}

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
  // @ 提及键盘导航
  if (mentionPopupVisible.value) {
    if (['ArrowDown', 'ArrowUp', 'Enter', 'Tab', 'Escape'].includes(e.key)) {
      handleMentionNavigation(e)
      return
    }
  }

  emit('keydown', e)
}

// 检测 @ 触发
const handleKeyUp = (e) => {
  if (e.key === '@' && mentionEnabled.value) {
    console.log(
      '[Mention] @ detected, mentionEnabled:',
      mentionEnabled.value,
      'mention:',
      props.mention
    )
    nextTick(() => {
      checkMentionTrigger(e.target)
    })
  }
}

// 处理输入事件
const handleInput = (e) => {
  const value = e.target.value
  emit('update:modelValue', value)

  // 检测 @ 触发（每次输入后检查）
  if (mentionEnabled.value && !mentionPopupVisible.value) {
    const cursorPos = e.target.selectionStart
    const textBeforeCursor = value.slice(0, cursorPos)
    if (textBeforeCursor.endsWith('@')) {
      console.log('[Mention] @ detected via input event')
      checkMentionTrigger(e.target)
    }
  }

  // 如果弹出框打开，更新查询结果
  if (mentionPopupVisible.value) {
    nextTick(() => {
      checkMentionTrigger(e.target)
    })
  }
}

// 处理发送按钮点击
const handleSendOrStop = () => {
  emit('send')
}

// 用于存储固定的单行宽度基准
const singleLineWidth = ref(0)

// @ 提及功能状态
const mentionPopupVisible = ref(false)
const mentionQuery = ref('')
const mentionItems = ref({ files: [], knowledgeBases: [], mcps: [] })
const mentionSelectedIndex = ref(0)

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
  document.addEventListener('click', closeMentionPopup)
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

// 组件卸载时清除定时器和事件监听器
onBeforeUnmount(() => {
  if (debounceTimer.value) {
    clearTimeout(debounceTimer.value)
  }
  document.removeEventListener('click', closeMentionPopup)
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
  position: relative;

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
    // 移除点击缩小效果
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
    box-shadow: 0 2px 4px var(--shadow-2);
    // 移除点击动画效果
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

// @ 提及弹窗样式
.mention-dropdown-wrapper {
  position: absolute;
  z-index: 1000;
}

.mention-popup {
  min-width: 240px;
  max-height: 280px;
  overflow-y: auto;
  background: var(--gray-0);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  border: 1px solid var(--gray-200);

  .mention-group {
    margin-bottom: 4px;

    &:last-child {
      margin-bottom: 0;
    }
  }

  .mention-group-title {
    font-size: 12px;
    color: var(--gray-500);
    padding: 4px 8px;
    display: flex;
    align-items: center;
    gap: 4px;
    border-bottom: 1px solid var(--gray-100);
    margin-bottom: 2px;
  }

  .mention-item {
    padding: 4px 8px;
    cursor: pointer;
    font-size: 13px;
    color: var(--gray-700);
    transition: all 0.15s ease;
    margin: 1px 4px;
    border-radius: 4px;

    &:hover,
    &.active {
      background-color: var(--main-10);
      color: var(--main-600);
    }
  }

  .mention-empty {
    text-align: center;
    padding: 12px 8px;
    color: var(--gray-400);
    font-size: 13px;
  }
}
</style>
