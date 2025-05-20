<template>
  <a-dropdown>
    <a class="model-select" @click.prevent>
      <!-- <BulbOutlined /> -->
      <a-tooltip :title="model_name" placement="right">
        <span class="model-text text"> {{ model_name }} </span>
      </a-tooltip>
      <span class="text" style="color: #aaa;">{{ model_provider }} </span>
    </a>
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
import { computed } from 'vue'
import { BulbOutlined } from '@ant-design/icons-vue'
import { useConfigStore } from '@/stores/config'

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

// 从configStore中获取所需数据
const modelNames = computed(() => configStore.config?.model_names)
const modelStatus = computed(() => configStore.config?.model_provider_status)
const customModels = computed(() => configStore.config?.custom_models || [])

// 筛选 modelStatus 中为真的key
const modelKeys = computed(() => {
  return Object.keys(modelStatus.value || {}).filter(key => modelStatus.value?.[key])
})

// 选择模型的方法
const handleSelectModel = (provider, name) => {
  emit('select-model', { provider, name })
}
</script>

<style lang="less" scoped>
.model-select {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0.25rem 0.5rem;
  cursor: pointer;
  border: 1px solid var(--gray-300);
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background-color: white;

  &.borderless {
    border: none;
  }

  &.max-width {
    max-width: 380px;
  }

  .model-text {
    overflow: hidden;
    text-overflow: ellipsis;
  }


}

.nav-btn {
  height: 2.5rem;
  display: flex;
  justify-content: center;
  align-items: center;
  border-radius: 8px;
  color: var(--gray-900);
  cursor: pointer;
  width: auto;
  transition: background-color 0.3s;
  padding: 0.5rem 0.75rem;

  .text {
    margin-left: 10px;
  }

  &:hover {
    background-color: var(--main-light-3);
  }
}

.scrollable-menu {
  max-height: 300px;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--gray-400);
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb:hover {
    background: var(--gray-500);
  }
}
</style>

<style lang="less">
// 添加全局样式以确保滚动功能在dropdown内正常工作
.ant-dropdown-menu {
  &.scrollable-menu {
    max-height: 300px;
    overflow-y: auto;
  }
}
</style>