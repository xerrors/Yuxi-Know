<template>
  <div class="basic-settings-section">
    <h3 class="section-title">检索配置</h3>
    <div class="section">
      <div class="card card-select">
        <span class="label">{{ items?.default_model?.des || '默认对话模型' }}</span>
        <ModelSelectorComponent
          @select-model="handleChatModelSelect"
          :model_spec="configStore.config?.default_model"
          placeholder="请选择默认模型"
        />
      </div>
      <div class="card card-select">
        <span class="label">{{ items?.fast_model.des }}</span>
        <ModelSelectorComponent
          @select-model="handleFastModelSelect"
          :model_spec="configStore.config?.fast_model"
          placeholder="请选择模型"
        />
      </div>
      <div class="card card-select">
        <span class="label">{{ items?.embed_model.des }}</span>
        <EmbeddingModelSelector
          :value="configStore.config?.embed_model"
          @change="handleChange('embed_model', $event)"
          style="width: 320px"
        />
      </div>
      <div class="card card-select">
        <span class="label">{{ items?.reranker.des }}</span>
        <a-select style="width: 320px"
          :value="configStore.config?.reranker"
          @change="handleChange('reranker', $event)"
        >
          <a-select-option
            v-for="(name, idx) in rerankerChoices" :key="idx"
            :value="name">{{ name }}
          </a-select-option>
        </a-select>
      </div>
    </div>

    <h3 class="section-title">内容审查配置</h3>
    <div class="section">
      <div class="card">
        <span class="label">{{ items?.enable_content_guard.des }}</span>
        <a-switch
          :checked="configStore.config?.enable_content_guard"
          @change="handleChange('enable_content_guard', $event)"
        />
      </div>
      <div class="card" v-if="configStore.config?.enable_content_guard">
        <span class="label">{{ items?.enable_content_guard_llm.des }}</span>
        <a-switch
          :checked="configStore.config?.enable_content_guard_llm"
          @change="handleChange('enable_content_guard_llm', $event)"
        />
      </div>
      <div class="card card-select" v-if="configStore.config?.enable_content_guard && configStore.config?.enable_content_guard_llm">
        <span class="label">{{ items?.content_guard_llm_model.des }}</span>
        <ModelSelectorComponent
          @select-model="handleContentGuardModelSelect"
          :model_spec="configStore.config?.content_guard_llm_model"
          placeholder="请选择模型"
        />
      </div>
    </div>

    <!-- 服务链接部分 -->
    <h3 v-if="userStore.isAdmin" class="section-title">服务链接</h3>
    <div v-if="userStore.isAdmin">
      <p class="service-description">快速访问系统相关的外部服务，需要将 localhost 替换为实际的 IP 地址。</p>
      <div class="services-grid">
        <div class="service-link-card">
          <div class="service-info">
            <h4>Neo4j 浏览器</h4>
            <p>图数据库管理界面</p>
          </div>
          <a-button type="default" @click="openLink('http://localhost:7474/')" :icon="h(GlobalOutlined)">
            访问
          </a-button>
        </div>

        <div class="service-link-card">
          <div class="service-info">
            <h4>API 接口文档</h4>
            <p>系统接口文档和调试工具</p>
          </div>
          <a-button type="default" @click="openLink('http://localhost:5050/docs')" :icon="h(GlobalOutlined)">
            访问
          </a-button>
        </div>

        <div class="service-link-card">
          <div class="service-info">
            <h4>MinIO 对象存储</h4>
            <p>文件存储管理控制台</p>
          </div>
          <a-button type="default" @click="openLink('http://localhost:9001')" :icon="h(GlobalOutlined)">
            访问
          </a-button>
        </div>

        <div class="service-link-card">
          <div class="service-info">
            <h4>Milvus WebUI</h4>
            <p>向量数据库管理界面</p>
          </div>
          <a-button type="default" @click="openLink('http://localhost:9091/webui/')" :icon="h(GlobalOutlined)">
            访问
          </a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, h } from 'vue'
