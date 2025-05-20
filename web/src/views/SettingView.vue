<template>
  <!-- TODO 优化样式，表格优化，添加一个 utils 的函数，用来把时间戳转换为东 8 区的时间，并格式化显示出来 -->
  <div class="">
    <HeaderComponent title="设置" class="setting-header">

      <template #actions>
        <a-button :type="isNeedRestart ? 'primary' : 'default'" @click="sendRestart" :icon="h(ReloadOutlined)">
          {{ isNeedRestart ? '需要刷新' : '重新加载' }}
        </a-button>
      </template>
    </HeaderComponent>
    <div class="setting-container layout-container">
      <div class="sider" v-if="state.windowWidth > 520">
        <a-button type="text" :class="{ activesec: state.section === 'base'}" @click="state.section='base'" :icon="h(SettingOutlined)"> 基本设置 </a-button>
        <a-button type="text" :class="{ activesec: state.section === 'model'}" @click="state.section='model'" :icon="h(CodeOutlined)"> 模型配置 </a-button>
        <a-button type="text" :class="{ activesec: state.section === 'path'}" @click="state.section='path'" :icon="h(FolderOutlined)"> 路径配置 </a-button>
        <a-button type="text" :class="{ activesec: state.section === 'user'}" @click="state.section='user'" :icon="h(UserOutlined)" v-if="userStore.isAdmin"> 用户管理 </a-button>
      </div>
      <div class="setting" v-if="state.windowWidth <= 520 || state.section === 'base'">
        <h3>检索配置</h3>
        <div class="section">
          <div class="card card-select">
            <span class="label">对话模型</span>
            <ModelSelectorComponent
              @select-model="handleChatModelSelect"
              :model_name="configStore.config?.model_name"
              :model_provider="configStore.config?.model_provider"
            />
          </div>
          <div class="card card-select">
            <span class="label">{{ items?.embed_model.des }}</span>
            <a-select style="width: 300px"
              :value="configStore.config?.embed_model"
              @change="handleChange('embed_model', $event)"
            >
              <a-select-option
                v-for="(name, idx) in items?.embed_model.choices" :key="idx"
                :value="name">{{ name }}
              </a-select-option>
            </a-select>
          </div>
          <div class="card card-select">
            <span class="label">{{ items?.reranker.des }}</span>
            <a-select style="width: 300px"
              :value="configStore.config?.reranker"
              @change="handleChange('reranker', $event)"
              :disabled="!configStore.config.enable_reranker"
            >
              <a-select-option
                v-for="(name, idx) in items?.reranker.choices" :key="idx"
                :value="name">{{ name }}
              </a-select-option>
            </a-select>
          </div>
          <div class="card">
            <span class="label">{{ items?.enable_reranker.des }}</span>
            <a-switch
              :checked="configStore.config.enable_reranker"
              @change="handleChange('enable_reranker', !configStore.config.enable_reranker)"
            />
          </div>
          <div class="card card-select">
            <span class="label">{{ items?.use_rewrite_query.des }}</span>
            <a-select style="width: 200px"
              :value="configStore.config?.use_rewrite_query"
              @change="handleChange('use_rewrite_query', $event)"
            >
              <a-select-option
                v-for="(name, idx) in items?.use_rewrite_query.choices" :key="idx"
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
        </div>
      </div>
      <div class="setting" v-if="state.windowWidth <= 520 || state.section === 'model'">
        <h3>模型配置</h3>
        <p>请在 <code>src/.env</code> 文件中配置对应的 APIKEY，并重新启动服务</p>
        <ModelProvidersComponent />
      </div>
      <div class="setting" v-if="state.windowWidth <= 520 || state.section ==='path'">
        <h3>本地模型配置</h3>
        <p>如果是 Docker 启动，务必确保在 docker-compose.dev.yaml 中添加了 volumes 映射。</p>
        <TableConfigComponent
          :config="configStore.config?.model_local_paths"
          @update:config="handleModelLocalPathsUpdate"
        />
      </div>
      <!-- TODO 用户管理优化，添加姓名（默认使用用户名配置项） -->
      <div class="setting" v-if="state.section === 'user'">
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
  ReloadOutlined,
  SettingOutlined,
  CodeOutlined,
  FolderOutlined,
  UserOutlined
} from '@ant-design/icons-vue';
import HeaderComponent from '@/components/HeaderComponent.vue';
import TableConfigComponent from '@/components/TableConfigComponent.vue';
import ModelProvidersComponent from '@/components/ModelProvidersComponent.vue';
import UserManagementComponent from '@/components/UserManagementComponent.vue';
import { notification, Button } from 'ant-design-vue';
import { systemConfigApi } from '@/apis/admin_api'
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue';

const configStore = useConfigStore()
const userStore = useUserStore()
const items = computed(() => configStore.config._config_items)
const isNeedRestart = ref(false)
const state = reactive({
  loading: false,
  section: 'base',
  windowWidth: window?.innerWidth || 0
})

const handleModelLocalPathsUpdate = (config) => {
  handleChange('model_local_paths', config)
}

const preHandleChange = (key, e) => {
  if (key == 'enable_knowledge_graph' && e && !configStore.config.enable_knowledge_base) {
    message.error('启动知识图谱必须请先启用知识库功能')
    return
  }

  if (key == 'enable_knowledge_base' && !e && configStore.config.enable_knowledge_graph) {
    message.error('关闭知识库功能必须请先关闭知识图谱功能')
    return
  }

  if (key == 'enable_reranker'
    || key == 'enable_knowledge_graph'
    || key == 'enable_knowledge_base'
    || key == 'embed_model'
    || key == 'reranker'
    || key == 'model_local_paths') {
    isNeedRestart.value = true
    notification.info({
      message: '需要重新加载模型',
      description: '请点击右下角按钮重新加载模型',
      placement: 'topLeft',
      duration: 0,
      btn: h(Button, { type: 'primary', onClick: sendRestart }, '立即重新加载')
    })
  }
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

const handleChatModelSelect = ({ provider, name }) => {
  configStore.setConfigValues({
    model_provider: provider,
    model_name: name,
  })
}

onMounted(() => {
  updateWindowWidth()
  window.addEventListener('resize', updateWindowWidth)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateWindowWidth)
})

const sendRestart = () => {
  console.log('Restarting...')
  message.loading({ content: '重新加载模型中', key: "restart", duration: 0 });

  systemConfigApi.restartServer()
    .then(() => {
      console.log('Restarted')
      message.success({ content: '重新加载完成!', key: "restart", duration: 2 });
      setTimeout(() => {
        window.location.reload()
      }, 200)
    })
    .catch(error => {
      console.error('重启服务失败:', error)
      message.error({ content: `重启失败: ${error.message}`, key: "restart", duration: 2 });
    });
}
</script>

<style lang="less" scoped>
.setting-container {
  --setting-header-height: 65px;
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
  width: 200px;
  height: 100%;
  padding: 0 20px;
  position: sticky;
  top: var(--setting-header-height);
  display: flex;
  flex-direction: column;
  align-items: center;
  border-right: 1px solid var(--main-light-3);
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
      background: var(--gray-100);
    }

    &.activesec {
      background: var(--gray-200);
      color: var(--gray-900);
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

  h3 {
    margin-top: 20px;
  }

  .section {
    margin-top: 20px;
    background-color: var(--gray-10);
    padding: 20px;
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    // box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    border: 1px solid var(--gray-300);
  }

  .card {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .label {
      margin-right: 20px;

      button {
        margin-left: 10px;
        height: 24px;
        padding: 0 8px;
        font-size: smaller;
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
