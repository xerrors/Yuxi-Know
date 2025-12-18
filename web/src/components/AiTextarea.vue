<template>
  <div class="ai-textarea-wrapper">
    <a-textarea
      :value="modelValue"
      @update:value="$emit('update:modelValue', $event)"
      :placeholder="placeholder"
      :rows="rows"
      :auto-size="autoSize"
    />
    <a-tooltip v-if="name" title="使用 AI 生成或优化描述">
      <a-button
        class="ai-btn"
        type="text"
        size="small"
        :loading="loading"
        @click="generateDescription"
      >
        <template #icon>
          <svg v-if="!loading" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
          </svg>
        </template>
        <span v-if="!loading" class="ai-text">AI</span>
      </a-button>
    </a-tooltip>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { databaseApi } from '@/apis/knowledge_api'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  name: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: ''
  },
  rows: {
    type: Number,
    default: 4
  },
  autoSize: {
    type: [Boolean, Object],
    default: false
  }
})

const emit = defineEmits(['update:modelValue'])

const loading = ref(false)

const generateDescription = async () => {
  if (!props.name?.trim()) {
    message.warning('请先输入知识库名称')
    return
  }

  loading.value = true
  try {
    const result = await databaseApi.generateDescription(props.name, props.modelValue)
    if (result.status === 'success' && result.description) {
      emit('update:modelValue', result.description)
      message.success('描述生成成功')
    } else {
      message.error(result.message || '生成失败')
    }
  } catch (error) {
    console.error('生成描述失败:', error)
    message.error(error.message || '生成描述失败')
  } finally {
    loading.value = false
  }
}
</script>

<style lang="less" scoped>
.ai-textarea-wrapper {
  position: relative;

  .ai-btn {
    position: absolute;
    top: 4px;
    right: 4px;
    z-index: 1;
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 2px 6px;
    height: 24px;
    color: var(--main-color);
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 4px;
    font-size: 12px;
    transition: all 0.2s ease;

    &:hover {
      background: var(--main-10);
      border-color: var(--main-color);
    }

    .ai-text {
      font-weight: 500;
    }
  }

  :deep(.ant-input) {
    padding-right: 50px;
  }
}
</style>
