<template>
  <a-dropdown trigger="click" @open-change="handleOpenChange">
    <div class="model-select" @click.prevent>
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
            {{ model.display_name }}
          </a-menu-item>
        </a-menu-item-group>

        <a-menu-item-group v-if="v1Models.length" key="v1" title="V1 版本（过时）">
          <a-menu-item v-for="name in v1Models" :key="name" @click="handleSelect(name)">
            <span>{{ name }}</span>
            <a-tag color="default" size="small" class="provider-tag">过时</a-tag>
          </a-menu-item>
        </a-menu-item-group>
      </a-menu>
    </template>
  </a-dropdown>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import { modelProviderApi } from '@/apis/system_api'

const configStore = useConfigStore()

const props = defineProps({
  value: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '请选择重排序模型'
  },
  size: {
    type: String,
    default: 'small',
    validator: (value) => ['small', 'middle', 'large'].includes(value)
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

const displayText = computed(() => props.value || props.placeholder)

const v1Models = computed(() => {
  return Object.keys(configStore?.config?.reranker_names || {})
})

const handleOpenChange = async (open) => {
  if (!open) return
  try {
    const response = await modelProviderApi.getV2Models('rerank')
    if (response.success) {
      v2Models.value = response.data || {}
    }
  } catch (error) {
    console.error('获取 V2 rerank 模型失败:', error)
  }
}

const handleSelect = (spec) => {
  emit('update:value', spec)
  emit('change', spec)
}
</script>

<style lang="less" scoped>
@import '@/assets/css/model-selector-common.less';
</style>