import { useConfigStore } from '@/stores/config'
import { useUserStore } from '@/stores/user'
import { GlobalOutlined } from '@ant-design/icons-vue'
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue'
import EmbeddingModelSelector from '@/components/EmbeddingModelSelector.vue'

const configStore = useConfigStore()
const userStore = useUserStore()
const items = computed(() => configStore.config._config_items)

const rerankerChoices = computed(() => {
  return Object.keys(configStore?.config?.reranker_names || {}) || []
})

const preHandleChange = (key, e) => {
  return true
}

const handleChange = (key, e) => {
  if (!preHandleChange(key, e)) {
    return
  }
  configStore.setConfigValue(key, e)
}

const handleChanges = (items) => {
  for (const key in items) {
    if (!preHandleChange(key, items[key])) {
      return
    }
  }
  configStore.setConfigValues(items)
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

const handleContentGuardModelSelect = (spec) => {
  if (typeof spec === 'string' && spec) {
    configStore.setConfigValue('content_guard_llm_model', spec)
  }
}

const openLink = (url) => {
  window.open(url, '_blank')
}
</script>

<style lang="less" scoped>
.basic-settings-section {
  .settings-content {
    max-width: 100%;
  }

  .section-title {
    color: var(--gray-900);
    font-size: 16px;
    font-weight: 600;
    margin: 24px 0 12px 0;
    padding-bottom: 8px;

    &:first-child {
      margin-top: 8px;
    }
  }

  .service-description {
    color: var(--gray-600);
    font-size: 14px;
    margin: 0 0 16px 0;
    line-height: 1.5;
  }

  .section {
    margin-top: 10px;
    background-color: var(--gray-0);
    padding: 10px 16px;
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    border: 1px solid var(--gray-150);
  }

  .card {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .label {
      margin-right: 20px;
      font-weight: 500;
      color: var(--gray-800);
      flex-shrink: 0;
      min-width: 140px;
    }

    &.card-select {
      align-items: flex-start;
      gap: 12px;

      .label {
        margin-right: 0;
        margin-top: 6px;
      }
    }
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
    padding: 16px;
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    background: var(--gray-0);
    transition: all 0.2s;
    min-height: 70px;

    &:hover {
      box-shadow: 0 1px 8px var(--gray-200);
      border-color: var(--main-200);
    }

    .service-info {
      flex: 1;
      margin-right: 16px;

      h4 {
        margin: 0 0 4px 0;
        color: var(--gray-900);
        font-size: 15px;
        font-weight: 600;
      }

      p {
        margin: 0;
        color: var(--gray-600);
        font-size: 13px;
        line-height: 1.4;
      }
    }
  }
}

// 移动端适配
@media (max-width: 768px) {
  .basic-settings-section {
    .section {
      padding: 12px;
    }

    .card {
      flex-direction: column;
      align-items: flex-start;
      gap: 12px;
      padding: 16px 0;

      .label {
        margin-right: 0;
        margin-bottom: 8px;
      }

      &.card-select {
        .label {
          margin-top: 0;
        }
      }
    }

    .services-grid {
      grid-template-columns: 1fr;
      gap: 12px;
    }

    .service-link-card {
      flex-direction: column;
      align-items: flex-start;
      gap: 12px;
      min-height: auto;
      padding: 12px;

      .service-info {
        margin-right: 0;
        margin-bottom: 8px;
      }
    }
  }
}

// 小屏幕进一步优化
@media (max-width: 480px) {
  .basic-settings-section {
    .section-title {
      font-size: 15px;
    }

    .card {
      .label {
        font-size: 14px;
        min-width: 120px;
      }
    }

    .service-link-card {
      .service-info {
        h4 {
          font-size: 14px;
        }

        p {
          font-size: 12px;
        }
      }
    }
  }
}
</style>