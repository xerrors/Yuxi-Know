<template>
  <div class="">
    <HeaderComponent title="设置" class="setting-header">
      <template #description>
        <p>配置文件也可以在 <code>saves/config/base.yaml</code> 中修改</p>
      </template>
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
      </div>
      <div class="setting" v-if="state.windowWidth <= 520 || state.section === 'base'">
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
        <h3>检索配置</h3>
        <div class="section">
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
      </div>
      <div class="setting" v-if="state.windowWidth <= 520 || state.section === 'model'">
        <h3>模型配置</h3>
        <p>请在 <code>src/.env</code> 文件中配置对应的 APIKEY，并重新启动服务</p>
        <div class="model-provider-card">
          <div class="card-header">
            <h3>自定义模型</h3>
          </div>
          <div class="card-body">
            <div
              :class="{'model_selected': modelProvider == 'custom' && configStore.config.model_name == item.custom_id, 'card-models': true, 'custom-model': true}"
              v-for="(item, key) in configStore.config.custom_models" :key="item.custom_id"
              @click="handleChange('model_provider', 'custom'); handleChange('model_name', item.custom_id)"
            >
              <div class="card-models__header">
                <div class="name" :title="item.name">{{ item.name }}</div>
                <div class="action">
                  <a-popconfirm
                    title="确认删除该模型?"
                    @confirm="handleDeleteCustomModel(item.custom_id)"
                    okText="确认删除"
                    cancelText="取消"
                    ok-type="danger"
                    :disabled="configStore.config.model_name == item.name"
                  >
                    <a-button type="text" :disabled="configStore.config.model_name == item.name"  @click.stop><DeleteOutlined /></a-button>
                  </a-popconfirm>
                  <a-button type="text" @click.stop="prepareToEditCustomModel(item)"><EditOutlined /></a-button>
                </div>
              </div>
              <div class="api_base">{{ item.api_base }}</div>
            </div>
            <div class="card-models custom-model" @click="prepareToAddCustomModel">
              <div class="card-models__header">
                <div class="name"> + 添加模型</div>
              </div>
              <div class="api_base">添加兼容 OpenAI 的模型</div>
              <a-modal
                class="custom-model-modal"
                v-model:open="customModel.visible"
                :title="customModel.modelTitle"
                @ok="handleAddOrEditCustomModel"
                @cancel="handleCancelCustomModel"
                :okText="'确认'"
                :cancelText="'取消'"
                :okButtonProps="{disabled: !customModel.name || !customModel.api_base}"
                :ok-type="'primary'"
              >
                <p>添加的模型是兼容 OpenAI 的模型，比如 vllm，Ollama。</p>
                <a-form :model="customModel" layout="vertical" >
                  <a-form-item label="模型名称" name="name" :rules="[{ required: true, message: '请输入模型名称' }]">
                    <p class="form-item-description">调用的模型的名称</p>
                    <a-input v-model:value="customModel.name" :disabled="customModel.edit_type == 'edit'"/>
                  </a-form-item>
                  <a-form-item label="API Base" name="api_base" :rules="[{ required: true, message: '请输入API Base' }]">
                    <p class="form-item-description">比如 <code>http://localhost:11434/v1</code></p>
                    <a-input v-model:value="customModel.api_base" />
                  </a-form-item>
                  <a-form-item label="API KEY" name="api_key">
                    <a-input-password v-model:value="customModel.api_key" :visibilityToggle="false" autocomplete="new-password"/>
                  </a-form-item>
                </a-form>
              </a-modal>
            </div>
          </div>
        </div>
        <div class="model-provider-card" v-for="(item, key) in modelKeys" :key="key">
          <div class="card-header" @click="toggleExpand(item)">
            <!-- <div v-if="modelStatus[item]" class="success"></div> -->
            <div :class="{'model-icon': true, 'available': modelStatus[item]}">
              <img :src="modelIcons[item] || modelIcons.default" alt="模型图标">
            </div>
            <div class="model-title-container">
              <h3>{{ modelNames[item].name }}</h3>
              <!-- <a :href="modelNames[item].url" target="_blank" class="model-url" @click.stop>
                <InfoCircleOutlined />
              </a> -->
            </div>
            <a-button
              type="text"
              class="expand-button"
              @click.stop="openProviderConfig(item)"
              title="配置模型提供商"
            >
              <SettingOutlined />
            </a-button>
            <a-button
              type="text"
              class="expand-button"
              @click.stop="toggleExpand(item)"
            >
              <span class="icon-wrapper" :class="{'rotated': expandedModels[item]}">
                <DownCircleOutlined />
              </span>
            </a-button>
          </div>
          <div class="card-body-wrapper" :class="{'expanded': expandedModels[item]}">
            <div class="card-body" v-if="modelStatus[item]">
              <div
                :class="{'model_selected': modelProvider == item && configStore.config.model_name == model, 'card-models': true}"
                v-for="(model, idx) in modelNames[item].models" :key="idx"
                @click="handleChange('model_provider', item); handleChange('model_name', model)"
              >
                <div class="model_name">{{ model }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="model-provider-card" v-for="(item, key) in notModelKeys" :key="key">
          <div class="card-header">
            <div class="model-icon">
              <img :src="modelIcons[item] || modelIcons.default" alt="模型图标">
            </div>
            <div class="model-title-container">
              <h3 style="font-weight: 400">{{ modelNames[item].name }}</h3>
              <a :href="modelNames[item].url" target="_blank" class="model-url">
                <InfoCircleOutlined />
              </a>
            </div>
            <a-button
              type="text"
              class="config-button"
              @click.stop="openProviderConfig(item)"
              title="配置模型提供商"
            >
              <SettingOutlined />
            </a-button>
            <div class="missing-keys">
              需配置<span v-for="(key, idx) in modelNames[item].env" :key="idx">{{ key }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="setting" v-if="state.windowWidth <= 520 || state.section ==='path'">
        <h3>本地模型配置</h3>
        <p>如果是 Docker 启动，务必确保在 docker-compose.dev.yaml 中添加了 volumes 映射。</p>
        <TableConfigComponent
          :config="configStore.config?.model_local_paths"
          @update:config="handleModelLocalPathsUpdate"
        />
      </div>
    </div>
    <a-modal
      class="provider-config-modal"
      v-model:open="providerConfig.visible"
      :title="`配置${providerConfig.providerName}模型`"
      @ok="saveProviderConfig"
      @cancel="cancelProviderConfig"
      :okText="'保存配置'"
      :cancelText="'取消'"
      :ok-type="'primary'"
      :width="800"
      :bodyStyle="{ padding: '16px 24px' }"
    >
      <div v-if="providerConfig.loading" class="modal-loading-container">
        <a-spin :indicator="h(LoadingOutlined, { style: { fontSize: '32px', color: 'var(--main-color)' }})" />
        <div class="loading-text">正在获取模型列表...</div>
      </div>
      <div v-else class="modal-config-content">
        <div class="modal-config-header">
          <h3>选择 {{ providerConfig.providerName }} 的模型</h3>
          <p class="description">勾选您希望在系统中启用的模型，请注意，列表中可能包含非对话模型，请仔细甄别。</p>
        </div>

        <div class="modal-models-section">
          <div class="modal-checkbox-list">
            <a-checkbox-group v-model:value="providerConfig.selectedModels">
              <div v-for="(model, index) in providerConfig.allModels" :key="index" class="modal-checkbox-item">
                <a-checkbox :value="model.id">{{ model.id }}</a-checkbox>
              </div>
            </a-checkbox-group>
          </div>
          <div v-if="providerConfig.allModels.length === 0" class="modal-no-models">
            <a-alert v-if="!modelStatus[providerConfig.provider]" type="warning" message="请在 src/.env 中配置对应的 APIKEY，并重新启动服务" />
            <div v-else>
              <a-alert type="warning" message="该提供商暂未适配获取模型列表的方法，如果需要添加模型，请在 src/static/models.private.yml 中添加。" />
              <img src="@/assets/pics/guides/how-to-add-models.png" alt="添加模型指引" style="width: 100%; height: 100%;">
            </div>
          </div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { message } from 'ant-design-vue';
import { computed, reactive, ref, h, watch, onMounted, onUnmounted } from 'vue'
import { useConfigStore } from '@/stores/config';
import {
  ReloadOutlined,
  SettingOutlined,
  CodeOutlined,
  ExceptionOutlined,
  FolderOutlined,
  DeleteOutlined,
  EditOutlined,
  InfoCircleOutlined,
  DownOutlined,
  UpOutlined,
  LoadingOutlined,
  UpCircleOutlined,
  DownCircleOutlined,
} from '@ant-design/icons-vue';
import HeaderComponent from '@/components/HeaderComponent.vue';
import TableConfigComponent from '@/components/TableConfigComponent.vue';
import { notification, Button } from 'ant-design-vue';
import { modelIcons } from '@/utils/modelIcon'


const configStore = useConfigStore()
const items = computed(() => configStore.config._config_items)
const modelNames = computed(() => configStore.config?.model_names)
const modelStatus = computed(() => configStore.config?.model_provider_status)
const modelProvider = computed(() => configStore.config?.model_provider)
const isNeedRestart = ref(false)
const customModel = reactive({
  modelTitle: '添加自定义模型',
  visible: false,
  custom_id: '',
  name: '',
  api_key: '',
  api_base: '',
  edit_type: 'add',
})
const providerConfig = reactive({
  visible: false,
  provider: '',
  providerName: '',
  models: [],
  allModels: [], // 所有可用的模型
  selectedModels: [], // 用户选择的模型
  loading: false,
})
const state = reactive({
  loading: false,
  section: 'base',
  windowWidth: window?.innerWidth || 0
})

// 筛选 modelStatus 中为真的key
const modelKeys = computed(() => {
  return Object.keys(modelStatus.value || {}).filter(key => modelStatus.value?.[key])
})

const notModelKeys = computed(() => {
  return Object.keys(modelStatus.value || {}).filter(key => !modelStatus.value?.[key])
})

// 模型展开状态管理
const expandedModels = reactive({})

// 监听 modelKeys 变化，确保新添加的模型也是默认展开状态
watch(modelKeys, (newKeys) => {
  newKeys.forEach(key => {
    if (expandedModels[key] === undefined) {
      expandedModels[key] = true
    }
  })
}, { immediate: true })

// 切换展开状态的方法
const toggleExpand = (item) => {
  expandedModels[item] = !expandedModels[item]
}

const generateRandomHash = (length) => {
  let chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let hash = '';
  for (let i = 0; i < length; i++) {
      hash += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return hash;
}

const handleModelLocalPathsUpdate = (config) => {
  handleChange('model_local_paths', config)
}

const handleChange = (key, e) => {
  if (key == 'enable_knowledge_graph' && e && !configStore.config.enable_knowledge_base) {
    message.error('启动知识图谱必须请先启用知识库功能')
    return
  }

  if (key == 'enable_knowledge_base' && !e && configStore.config.enable_knowledge_graph) {
    message.error('关闭知识库功能必须请先关闭知识图谱功能')
    return
  }

  // 这些都是需要重启的配置
  if (key == 'enable_reranker'
        || key == 'enable_knowledge_graph'
        || key == 'enable_knowledge_base'
        || key == 'enable_web_search'
        || key == 'embed_model'
        || key == 'reranker'
        || key == 'model_local_paths') {
    if (!isNeedRestart.value) {
      isNeedRestart.value = true
      notification.info({
        message: '需要重新加载模型',
        description: '请点击右下角按钮重新加载模型',
        placement: 'topLeft',
        duration: 0,
        btn: h(Button, { type: 'primary', onClick: sendRestart }, '立即重新加载')
      })
    }
  }

  configStore.setConfigValue(key, e)
}

const handleAddOrEditCustomModel = async () => {
  if (!customModel.name || !customModel.api_base) {
    message.error('请填写完整的模型名称和API Base信息。')
    return
  }

  let custom_models = configStore.config.custom_models || [];

  const model_info = {
    custom_id: customModel.custom_id || `${customModel.name}-${generateRandomHash(4)}`,
    name: customModel.name,
    api_key: customModel.api_key,
    api_base: customModel.api_base,
  }

  if (customModel.edit_type === 'add') {
    if (custom_models.find(item => item.custom_id === customModel.custom_id)) {
      message.error('模型ID已存在')
      return
    }
    custom_models.push(model_info)
  } else {
    // 如果 custom_id 相同，则更新
    custom_models = custom_models.map(item => item.custom_id === customModel.custom_id ? model_info : item);
  }

  customModel.visible = false;
  await configStore.setConfigValue('custom_models', custom_models);
  message.success(customModel.edit_type === 'add' ? '模型添加成功' : '模型修改成功');
}

const handleDeleteCustomModel = (custom_id) => {
  const updatedModels = configStore.config.custom_models.filter(item => item.custom_id !== custom_id);
  configStore.setConfigValue('custom_models', updatedModels);
}

const prepareToEditCustomModel = (item) => {
  customModel.modelTitle = '编辑自定义模型'
  customModel.custom_id = item.custom_id
  customModel.visible = true
  customModel.edit_type = 'edit'
  customModel.name = item.name
  customModel.api_key = item.api_key
  customModel.api_base = item.api_base
}

const prepareToAddCustomModel = () => {
  customModel.modelTitle = '添加自定义模型'
  customModel.edit_type = 'add'
  customModel.visible = true
  clearCustomModel()
}

const clearCustomModel = () => {
  customModel.custom_id = ''
  customModel.name = ''
  customModel.api_key = ''
  customModel.api_base = ''
}

const handleCancelCustomModel = () => {
  clearCustomModel()
  customModel.visible = false
}

const updateWindowWidth = () => {
  state.windowWidth = window?.innerWidth || 0
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
  fetch('/api/restart', {
    method: 'POST',
  }).then(() => {
    console.log('Restarted')
    message.success({ content: '重新加载完成!', key: "restart", duration: 2 });
    setTimeout(() => {
      window.location.reload()
    }, 200)
  })
}

// 获取模型提供商的模型列表
const fetchProviderModels = (provider) => {
  providerConfig.loading = true;
  fetch(`/api/chat/models?model_provider=${provider}`)
    .then(response => response.json())
    .then(data => {
      console.log(`${provider} 模型列表:`, data);

      // 处理各种可能的API返回格式
      let modelsList = [];

      // 情况1: { data: [...] }
      if (data.data && Array.isArray(data.data)) {
        modelsList = data.data;
      }
      // 情况2: { models: [...] } (字符串数组)
      else if (data.models && Array.isArray(data.models)) {
        modelsList = data.models.map(model => typeof model === 'string' ? { id: model } : model);
      }
      // 情况3: { models: { data: [...] } }
      else if (data.models && data.models.data && Array.isArray(data.models.data)) {
        modelsList = data.models.data;
      }

      console.log("处理后的模型列表:", modelsList);
      providerConfig.allModels = modelsList;
      providerConfig.loading = false;
    })
    .catch(error => {
      console.error(`获取${provider}模型列表失败:`, error);
      message.error({ content: `获取${modelNames.value[provider].name}模型列表失败`, duration: 2 });
      providerConfig.loading = false;
    });
}

const openProviderConfig = (provider) => {
  providerConfig.provider = provider;
  providerConfig.providerName = modelNames.value[provider].name;
  providerConfig.allModels = [];
  providerConfig.visible = true;
  providerConfig.loading = true;

  // 获取当前选择的模型作为初始选中值
  const currentModels = modelNames.value[provider]?.models || [];
  providerConfig.selectedModels = [...currentModels];

  // 获取所有可用模型
  fetchProviderModels(provider);
}

const saveProviderConfig = async () => {
  if (!modelStatus.value[providerConfig.provider]) {
    message.error('请在 src/.env 中配置对应的 APIKEY，并重新启动服务')
    return
  }

  message.loading({ content: '保存配置中...', key: 'save-config', duration: 0 });

  try {
    // 发送选择的模型列表到后端
    const response = await fetch(`/api/chat/models/update?model_provider=${providerConfig.provider}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(providerConfig.selectedModels),
    });

    if (!response.ok) {
      throw new Error('保存模型配置失败');
    }

    const data = await response.json();
    console.log('更新后的模型列表:', data.models);

    message.success({ content: '模型配置已保存!', key: 'save-config', duration: 2 });

    // 关闭弹窗
    providerConfig.visible = false;

    // 刷新配置
    configStore.refreshConfig();

  } catch (error) {
    console.error('保存配置失败:', error);
    message.error({ content: '保存配置失败: ' + error.message, key: 'save-config', duration: 2 });
  }
}

const cancelProviderConfig = () => {
  providerConfig.visible = false;
}
</script>

<style lang="less" scoped>
:root {
  --setting-header-height: 200px;
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
  top: 100px;
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

  .model-provider-card {
    border: 1px solid var(--gray-300);
    background-color: white;
    border-radius: 8px;
    margin-bottom: 12px;
    padding: 12px;
    .card-header {
      display: flex;
      align-items: center;
      gap: 10px;
      cursor: pointer;

      .model-title-container {
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 10px;
        flex: 1;
      }

      .model-url {
        font-size: 12px;
        width: fit-content;
        color: var(--gray-500);
      }

      .model-icon {
        width: 28px;
        height: 28px;

        // 灰度
        filter: grayscale(100%);
        img {
          width: 100%;
          height: 100%;
          border-radius: 4px;
          border: 1px solid var(--gray-300);
        }

        &.available {
          filter: grayscale(0%);
        }
      }

      h3 {
        margin: 0;
        font-size: 0.9rem;
        font-weight: bold;
      }

      a {
        text-decoration: none;
        color: var(--gray-500);
        font-size: 12px;
        transition: all 0.1s;

        &:hover {
          color: var(--gray-900);
        }
      }

      .details, .missing-keys {
        margin-left: auto;
      }

      .success {
        width: 0.75rem;
        height: 0.75rem;
        background-color: rgb(91, 186, 91);
        border-radius: 50%;
        box-shadow: 0 0 10px 1px rgba(  0,128,  0, 0.1);
        border: 2px solid white;
      }

      .missing-keys {
        margin-top: 4px;
        color: var(--gray-600);
        font-size: 12px;
        & > span {
          margin-left: 6px;
          user-select: all;
          background-color: var(--gray-100);
          padding: 2px 6px;
          border-radius: 4px;
          color: var(--gray-800);
        }
      }

      .expand-button {
        margin-left: auto;
        height: 32px;
        width: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0;
        cursor: pointer;
        color: var(--gray-500);

        &:hover {
          background-color: var(--gray-100);
        }

        .icon-wrapper {
          display: inline-flex;
          transition: transform 0.2s ease;

          &.rotated {
            transform: rotate(180deg);
          }
        }
      }
    }

    .card-body-wrapper {
      max-height: 0;
      overflow: hidden;
      transition: max-height 0.2s ease-out;  // 先快后慢

      &.expanded {
        max-height: 700px; /* 设置一个足够大的值 */
      }
    }

    .card-body {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 12px;
      margin-top: 10px;
      .card-models {
        width: 100%;
        border-radius: 8px;
        border: 1px solid var(--gray-300);
        padding: 12px 16px;
        display: flex;
        gap: 6px;
        justify-content: space-between;
        align-items: center;
        cursor: pointer;
        box-sizing: border-box;
        background-color: var(--gray-50);
        transition: box-shadow 0.1s;
        &:hover {
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }
        .model_name {
          font-size: 14px;
          color: var(--gray-900);
        }
        .select-btn {
          width: 16px;
          height: 16px;
          flex: 0 0 16px;
          border-radius: 50%;
        }

        &.model_selected {
          border: 2px solid var(--main-color);
          padding: 9px 15px;
          .model_name {
            color: var(--gray-1000)
          }
          .select-btn {
            border-color: var(--main-color);
            border: 2px solid var(--main-color);
          }
        }

        &.custom-model {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          padding-right: 8px;
          gap: 10px;
          .card-models__header {
            width: 100%;
            height: 24px;
            display: flex;
            justify-content: flex-start;
            align-items: center;
            .name {
              color: var(--gray-1000);
              overflow: hidden;
              text-overflow: ellipsis;
              white-space: nowrap;
              flex: 1;
              margin-right: 8px;
              position: relative;

              &:hover::after {
                content: attr(title);
                position: absolute;
                left: 0;
                top: 100%;
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                white-space: nowrap;
                z-index: 1000;
                margin-top: 5px;
              }
            }
            .action {
              opacity: 0;
              user-select: none;
              margin-left: auto;
              flex-shrink: 0;
              button {
                padding: 4px 8px;
              }
            }
            .custom-model-modal {
              .ant-form-item {
                margin-bottom: 10px;
                .form-item-description {
                  font-size: 12px;
                  color: var(--gray-600);
                  margin-bottom: 10px;
                }
              }
            }
          }
          .api_base {
            font-size: 12px;
            color: var(--gray-600);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            width: 100%;
          }

          &:hover {
            .card-models__header {
              .action {
                opacity: 1;
              }
            }
          }
        }
        &.model_selected.custom-model {
          padding: 9px 7px 9px 15px;
          .card-models__header {
            .action {
              opacity: 1;
            }
          }
        }
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

.provider-config-modal {
  .ant-modal-body {
    padding: 16px 0 !important;
    .modal-loading-container {
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      height: 200px;

      .loading-text {
        margin-top: 20px;
        color: var(--gray-700);
        font-size: 14px;
      }
    }

    .modal-config-content {
      max-height: 70vh;
      overflow-y: auto;
      // padding-right: 10px;

      .modal-config-header {
        margin-bottom: 20px;

        .description {
          font-size: 14px;
          color: var(--gray-600);
          margin: 0;
        }
      }

      .modal-models-section {
        .modal-checkbox-list {
          max-height: 50vh;
          overflow-y: auto;
          .modal-checkbox-item {
            margin-bottom: 4px;
            padding: 4px 6px;
            border-radius: 6px;
            background-color: white;
            border: 1px solid var(--gray-200);

            &:hover {
              background-color: var(--gray-50);
            }
          }
        }
      }
    }
  }
}
</style>
