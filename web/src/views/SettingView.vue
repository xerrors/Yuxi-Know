<template>
  <div class="setting-container">
    <div class="setting">
      <h2>设置</h2>
      <h3>模型配置</h3>
      <div class="section">
        <div class="card">
          <span class="label">
            {{ items?.model_provider.des }} &nbsp;
            <a-button small v-if="needRestart.model_provider" @click="sendRestart">
              <ReloadOutlined />需要重启
            </a-button>
          </span>
          <a-select ref="select" style="width: 160px"
            :value="configStore.config?.model_provider"
            @change="handleChange('model_provider', $event)"
          >
            <a-select-option
              v-for="(name, idx) in items?.model_provider.choices" :key="idx"
              :value="name">{{ name }}
            </a-select-option>
          </a-select>
        </div>
        <div class="card">
          <span class="label">{{ items?.embed_model.des }} &nbsp;
            <a-button small v-if="needRestart.embed_model" @click="sendRestart">
              <ReloadOutlined />需要重启
            </a-button>
          </span>
          <a-select style="width: 160px"
            :value="configStore.config?.embed_model"
            @change="handleChange('embed_model', $event)"
          >
            <a-select-option
              v-for="(name, idx) in items?.embed_model.choices" :key="idx"
              :value="name">{{ name }}
            </a-select-option>
          </a-select>
        </div>
        <div class="card">
          <span class="label">{{ items?.reranker.des }} &nbsp;
            <a-button small v-if="needRestart.reranker" @click="sendRestart">
              <ReloadOutlined />需要重启
            </a-button>
          </span>
          <a-select style="width: 160px"
            :value="configStore.config?.reranker"
            @change="handleChange('reranker', $event)"
          >
            <a-select-option
              v-for="(name, idx) in items?.reranker.choices" :key="idx"
              :value="name">{{ name }}
            </a-select-option>
          </a-select>
        </div>
      </div>
      <h3>功能配置</h3>
      <div class="section">
        <div class="card">
          <span class="label">{{ items?.enable_knowledge_base.des }}</span>
          <a-switch
            :checked="configStore.config.enable_knowledge_base"
            @change="handleChange('enable_knowledge_base', !configStore.config.enable_knowledge_base)"
          />
        </div>
        <div class="card">
          <span class="label">{{ items?.enable_knowledge_graph.des }}</span>
          <a-switch
            :checked="configStore.config.enable_knowledge_graph"
            @change="handleChange('enable_knowledge_graph', !configStore.config.enable_knowledge_graph)"
          />
        </div>
        <div class="card">
          <span class="label">{{ items?.enable_search_engine.des }}</span>
          <a-switch
            :checked="configStore.config.enable_search_engine"
            @change="handleChange('enable_search_engine', !configStore.config.enable_search_engine)"
          />
        </div>
        <div class="card">
          <span class="label">{{ items?.enable_query_rewrite.des }}</span>
          <a-switch
            :checked="configStore.config.enable_query_rewrite"
            @change="handleChange('enable_query_rewrite', !configStore.config.enable_query_rewrite)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { message } from 'ant-design-vue';
import { computed, reactive, ref } from 'vue'
import { useConfigStore } from '@/stores/config';
import { ReloadOutlined } from '@ant-design/icons-vue';

const configStore = useConfigStore()
const needRestart = reactive({
  model_provider: false,
  embed_model: false,
  reranker: false,
})
const items = computed(() => configStore.config._config_items)
const state = reactive({
  loading: false,
})

const handleChange = (key, e) => {
  console.log('Change', key, e)
  needRestart[key] = true
  configStore.setConfigValue(key, e)
}
const sendRestart = () => {
  console.log('Restarting...')
  message.loading({ content: '重新加载模型中', key: "restart", duration: 0 });
  fetch('/api/restart', {
    method: 'POST',
  }).then(() => {
    console.log('Restarted')
    message.success({ content: '重新加载完成!', key: "restart", duration: 2 });
    setTimeout(() => {
      window.location.reload()
    }, 1000)
  })
}
</script>

<style lang="less" scoped>
.setting-container {
  width: 100%;
  padding: 20px;
}

.setting {
  max-width: 800px;
  margin: 0 auto;

  h3 {
    margin-top: 20px;
  }

  .section {
    margin-top: 20px;
    background-color: var(--main-light-4);
    padding: 20px;
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    // box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    border: 1px solid var(--main-light-3);
  }

  .card {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .label {
      margin-right: 20px;
    }
  }

}


</style>