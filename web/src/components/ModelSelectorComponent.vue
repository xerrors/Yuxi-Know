<template>
  <a-dropdown trigger="click">
    <div class="model-select" @click.prevent>
      <div class="model-select-content">
        <div class="model-info">
          <a-tooltip :title="model_name" placement="right">
            <span class="model-text text"> {{ model_name }} </span>
          </a-tooltip>
          <span class="model-provider">{{ model_provider }}</span>
        </div>
        <div class="model-status-controls">
          <span
            v-if="currentModelStatus"
            class="model-status-indicator"
            :class="currentModelStatus.status"
            :title="getCurrentModelStatusTooltip()"
          >
            {{ modelStatusIcon }}
          </span>
          <a-button
            size="small"
            type="text"
            :loading="state.checkingStatus"
            @click.stop="checkCurrentModelStatus"
            :disabled="state.checkingStatus"
            class="status-check-button"
          >
            {{ state.checkingStatus ? '检查中...' : '检查' }}
          </a-button>
        </div>
      </div>
    </div>
    <template #overlay>
      <a-menu class="scrollable-menu">
        <a-menu-item-group v-for="(item, key) in modelKeys" :key="key" :title="modelNames[item]?.name">
          <a-menu-item v-for="(model, idx) in modelNames[item]?.models" :key="`${item}-${idx}`" @click="handleSelectModel(item, model)">
            {{ model }}
          </a-menu-item>
        </a-menu-item-group>
        <a-menu-item-group v-if="customModels.length > 0" title="自定义模型">
          <a-menu-item v-for="(model, idx) in customModels" :key="`custom-${idx}`" @click="handleSelectModel('custom', model.custom_id)">
            custom/{{ model.custom_id }}
          </a-menu-item>
        </a-menu-item-group>
      </a-menu>
    </template>
  </a-dropdown>
</template>

<script setup>
import { computed, reactive } from 'vue'
import { useConfigStore } from '@/stores/config'
import { chatModelApi } from '@/apis/system_api'

const props = defineProps({
  model_name: {
    type: String,
    default: ''
  },
  model_provider: {
    type: String,
    default: ''
  }
});

const configStore = useConfigStore()
const emit = defineEmits(['select-model'])

// 状态管理
const state = reactive({
  currentModelStatus: null, // 当前模型状态
  checkingStatus: false // 是否正在检查状态
})

// 从configStore中获取所需数据
const modelNames = computed(() => configStore.config?.model_names)
const modelStatus = computed(() => configStore.config?.model_provider_status)
const customModels = computed(() => configStore.config?.custom_models || [])

// 筛选 modelStatus 中为真的key
const modelKeys = computed(() => {
  return Object.keys(modelStatus.value || {}).filter(key => modelStatus.value?.[key])
})

// 当前模型状态
const currentModelStatus = computed(() => {
  return state.currentModelStatus
})

// 检查当前模型状态
const checkCurrentModelStatus = async () => {
  if (!props.model_provider || !props.model_name) return

  try {
    state.checkingStatus = true
    const response = await chatModelApi.getModelStatus(props.model_provider, props.model_name)
    if (response.status) {
      state.currentModelStatus = response.status
    } else {
      state.currentModelStatus = null
    }
  } catch (error) {
    console.error(`检查当前模型 ${props.model_provider}/${props.model_name} 状态失败:`, error)
    state.currentModelStatus = { status: 'error', message: error.message }
  } finally {
    state.checkingStatus = false
  }
}

const modelStatusIcon = computed(() => {
  const status = currentModelStatus.value
  if (!status) return '○'
  if (status.status === 'available') return '✓'
  if (status.status === 'unavailable') return '✗'
  if (status.status === 'error') return '⚠'
  return '○'
})


// 获取当前模型状态提示文本
const getCurrentModelStatusTooltip = () => {
  const status = currentModelStatus.value
  if (!status) return '状态未知'

  let statusText = ''
  if (status.status === 'available') statusText = '可用'
  else if (status.status === 'unavailable') statusText = '不可用'
  else if (status.status === 'error') statusText = '错误'

  const message = status.message || '无详细信息'
  return `${statusText}: ${message}`
}


// 选择模型的方法
const handleSelectModel = async (provider, name) => {
  emit('select-model', { provider, name })
}

</script>

<style lang="less" scoped>
// 变量定义
@status-success: #52c41a;
@status-error: #ff4d4f;
@status-warning: #faad14;
@status-default: #999;
@border-radius: 8px;
@scrollbar-width: 6px;
@status-indicator-padding: 2px 4px;
@status-check-button-padding: 0 4px;
@status-check-button-font-size: 12px;
@status-indicator-font-size: 11px;
@model-provider-color: #aaa;

// 主选择器样式
.model-select {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 4px 8px;
  cursor: pointer;
  border: 1px solid var(--gray-200);
  border-radius: @border-radius;
  background-color: white;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;

  // 修饰符类
  &.borderless {
    border: none;
  }

  &.max-width {
    max-width: 380px;
  }

  // 内容区域
  .model-select-content {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    width: 100%;

    // 模型信息区域
    .model-info {
      flex: 1;
      min-width: 0;
      overflow: hidden;

      .model-text {
        overflow: hidden;
        text-overflow: ellipsis;
        color: #000;
        white-space: nowrap;
      }

      .model-provider {
        color: @model-provider-color;
        margin-left: 4px;
      }
    }

    // 状态控制区域
    .model-status-controls {
      display: flex;
      align-items: center;
      gap: 4px;
      flex: 0;
      margin-left: auto;

      // 状态指示器
      .model-status-indicator {
        font-size: @status-indicator-font-size;
        font-weight: bold;
        padding: @status-indicator-padding;
        border-radius: 3px;

        // 状态样式修饰符
        &.available {
          color: @status-success;
        }

        &.unavailable {
          color: @status-error;
        }

        &.error {
          color: @status-warning;
        }
      }

      // 检查按钮
      .status-check-button {
        font-size: @status-check-button-font-size;
        padding: @status-check-button-padding;
      }
    }
  }
}

// 滚动菜单样式
.scrollable-menu {
  max-height: 300px;
  overflow-y: auto;

  // 自定义滚动条样式
  &::-webkit-scrollbar {
    width: @scrollbar-width;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--gray-400);
    border-radius: 3px;

    &:hover {
      background: var(--gray-500);
    }
  }
}
</style>

<style lang="less" scoped>
// 将全局样式移到scoped中以避免样式污染
:deep(.ant-dropdown-menu) {
  &.scrollable-menu {
    max-height: 300px;
    overflow-y: auto;
  }
}
</style>