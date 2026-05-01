<template>
  <a-dropdown trigger="click" @open-change="handleOpenChange">
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
          <a-tooltip title="刷新缓存">
            <button
              :loading="state.refreshingCache"
              @click.stop="refreshCache"
              :disabled="state.refreshingCache"
              class="cache-refresh-button"
            >
              <RefreshCw :size="13" :class="{ spin: state.refreshingCache }" />
            </button>
          </a-tooltip>
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
            <a-tag color="success" size="small" class="provider-tag">新</a-tag>
          </template>
          <a-menu-item
            v-for="model in providerData.models"
            :key="model.spec"
            @click="handleSelectV2Model(model.spec)"
          >
            {{ model.display_name }}
          </a-menu-item>
        </a-menu-item-group>
      </a-menu>
    </template>
  </a-dropdown>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { modelProviderApi } from '@/apis/system_api'
import { RefreshCw } from 'lucide-vue-next'
import { useModelStatus } from '@/composables/useModelStatus'

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

const emit = defineEmits(['select-model'])

// v2 模型数据：每次展开下拉时实时从后端拉取
const v2Models = ref({})
const loadingV2Models = ref(false)

// 拉取 v2 模型列表
const fetchV2Models = async () => {
  if (loadingV2Models.value) return
  loadingV2Models.value = true
  try {
    const response = await modelProviderApi.getV2Models('chat')
    if (response.success) {
      v2Models.value = response.data || {}
    }
  } catch (error) {
    console.warn('Failed to load v2 models:', error)
  } finally {
    loadingV2Models.value = false
  }
}

// 下拉展开时触发实时刷新（仅在打开瞬间触发，关闭时忽略）
const handleOpenChange = (open) => {
  if (open) fetchV2Models()
}

// 强制刷新缓存
const refreshCache = async () => {
  if (state.refreshingCache) return
  state.refreshingCache = true
  try {
    await modelProviderApi.refreshModelCache()
    // 刷新后重新拉取模型列表
    await fetchV2Models()
  } catch (error) {
    console.error('Failed to refresh cache:', error)
  } finally {
    state.refreshingCache = false
  }
}

// 状态管理
useModelStatus()
const state = reactive({
  currentModelStatus: null,
  checkingStatus: false,
  refreshingCache: false
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

// 选择 v2 模型的方法
const handleSelectV2Model = (spec) => {
  emit('select-model', spec)
}
</script>

<style lang="less" scoped>
@import '@/assets/css/model-selector-common.less';

// 状态检查按钮
.status-check-button {
  font-size: 12px;
  padding: 0 4px;
}

// 缓存刷新按钮
.cache-refresh-button {
  font-size: 12px;
  padding: 0 4px;
  display: flex;
  align-items: center;
  width: 24px;
  background-color: transparent;
  border: none;
  outline: none;
  cursor: pointer;
}

:deep(.ant-dropdown-menu) {
  &.scrollable-menu {
    max-height: 300px;
    overflow-y: auto;
  }
}
</style>
