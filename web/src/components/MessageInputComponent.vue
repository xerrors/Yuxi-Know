<template>
  <div class="input-box" :class="[customClasses, { 'single-line': isSingleLine }]" @click="focusInput">
    <div class="expand-options" v-if="hasOptionsLeft">
      <a-popover
        v-model:open="optionsExpanded"
        placement="bottomLeft"
        trigger="click"
      >
        <template #content>
          <div class="popover-options">
            <slot name="options-left">
              <div class="no-options">没有配置 options</div>
            </slot>
          </div>
        </template>
        <a-button
          type="text"
          size="small"
          class="expand-btn"
        >
          <template #icon>
            <PlusOutlined :class="{ 'rotated': optionsExpanded }" />
          </template>
        </a-button>
      </a-popover>
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
      <a-tooltip :title="isLoading ? '停止回答' : ''">
        <a-button
          @click="handleSendOrStop"
          :disabled="sendButtonDisabled"
          type="link"
          class="send-button"
        >
          <template #icon>
            <component :is="getIcon" class="send-btn"/>
          </template>
        </a-button>
      </a-tooltip>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, toRefs, onMounted, nextTick, watch, onBeforeUnmount } from 'vue';
import {
  SendOutlined,
  ArrowUpOutlined,
  LoadingOutlined,
  PauseOutlined,
  PlusOutlined
} from '@ant-design/icons-vue';


const inputRef = ref(null);
const isSingleLine = ref(true);
const optionsExpanded = ref(false);
const hasOptionsLeft = ref(false);
const singleLineHeight = ref(0); // Add this
// 用于防抖的定时器
const debounceTimer = ref(null);
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
  }
});

const emit = defineEmits(['update:modelValue', 'send', 'keydown']);

// 图标映射
const iconComponents = {
  'SendOutlined': SendOutlined,
  'ArrowUpOutlined': ArrowUpOutlined,
  'PauseOutlined': PauseOutlined
};

// 根据传入的图标名动态获取组件
const getIcon = computed(() => {
  if (props.isLoading) {
    return PauseOutlined;
  }
  return iconComponents[props.sendIcon] || ArrowUpOutlined;
});

// 创建本地引用以进行双向绑定
const inputValue = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
});

// 处理键盘事件
const handleKeyPress = (e) => {
  emit('keydown', e);
};

// 处理输入事件
const handleInput = (e) => {
  const value = e.target.value;
  emit('update:modelValue', value);
};

// 处理发送按钮点击
const handleSendOrStop = () => {
  emit('send');
};

// 用于存储固定的单行宽度基准
const singleLineWidth = ref(0);

// 检查行数
const checkLineCount = () => {
  if (!inputRef.value || singleLineHeight.value === 0) {
    return;
  }
  const textarea = inputRef.value;
  const content = inputValue.value;

  // 主要判断依据：内容是否包含换行符
  const hasNewlines = content.includes('\n');

  // 辅助判断：内容是否超出单行宽度（使用固定的单行宽度基准）
  let contentExceedsWidth = false;
  if (!hasNewlines && content.trim() && singleLineWidth.value > 0) {
    // 使用固定的单行宽度作为测量基准，避免因模式切换导致的宽度变化
    const measureDiv = document.createElement('div');
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
    `;
    measureDiv.textContent = content;
    document.body.appendChild(measureDiv);

    // 检查内容是否会换行（基于固定的单行宽度）
    contentExceedsWidth = measureDiv.scrollWidth > measureDiv.clientWidth;
    document.body.removeChild(measureDiv);
  }

  const shouldBeMultiLine = hasNewlines || contentExceedsWidth;
  isSingleLine.value = !shouldBeMultiLine;

  // 根据模式调整高度
  if (shouldBeMultiLine) {
    // 多行模式：让textarea自适应内容高度
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.max(textarea.scrollHeight, singleLineHeight.value)}px`;
  } else {
    // 单行模式：清除内联样式，让CSS控制高度
    textarea.style.height = '';
  }
};



// 聚焦输入框
const focusInput = () => {
  if (inputRef.value && !props.disabled) {
    inputRef.value.focus();
  }
};

// 检查是否有左侧选项
const checkOptionsLeft = () => {
  // 这里可以通过检查slot内容来判断是否有选项
  // 暂时设为true，实际使用时可以根据slot内容动态判断
  hasOptionsLeft.value = true;
};

// 监听输入值变化
watch(inputValue, () => {
  nextTick(() => {
    checkLineCount();
  });
});

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
  checkOptionsLeft();
  nextTick(() => {
    if (inputRef.value) {
      // 记录单行模式下的高度和宽度基准
      singleLineHeight.value = inputRef.value.clientHeight;
      singleLineWidth.value = inputRef.value.clientWidth;
      checkLineCount();
      inputRef.value.focus();
    }
  });
  // observeTextareaResize();
});

// 组件卸载时清除定时器
onBeforeUnmount(() => {
  if (debounceTimer.value) {
    clearTimeout(debounceTimer.value);
  }
});

</script>

<style lang="less" scoped>
.input-box {
  display: grid;
  width: 100%;
  margin: 0 auto;
  border: 1px solid var(--gray-200);
  border-radius: 0.8rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  transition: all 0.3s ease;
  gap: 8px;

  /* Default: Multi-line layout */
  padding: 0.8rem 0.75rem 0.6rem 0.75rem;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  grid-template-areas:
    "input input"
    "options send";

  .expand-options {
    justify-self: start;
  }
  .send-button-container {
    justify-self: end;
  }

  // &:focus-within {
  //   border-color: var(--main-500);
  //   background: white;
  //   box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  // }

  &.single-line {
    padding: 0.75rem 0.75rem;
    grid-template-columns: auto 1fr auto;
    grid-template-rows: 1fr;
    grid-template-areas: "options input send";
    align-items: center;

    .user-input {
      min-height: 24px;
      height: 24px; /* Fix height for single line */
      align-self: center;
      white-space: nowrap;
      overflow: hidden;
    }

    .expand-options, .send-button-container {
      align-self: center;
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
  color: #222222;
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
    color: #888888;
  }
}

.send-button-container {
  grid-area: send;
  display: flex;
  align-items: center;
  justify-content: center;
}

.expand-btn {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--gray-600);
  transition: all 0.2s ease;

  &:hover {
    background-color: var(--gray-100);
    color: var(--main-500);
  }

  .anticon {
    font-size: 12px;
    transition: transform 0.2s ease;

    &.rotated {
      transform: rotate(45deg);
    }
  }
}

// Popover 选项样式
.popover-options {
  min-width: 200px;
  max-width: 300px;

  .no-options {
    color: var(--gray-700);
    font-size: 12px;
    text-align: center;
  }

  :deep(.opt-item) {
    border-radius: 12px;
    border: 1px solid var(--gray-300);
    padding: 5px 10px;
    cursor: pointer;
    font-size: 12px;
    color: var(--gray-700);
    transition: all 0.2s ease;
    margin: 4px;
    display: inline-block;

    &:hover {
      background-color: var(--main-10);
      color: var(--main-color);
    }

    &.active {
      color: var(--main-color);
      border: 1px solid var(--main-500);
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
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
  color: white;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;

  &:hover {
    background-color: var(--main-color);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
    color: white;
  }

  &:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  &:disabled {
    background-color: var(--gray-400);
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