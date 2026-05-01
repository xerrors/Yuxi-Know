<template>
  <a-dropdown trigger="click" @open-change="handleOpenChange">
    <div class="model-select" :class="modelSelectClasses" @click.prevent>
      <div class="model-select-content">
        <div class="model-info">
          <a-tooltip :title="displayText" placement="right">
            <span class="model-text">{{ displayText }}</span>
          </a-tooltip>
        </div>
      </div>
    </div>

    <template #overlay>
      <a-menu class="scrollable-menu">
        <!-- V2 模型列表（按 provider 分组） -->
        <a-menu-item-group v-for="(providerData, providerId) in v2Models" :key="`v2-${providerId}`">
          <template #title>
            <span>{{ providerId }}</span>
            <a-tag color="success" size="small" class="provider-tag">新</a-tag>
          </template>
          <a-menu-item
            v-for="model in providerData.models"
            :key="model.spec"
            @click="handleSelect(model.spec)"
          >
            <div class="model-option">
              <span class="model-option-name">
                {{ model.display_name }}
                <span class="model-dimension">({{ model.dimension }})</span>
              </span>
              <span
                class="model-status-icon"
                :class="getV2StatusClass(model.spec)"
                :title="getV2StatusTooltip(model.spec)"
                >{{ getV2StatusIcon(model.spec) }}</span
              >
            </div>
          </a-menu-item>
        </a-menu-item-group>

        <!-- V1 模型列表（过时，仅保留兼容） -->
        <a-menu-item-group v-if="v1EmbedModels.length" key="v1" title="V1 版本（过时）">
          <a-menu-item v-for="name in v1EmbedModels" :key="name" @click="handleSelect(name)">
            <div class="model-option">
              <span class="model-option-name">
                {{ name }}
                <span class="model-dimension"
                  >({{ configStore.config?.embed_model_names[name]?.dimension }})</span
                >
              </span>
              <a-tag color="default" size="small" class="provider-tag">过时</a-tag>
              <span
                class="model-status-icon"
                :class="getV1StatusClass(name)"
                :title="getV1StatusTooltip(name)"
                >{{ getV1StatusIcon(name) }}</span
              >
            </div>
          </a-menu-item>
        </a-menu-item-group>
      </a-menu>
    </template>
  </a-dropdown>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import { embeddingApi } from '@/apis/knowledge_api'
import { modelProviderApi } from '@/apis/system_api'
import { message } from 'ant-design-vue'
import { useModelStatus } from '@/composables/useModelStatus'

const configStore = useConfigStore()

const props = defineProps({
  value: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '请选择嵌入模型'
  },
  size: {
    type: String,
    default: 'small',
    validator: (value) => ['default', 'small', 'middle', 'large'].includes(value)
  },
  style: {
    type: Object,
    default: () => ({ width: '100%' })
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:value', 'change'])

const v2Models = ref({})
const v1ModelStatuses = reactive({})
const {
  getStatusIcon: getV2StatusIcon,
  getStatusClass: getV2StatusClass,
  getStatusTooltip: getV2StatusTooltip,
  checkV2Statuses
} = useModelStatus()
const state = reactive({
  checkingStatus: false
})

const displayText = computed(() => props.value || props.placeholder)

const resolvedSize = computed(() => props.size || 'small')
const modelSelectClasses = computed(() => ({
  'model-select--middle': resolvedSize.value === 'middle',
  'model-select--large': resolvedSize.value === 'large'
}))

const v1EmbedModels = computed(() => {
  return Object.keys(configStore?.config?.embed_model_names || {})
})

const handleOpenChange = async (open) => {
  if (!open) return
  fetchV2Models()
  checkV1ModelStatuses()
}

const fetchV2Models = async () => {
  try {
    const response = await modelProviderApi.getV2Models('embedding')
    if (response.success) {
      v2Models.value = response.data || {}
      // 拉取到 V2 模型列表后，逐一检查状态
      await checkV2ModelStatuses()
    }
  } catch (error) {
    console.error('获取 V2 embedding 模型失败:', error)
  }
}

const checkV2ModelStatuses = async () => {
  state.checkingStatus = true
  try {
    for (const providerData of Object.values(v2Models.value)) {
      await checkV2Statuses(providerData.models || [])
    }
  } catch (error) {
    console.error('检查 V2 模型状态失败:', error)
  } finally {
    state.checkingStatus = false
  }
}

const checkV1ModelStatuses = async () => {
  try {
    const response = await embeddingApi.getAllModelsStatus()
    if (response.status.models) {
      Object.assign(v1ModelStatuses, response.status.models)
    }
  } catch (error) {
    console.error('检查 V1 模型状态失败:', error)
    message.error('获取模型状态失败')
  }
}

// V1 模型状态辅助函数
const getV1StatusIcon = (modelId) => {
  const status = v1ModelStatuses[modelId]
  if (!status) return '○'
  if (status.status === 'available') return '✓'
  if (status.status === 'unavailable') return '✗'
  if (status.status === 'error') return '⚠'
  return '○'
}

const getV1StatusClass = (modelId) => {
  const status = v1ModelStatuses[modelId]
  return status?.status || ''
}

const getV1StatusTooltip = (modelId) => {
  const status = v1ModelStatuses[modelId]
  if (!status) return '状态未知'
  let statusText =
    { available: '可用', unavailable: '不可用', error: '错误' }[status.status] || '未知'
  return `${statusText}: ${status.message || '无详细信息'}`
}

const handleSelect = (value) => {
  emit('update:value', value)
  emit('change', value)
}
</script>

<style lang="less" scoped>
@import '@/assets/css/model-selector-common.less';

.model-option {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  width: 100%;
}

.model-option-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-dimension {
  color: var(--gray-500);
  font-size: 12px;
  margin-left: 4px;
}

.model-status-icon {
  font-size: 11px;
  font-weight: bold;
  flex-shrink: 0;
  color: var(--gray-500);

  &.available {
    color: var(--color-success-500);
  }

  &.unavailable {
    color: var(--color-error-500);
  }

  &.error {
    color: var(--color-warning-500);
  }
}
</style>
