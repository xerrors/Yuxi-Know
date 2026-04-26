<template>
  <div class="model-providers-section">
    <div class="header-section">
      <div class="header-content">
        <div class="section-title">自定义供应商</div>
        <p class="section-description">查看自定义的LLM供应商配置。</p>
      </div>
    </div>

    <a-alert type="info">
      <template #message>
        <span>改动提醒</span>
      </template>
      <template #description>
        项目已启用新版的模型配置，自定义程度更高，且支持 Embedding / Rerank 模型，您可以
        <a @click="goToNewModelConfig">点击此处</a>
        跳转到新版模型配置页面。 已配置模型将会在 0.6.x 期间继续使用，0.7
        版本将不再支持老版的模型调用。
        为了更加稳定的模型调用和更好的用户体验，建议尽快迁移到新的模型配置。
      </template>
    </a-alert>

    <div v-if="tableData.length === 0" class="empty-state">
      <a-empty description="暂无自定义供应商" />
    </div>

    <div v-for="item in tableData" :key="item.id" class="provider-block">
      <h4 class="provider-name">
        {{ item.name }} <span class="provider-id">({{ item.id }})</span>
      </h4>
      <a-descriptions bordered :column="1" size="small">
        <a-descriptions-item label="API地址">{{ item.base_url }}</a-descriptions-item>
        <a-descriptions-item label="默认模型">{{ item.default }}</a-descriptions-item>
        <a-descriptions-item label="API密钥">{{ item.env }}</a-descriptions-item>
        <a-descriptions-item label="文档地址">
          <a v-if="item.url" :href="item.url" target="_blank">{{ item.url }}</a>
          <span v-else>无</span>
        </a-descriptions-item>
        <a-descriptions-item label="可用模型">{{
          item.models?.join(', ') || '无'
        }}</a-descriptions-item>
      </a-descriptions>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useConfigStore } from '@/stores/config'

const configStore = useConfigStore()
const router = useRouter()

const tableData = computed(() => {
  const providers = configStore.config?.model_names || {}
  return Object.entries(providers)
    .filter(([, value]) => value.custom === true)
    .map(([id, provider]) => ({
      key: id,
      id,
      name: provider.name || '',
      base_url: provider.base_url || '',
      default: provider.default || '',
      env: provider.env || '',
      models: provider.models || [],
      url: provider.url || ''
    }))
})

const goToNewModelConfig = () => {
  router.push('/model-config')
}
</script>

<style lang="less" scoped>
.provider-block {
  margin: 16px 0;

  .provider-name {
    margin: 0 0 8px 0;
    font-weight: 500;
    color: var(--gray-900);

    .provider-id {
      font-weight: 400;
      color: var(--gray-500);
      font-size: 13px;
    }
  }
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  background: var(--gray-25);
  border-radius: 8px;
  border: 1px dashed var(--gray-300);
}
</style>
