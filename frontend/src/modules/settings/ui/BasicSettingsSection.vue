<template>
  <div class="basic-settings-section">
    <template v-if="userStore.isSuperAdmin">
      <div class="section-title">默认项配置</div>
      <section class="settings-panel" aria-label="默认模型配置">
        <div class="setting-row">
          <div class="setting-copy">
            <div class="setting-label">{{ items?.default_model?.des || '默认对话模型' }}</div>
            <p class="setting-description">未单独指定模型时，用于对话与内容生成。</p>
          </div>
          <div class="setting-content">
            <ModelSelectorComponent
              display-name="mini"
              @select-model="handleChatModelSelect"
              :model_spec="configStore.config?.default_model"
              placeholder="请选择默认模型"
            />
          </div>
        </div>
        <div class="setting-row">
          <div class="setting-copy">
            <div class="setting-label">{{ items?.fast_model?.des || '快速响应模型' }}</div>
            <p class="setting-description">用于会话标题等需要快速响应的轻量任务。</p>
          </div>
          <div class="setting-content">
            <ModelSelectorComponent
              display-name="mini"
              @select-model="handleFastModelSelect"
              :model_spec="configStore.config?.fast_model"
              placeholder="请选择模型"
            />
          </div>
        </div>
        <div class="setting-row">
          <div class="setting-copy">
            <div class="setting-label">{{ items?.embed_model?.des || '默认 Embedding 模型' }}</div>
            <p class="setting-description">将文本转为向量，用于知识库索引与检索。</p>
          </div>
          <div class="setting-content is-compact">
            <EmbeddingModelSelector
              display-name="mini"
              :value="configStore.config?.embed_model"
              @change="handleChange('embed_model', $event)"
            />
          </div>
        </div>
        <div class="setting-row">
          <div class="setting-copy">
            <div class="setting-label">{{ items?.reranker?.des || '默认 Re-Ranker 模型' }}</div>
            <p class="setting-description">对检索结果重排序，优先呈现更相关的内容。</p>
          </div>
          <div class="setting-content is-compact">
            <RerankModelSelector
              display-name="mini"
              :value="configStore.config?.reranker"
              @change="handleChange('reranker', $event)"
            />
          </div>
        </div>
      </section>

      <div class="section-title">协作限制</div>
      <section class="settings-panel">
        <div class="setting-row">
          <div class="setting-copy">
            <label class="setting-label" for="max-cooperation-depth">最大协作深度</label>
            <p class="setting-description" id="cooperation-depth-help">根对话为第 0 层，默认允许 2 层协作；设为 0 可关闭新增协作会话。</p>
          </div>
          <div class="setting-content is-number">
            <a-input-number
              id="max-cooperation-depth"
              aria-describedby="cooperation-depth-help"
              :value="configStore.config?.max_cooperation_depth ?? 2"
              :min="0"
              :precision="0"
              @change="handleCooperationDepthChange"
            />
          </div>
        </div>
      </section>

      <SkillSettingsSection :class="{ 'first-section': !userStore.isSuperAdmin }" />
    </template>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useConfigStore } from '@/modules/settings/model/config'
import { useUserStore } from '@/modules/identity/model/user'
import ModelSelectorComponent from '@/modules/agents/ui/ModelSelectorComponent.vue'
import EmbeddingModelSelector from '@/modules/settings/ui/EmbeddingModelSelector.vue'
import RerankModelSelector from '@/modules/settings/ui/RerankModelSelector.vue'
import SkillSettingsSection from '@/modules/agents/ui/SkillSettingsSection.vue'

const configStore = useConfigStore()
const userStore = useUserStore()
const items = computed(() => configStore.config?._config_items || {})
const handleChange = (key, e) => {
  configStore.setConfigValue(key, e)
}

/** 只提交完整的非负整数，清空输入不会修改已保存的限制。 */
const handleCooperationDepthChange = (value) => {
  if (Number.isInteger(value) && value >= 0) handleChange('max_cooperation_depth', value)
}

const handleChatModelSelect = (spec) => {
  if (typeof spec === 'string' && spec) {
    configStore.setConfigValue('default_model', spec)
  }
}

const handleFastModelSelect = (spec) => {
  if (typeof spec === 'string' && spec) {
    configStore.setConfigValue('fast_model', spec)
  }
}
</script>

<style lang="less" scoped src="./settings-form.less"></style>
