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
        <a-button type="text" v-if="userStore.isSuperAdmin" :class="{ activesec: state.section === 'base'}" @click="state.section='base'" :icon="h(SettingOutlined)"> 基本设置 </a-button>
        <a-button type="text" v-if="userStore.isSuperAdmin" :class="{ activesec: state.section === 'model'}" @click="state.section='model'" :icon="h(CodeOutlined)"> 模型配置 </a-button>
        <a-button type="text" :class="{ activesec: state.section === 'user'}" @click="state.section='user'" :icon="h(UserOutlined)" v-if="userStore.isAdmin"> 用户管理 </a-button>
      </div>
      <div class="setting" v-if="(state.windowWidth <= 520 || state.section === 'base') && userStore.isSuperAdmin">
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
            >
              <a-select-option
                v-for="(name, idx) in items?.reranker.choices" :key="idx"
                :value="name">{{ name }}
              </a-select-option>
            </a-select>
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
        <p>请在 <code>src/.env</code> 文件中配置对应的 APIKEY，并重新启动服务</p>
        <ModelProvidersComponent />
      </div>

      <!-- TODO 用户管理优化，添加姓名（默认使用用户名配置项） -->
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
  ReloadOutlined,
  SettingOutlined,
  CodeOutlined,
  FolderOutlined,
  UserOutlined,
  GlobalOutlined
} from '@ant-design/icons-vue';
import HeaderComponent from '@/components/HeaderComponent.vue';
import TableConfigComponent from '@/components/TableConfigComponent.vue';
import ModelProvidersComponent from '@/components/ModelProvidersComponent.vue';
import UserManagementComponent from '@/components/UserManagementComponent.vue';
import { notification, Button } from 'ant-design-vue';
import { configApi } from '@/apis/system_api'
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

  if (key == 'enable_reranker'
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
  state.section = userStore.isSuperAdmin ? 'base' : 'user'
})

onUnmounted(() => {
  window.removeEventListener('resize', updateWindowWidth)
})

const sendRestart = () => {
  console.log('Restarting...')
  message.loading({ content: '重新加载模型中', key: "restart", duration: 0 });

  configApi.restartSystem()
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

const openLink = (url) => {
  window.open(url, '_blank')
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
  border-right: 1px solid var(--main-20);
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
    background-color: var(--gray-0);
    padding: 20px;
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    // box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    border: 1px solid var(--gray-200);
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

  .services-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
    margin-top: 20px;

    @media (min-width: 768px) {
      grid-template-columns: repeat(2, 1fr);
    }
  }

    .service-link-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px;
    border: 1px solid var(--gray-300);
    border-radius: 8px;
    background: white;
    transition: all 0.2s;
    min-height: 80px;

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
