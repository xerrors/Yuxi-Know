<template>
  <div class="setting-view">
    <HeaderComponent title="设置" class="setting-header">
    </HeaderComponent>
    <div class="setting-container layout-container">
      <div class="sider" v-if="state.windowWidth > 520">
        <a-button type="text" v-if="userStore.isSuperAdmin" :class="{ activesec: state.section === 'base'}" @click="state.section='base'" :icon="h(SettingOutlined)"> 基本设置 </a-button>
        <a-button type="text" v-if="userStore.isSuperAdmin" :class="{ activesec: state.section === 'model'}" @click="state.section='model'" :icon="h(CodeOutlined)"> 模型配置 </a-button>
        <a-button type="text" :class="{ activesec: state.section === 'user'}" @click="state.section='user'" :icon="h(UserOutlined)" v-if="userStore.isAdmin"> 用户管理 </a-button>
      </div>
      <div class="setting" v-if="(state.windowWidth <= 520 || state.section === 'base') && userStore.isSuperAdmin">
        <h3>检索配置</h3>
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
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span class="label">{{ items?.embed_model.des }}</span>
              <!-- <a-button
                size="small"
                :loading="state.checkingStatus"
                @click="checkAllModelStatus"
                :disabled="state.checkingStatus"
              >
                检查状态
              </a-button> -->
            </div>
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
        <h3>内容审查配置</h3>
        <div class="section">
          <!-- 内容审查配置 -->
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
        <div v-if="userStore.isAdmin">
          <h3>服务链接</h3>
          <p>快速访问系统相关的外部服务，需要将 localhost 替换为实际的 IP 地址。</p>
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
      <div class="setting" v-if="(state.windowWidth <= 520 || state.section === 'model') && userStore.isSuperAdmin">
        <h3>模型配置</h3>
        <p>请在 <code>.env</code> 文件中配置对应的 APIKEY，并重新启动服务</p>
        <ModelProvidersComponent />
      </div>

      <div class="setting" v-if="(state.windowWidth <= 520 || state.section === 'user') && userStore.isAdmin">
         <UserManagementComponent />
      </div>
    </div>
  </div>
</template>

<script setup>
import { message } from 'ant-design-vue';
import { computed, reactive, ref, h, watch, onMounted, onUnmounted } from 'vue'
import { useConfigStore } from '@/stores/config';
import { useUserStore } from '@/stores/user'
import {
  SettingOutlined,
  CodeOutlined,
  FolderOutlined,
  UserOutlined,
  GlobalOutlined
} from '@ant-design/icons-vue';
import HeaderComponent from '@/components/HeaderComponent.vue';
import ModelProvidersComponent from '@/components/ModelProvidersComponent.vue';
import UserManagementComponent from '@/components/UserManagementComponent.vue';
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue';
import EmbeddingModelSelector from '@/components/EmbeddingModelSelector.vue';

const configStore = useConfigStore()
const userStore = useUserStore()
const items = computed(() => configStore.config._config_items)
const state = reactive({
  loading: false,
  section: 'base',
  windowWidth: window?.innerWidth || 0,
})

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

const updateWindowWidth = () => {
  state.windowWidth = window?.innerWidth || 0
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

onMounted(() => {
  updateWindowWidth()
  window.addEventListener('resize', updateWindowWidth)
  state.section = userStore.isSuperAdmin ? 'base' : 'user'
})

onUnmounted(() => {
  window.removeEventListener('resize', updateWindowWidth)
})

const openLink = (url) => {
  window.open(url, '_blank')
}
</script>

<style lang="less" scoped>

.setting-container {
  --setting-header-height: 55px;
  max-width: 1054px;
}

.setting-header {
  height: var(--setting-header-height);
}

.setting-header p {
  margin: 8px 0 0;
}

.setting-container {
  padding: 0;
  box-sizing: border-box;
  display: flex;
  position: relative;
  min-height: calc(100vh - var(--setting-header-height));
}

.sider {
  width: 180px;
  height: 100%;
  padding: 0 20px;
  position: sticky;
  top: var(--setting-header-height);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding-top: 20px;


  & > * {
    width: 100%;
    height: auto;
    padding: 6px 16px;
    cursor: pointer;
    transition: all 0.1s;
    text-align: left;
    font-size: 15px;
    border-radius: 8px;
    color: var(--gray-700);

    &:hover {
      background: var(--gray-50);
    }

    &.activesec {
      background: var(--gray-100);
      color: var(--main-700);
    }
  }
}

.setting {
  width: 100%;
  flex: 1;
  margin: 0 auto;
  height: 100%;
  padding: 0 20px;
  margin-bottom: 40px;

  h3:not(:first-child) {
    margin-top: 30px;
  }
  h3:first-child {
    margin-top: 20px;
  }

  .section {
    margin-top: 10px;
    background-color: var(--gray-0);
    padding: 12px 16px;
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    border: 1px solid var(--gray-150);

    .content-guard-section {
      h4 {
        margin: 0 0 12px 0;
        color: var(--gray-900);
        font-size: 16px;
        font-weight: 600;
        border-bottom: 1px solid var(--gray-150);
        padding-bottom: 8px;
      }
    }
  }

  .card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    // padding: 12px 0;

    .label {
      margin-right: 20px;
      font-weight: 500;
      color: var(--gray-800);

      button {
        margin-left: 10px;
        height: 24px;
        padding: 0 8px;
        font-size: smaller;
      }
    }
  }

  .services-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 12px;
    margin-top: 20px;
  }

  .service-link-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    background: var(--gray-0);
    transition: all 0.2s;
    min-height: 60px;

    &:hover {
      box-shadow: 0 1px 8px var(--gray-200);
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



@media (max-width: 520px) {
  .setting-container {
    flex-direction: column;
  }

  .card.card-select {
    gap: 0.75rem;
    align-items: flex-start;
    flex-direction: column;
  }

  .services-grid {
    gap: 12px;
  }

  .service-link-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
    min-height: auto;
    padding: 12px;

    .service-info {
      text-align: left;
      margin-bottom: 4px;
      margin-right: 0;
    }
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