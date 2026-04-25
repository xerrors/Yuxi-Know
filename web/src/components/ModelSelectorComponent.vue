<template>
  <a-dropdown trigger="click">
    <div class="model-select" :class="modelSelectClasses" @click.prevent>
      <div class="model-select-content">
        <div class="model-info">
          <a-tooltip :title="displayModelText" placement="right">
            <span class="model-text text"> {{ displayModelText }} </span>
          </a-tooltip>
        </div>
        <div class="model-status-controls">
          <span
            v-if="state.currentModelStatus"
            class="model-status-indicator"
            :class="state.currentModelStatus.status"
            :title="getCurrentModelStatusTooltip()"
          >
            {{ modelStatusIcon }}
          </span>
          <a-button
            :size="buttonSize"
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
        <!-- v2 模型列表（新版本，优先显示） -->
        <a-menu-item-group v-for="(providerData, providerId) in v2Models" :key="`v2-${providerId}`">
          <template #title>
            <span>{{ providerId }}</span>
            <a-tag color="success" size="small" class="provider-tag">v2</a-tag>
          </template>
          <a-menu-item
            v-for="model in providerData.models"
            :key="model.spec"
            @click="handleSelectV2Model(model.spec)"
          >
            {{ model.display_name }}
          </a-menu-item>
        </a-menu-item-group>

        <!-- v1 模型列表（Legacy，弱化处理） -->
        <a-menu-item-group v-for="(item, key) in modelKeys" :key="key">
          <template #title>
            <span>{{ modelNames[item]?.name }}</span>
            <a-tag color="warning" size="small" class="provider-tag">Legacy</a-tag>
          </template>
          <a-menu-item
            v-for="(model, idx) in modelNames[item]?.models"
            :key="`${item}-${idx}`"
            @click="handleSelectModel(item, model)"
          >
            {{ model }}
          </a-menu-item>
        </a-menu-item-group>
      </a-menu>
    </template>
  </a-dropdown>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { useConfigStore } from '@/stores/config'
import { modelProviderApi } from '@/apis/system_api'

const props = defineProps({
  model_spec: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '请选择模型'
  },
  size: {
    type: String,
    default: 'small',
    validator: (value) => ['small', 'middle', 'large'].includes(value)
  }
})

const configStore = useConfigStore()
const emit = defineEmits(['select-model'])

// v2 模型数据
const v2Models = ref({})

// 加载 v2 模型列表
onMounted(async () => {
  try {
    const response = await modelProviderApi.getV2Models('chat')
    if (response.success) {
      v2Models.value = response.data || {}
    }
  } catch (error) {
    console.warn('Failed to load v2 models:', error)
  }
})

// 状态管理
const state = reactive({
  currentModelStatus: null, // 当前模型状态
  checkingStatus: false // 是否正在检查状态
})

// 从configStore中获取所需数据
const modelNames = computed(() => configStore.config?.model_names)
const modelStatus = computed(() => configStore.config?.model_provider_status)

// 筛选 modelStatus 中为真的key
const modelKeys = computed(() => {
  return Object.keys(modelStatus.value || {}).filter((key) => modelStatus.value?.[key])
})

const resolvedSize = computed(() => props.size || 'small')
const modelSelectClasses = computed(() => ({
  'model-select--middle': resolvedSize.value === 'middle',
  'model-select--large': resolvedSize.value === 'large'
}))
const buttonSize = computed(() => {
  if (resolvedSize.value === 'large') return 'large'
  if (resolvedSize.value === 'middle') return 'middle'
  return 'small'
})

const displayModelText = computed(() => props.model_spec || props.placeholder)

// 当前模型状态

// 检查当前模型状态
const checkCurrentModelStatus = async () => {
  const spec = props.model_spec
  if (!spec) return

  try {
    state.checkingStatus = true
    const response = await modelProviderApi.getModelStatusBySpec(spec)
    if (response.data) {
      state.currentModelStatus = response.data
    } else {
      state.currentModelStatus = null
    }
  } catch (error) {
    console.error(`检查模型 ${spec} 状态失败:`, error)
    state.currentModelStatus = { status: 'error', message: error.message }
  } finally {
    state.checkingStatus = false
  }
}

const modelStatusIcon = computed(() => {
  const status = state.currentModelStatus
  if (!status) return '○'
  if (status.status === 'available') return '✓'
  if (status.status === 'unavailable') return '✗'
  if (status.status === 'error') return '⚠'
  return '○'
})

// 获取当前模型状态提示文本
const getCurrentModelStatusTooltip = () => {
  const status = state.currentModelStatus
  if (!status) return '状态未知'

  let statusText = ''
  if (status.status === 'available') statusText = '可用'
  else if (status.status === 'unavailable') statusText = '不可用'
  else if (status.status === 'error') statusText = '错误'

  const message = status.message || '无详细信息'
  return `${statusText}: ${message}`
}

// 选择 v1 模型的方法（Legacy）
const handleSelectModel = async (provider, name) => {
  const spec = `${provider}/${name}`
  emit('select-model', spec)
}

// 选择 v2 模型的方法
const handleSelectV2Model = (spec) => {
  emit('select-model', spec)
}
</script>

<style lang="less" scoped>
// 变量定义
@status-success: var(--color-success-500);
@status-error: var(--color-error-500);
@status-warning: var(--color-warning-500);
@status-default: var(--gray-500);
@border-radius: 8px;
@scrollbar-width: 6px;
@status-indicator-padding: 2px 4px;
@status-check-button-padding: 0 4px;
@status-check-button-font-size: 12px;
@status-indicator-font-size: 11px;

// 主选择器样式
.model-select {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 4px 8px;
  cursor: pointer;
  border: 1px solid var(--gray-200);
  border-radius: @border-radius;
  background-color: var(--gray-0);
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

  &.model-select--middle {
    font-size: 15px;
  }

  &.model-select--large {
    font-size: 16px;
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
        color: var(--gray-1000);
        white-space: nowrap;
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

// Provider 标签样式
.provider-tag {
  margin-left: 6px;
  font-size: 10px;
  line-height: 1;
  vertical-align: middle;
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
