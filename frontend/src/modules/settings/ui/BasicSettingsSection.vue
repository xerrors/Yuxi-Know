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
      <section class="cooperation-limit-card">
        <div class="cooperation-limit-copy">
          <label for="max-cooperation-depth">最大协作深度</label>
          <p id="cooperation-depth-help">根对话为第 0 层，默认允许 2 层协作；设为 0 可关闭新增协作会话。</p>
        </div>
        <a-input-number
          id="max-cooperation-depth"
          class="cooperation-limit-input"
          aria-describedby="cooperation-depth-help"
          :value="configStore.config?.max_cooperation_depth ?? 2"
          :min="0"
          :precision="0"
          @change="handleCooperationDepthChange"
        />
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

<style lang="less" scoped>
.basic-settings-section {
  .settings-panel {
    container: default-model-settings / inline-size;
    background: var(--gray-0);
    border: 1px solid var(--gray-150);
    border-radius: 8px;
  }

  .setting-row {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding: 14px 16px;

    & + .setting-row {
      border-top: 1px solid var(--gray-150);
    }
  }

  .cooperation-limit-card {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    padding: 14px 16px;
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    background: var(--gray-0);
  }

  .cooperation-limit-copy {
    flex: 1;
    min-width: 0;

    label {
      display: block;
      color: var(--gray-900);
      font-size: 13px;
      font-weight: 500;
    }

    p {
      margin: 4px 0 0;
      color: var(--color-text-secondary);
      font-size: 12px;
      line-height: 1.5;
    }
  }

  .cooperation-limit-input {
    flex: none;
    width: 88px;
  }

  .setting-copy {
    flex: 1;
    min-width: 0;
  }

  .setting-description {
    margin: 4px 0 0;
    color: var(--color-text-secondary);
    font-size: 12px;
    line-height: 1.5;
  }

  .setting-label {
    font-size: 13px;
    font-weight: 500;
    color: var(--gray-900);
  }

  .setting-content {
    flex: 0 1 340px;
    width: 340px;
    max-width: 100%;
    min-width: 0;
  }

  .setting-content.is-compact {
    flex-basis: 260px;
    width: 260px;
  }

  @container default-model-settings (max-width: 520px) {
    .setting-row {
      flex-direction: column;
      align-items: stretch;
      gap: 8px;
    }

    .setting-content {
      flex: none;
      width: 100%;
      max-width: 340px;
    }

    .setting-content.is-compact {
      flex: none;
      width: 100%;
      max-width: 260px;
    }
  }

  .agent-select {
    width: 320px;
    max-width: 100%;
  }

  @media (max-width: 768px) {
    .agent-select {
      width: 100%;
    }
  }
}
</style>
