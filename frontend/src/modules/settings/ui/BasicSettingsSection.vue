<template>
  <div class="basic-settings-section">
    <template v-if="userStore.isSuperAdmin">
      <template v-if="userStore.isSuperAdmin">
        <div class="section-title">默认项配置</div>
        <div class="settings-panel">
          <div class="setting-row two-cols">
            <div class="col-item">
              <div class="setting-label">{{ items?.default_model?.des || '默认对话模型' }}</div>
              <div class="setting-content">
                <ModelSelectorComponent
                  @select-model="handleChatModelSelect"
                  :model_spec="configStore.config?.default_model"
                  placeholder="请选择默认模型"
                />
              </div>
            </div>
            <div class="col-item">
              <div class="setting-label">{{ items?.fast_model?.des }}</div>
              <div class="setting-content">
                <ModelSelectorComponent
                  @select-model="handleFastModelSelect"
                  :model_spec="configStore.config?.fast_model"
                  placeholder="请选择模型"
                />
              </div>
            </div>
          </div>
          <div class="setting-row two-cols">
            <div class="col-item">
              <div class="setting-label">{{ items?.embed_model?.des }}</div>
              <div class="setting-content">
                <EmbeddingModelSelector
                  :value="configStore.config?.embed_model"
                  @change="handleChange('embed_model', $event)"
                  style="width: 100%"
                />
              </div>
            </div>
            <div class="col-item">
              <div class="setting-label">{{ items?.reranker?.des }}</div>
              <div class="setting-content">
                <RerankModelSelector
                  :value="configStore.config?.reranker"
                  @change="handleChange('reranker', $event)"
                  style="width: 100%"
                />
              </div>
            </div>
          </div>
        </div>
      </template>

      <div class="section-title">协作限制</div>
      <div class="settings-panel">
        <div class="setting-row">
          <label class="setting-label" for="max-cooperation-depth">最大协作深度</label>
          <div class="setting-content">
            <a-input-number
              id="max-cooperation-depth"
              aria-describedby="cooperation-depth-help"
              :value="configStore.config?.max_cooperation_depth ?? 2"
              :min="0"
              :precision="0"
              @change="handleCooperationDepthChange"
            />
          </div>
          <p id="cooperation-depth-help" class="setting-description">根对话为第 0 层，默认允许 2 层协作；设为 0 可关闭新增协作会话。</p>
        </div>
      </div>

      <SkillSettingsSection :class="{ 'first-section': !userStore.isSuperAdmin }" />
    </template>

    <!-- 服务链接部分 -->
    <div v-if="userStore.isSuperAdmin">
      <div class="services-grid">
        <div class="service-link-card">
          <div class="service-info">
            <h4>Neo4j 浏览器</h4>
            <p>图数据库管理界面</p>
          </div>
          <a-button
            type="default"
            class="lucide-icon-btn"
            @click="openLink('http://localhost:7474/')"
            :icon="h(Globe, { size: 18 })"
          >
            访问
          </a-button>
        </div>

        <div class="service-link-card">
          <div class="service-info">
            <h4>API 接口文档</h4>
            <p>系统接口文档和调试工具</p>
          </div>
          <a-button
            type="default"
            class="lucide-icon-btn"
            @click="openLink('http://localhost:5050/docs')"
            :icon="h(Globe, { size: 18 })"
          >
            访问
          </a-button>
        </div>

        <div class="service-link-card">
          <div class="service-info">
            <h4>MinIO 对象存储</h4>
            <p>文件存储管理控制台</p>
          </div>
          <a-button
            type="default"
            class="lucide-icon-btn"
            @click="openLink('http://localhost:9001')"
            :icon="h(Globe, { size: 18 })"
          >
            访问
          </a-button>
        </div>

        <div class="service-link-card">
          <div class="service-info">
            <h4>Milvus WebUI</h4>
            <p>向量数据库管理界面</p>
          </div>
          <a-button
            type="default"
            class="lucide-icon-btn"
            @click="openLink('http://localhost:9091/webui/')"
            :icon="h(Globe, { size: 18 })"
          >
            访问
          </a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, h } from 'vue'
import { useConfigStore } from '@/modules/settings/model/config'
import { useUserStore } from '@/modules/identity/model/user'
import { Globe } from '@lucide/vue'
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

const openLink = (url) => {
  window.open(url, '_blank')
}
</script>

<style lang="less" scoped>
.basic-settings-section {
  .settings-panel {
    background-color: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .setting-row {
    display: flex;
    flex-direction: column;
    gap: 8px;

    &.two-cols {
      flex-direction: row;
      gap: 20px;
    }

    .col-item {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-width: 0;
    }
  }

  .setting-description {
    margin: 0;
    color: var(--color-text-secondary);
    font-size: 13px;
  }

  .setting-label {
    font-size: 13px;
    font-weight: 500;
    color: var(--gray-700);
  }

  .setting-content {
    width: 100%;

    .full-width {
      width: 100%;
    }
  }

  .agent-select {
    width: 320px;
    max-width: 100%;
  }

  .services-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
    margin-top: 16px;
  }

  .service-link-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    background: var(--gray-0);
    transition: all 0.2s;
    min-height: 70px;

    &:hover {
      box-shadow: 0 1px 8px var(--gray-150);
      border-color: var(--gray-100);
    }

    .service-info {
      flex: 1;
      margin-right: 16px;

      h4 {
        margin: 0 0 4px 0;
        color: var(--gray-900);
        font-size: 15px;
        font-weight: 500;
      }

      p {
        margin: 0;
        color: var(--gray-600);
        font-size: 13px;
        line-height: 1.4;
      }
    }
  }

  @media (max-width: 768px) {
    .agent-select {
      width: 100%;
    }
  }
}
</style>
