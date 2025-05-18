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
              @click="handleChanges({ model_provider: 'custom', model_name: item.custom_id })"
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
                    <a-input-password v-model:value="customModel.api_key" :visibilityToggle="true" autocomplete="new-password"/>
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
                @click="handleChanges({ model_provider: item, model_name: model })"
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
      <!-- TODO 用户管理优化，添加姓名（默认使用用户名配置项） -->
      <div class="setting" v-if="state.section === 'user'">
        <div class="section-header">
          <h2>用户管理</h2>
          <a-button type="primary" @click="showAddUserModal">
            <template #icon><PlusOutlined /></template>
            添加用户
          </a-button>
        </div>

        <a-spin :spinning="userManagement.loading">
          <div v-if="userManagement.error" class="error-message">
            {{ userManagement.error }}
          </div>

          <a-table
            :dataSource="userManagement.users"
            :columns="userColumns"
            rowKey="id"
            :pagination="{ pageSize: 10 }"
          >
            <!-- 角色列自定义渲染 -->
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'role'">
                <a-tag :color="getRoleColor(record.role)">{{ getRoleLabel(record.role) }}</a-tag>
              </template>

              <!-- 操作列 -->
              <template v-if="column.key === 'action'">
                <div class="table-actions">
                  <a-button type="link" @click="showEditUserModal(record)">
                    <EditOutlined />
                  </a-button>
                  <a-button
                    type="link"
                    danger
                    @click="confirmDeleteUser(record)"
                    :disabled="record.id === userStore.userId || (record.role === 'superadmin' && userStore.userRole !== 'superadmin')"
                  >
                    <DeleteOutlined />
                  </a-button>
                </div>
              </template>
            </template>
          </a-table>
        </a-spin>

        <!-- 用户表单模态框 -->
        <a-modal
          v-model:visible="userManagement.modalVisible"
          :title="userManagement.modalTitle"
          @ok="handleUserFormSubmit"
          :confirmLoading="userManagement.loading"
          @cancel="userManagement.modalVisible = false"
          :maskClosable="false"
        >
          <a-form layout="vertical">
            <a-form-item label="用户名" required>
              <a-input v-model:value="userManagement.form.username" placeholder="请输入用户名" />
            </a-form-item>            <template v-if="userManagement.editMode">
              <div class="password-toggle">
                <a-checkbox v-model:checked="userManagement.displayPasswordFields">
                  修改密码
                </a-checkbox>
              </div>
            </template>

            <template v-if="!userManagement.editMode || userManagement.displayPasswordFields">
              <a-form-item label="密码" required>
                <a-input-password v-model:value="userManagement.form.password" placeholder="请输入密码" />
              </a-form-item>

              <a-form-item label="确认密码" required>
                <a-input-password v-model:value="userManagement.form.confirmPassword" placeholder="请再次输入密码" />
              </a-form-item>
            </template>

            <a-form-item label="角色">
              <a-select v-model:value="userManagement.form.role">
                <a-select-option value="user">普通用户</a-select-option>
                <a-select-option value="admin" v-if="userStore.isSuperAdmin">管理员</a-select-option>
                <a-select-option value="superadmin" v-if="userStore.isSuperAdmin">超级管理员</a-select-option>
              </a-select>
            </a-form-item>
          </a-form>
        </a-modal>
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
import { useUserStore } from '@/stores/user'
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
  UserOutlined,
  PlusOutlined
} from '@ant-design/icons-vue';
import HeaderComponent from '@/components/HeaderComponent.vue';
import TableConfigComponent from '@/components/TableConfigComponent.vue';
import { notification, Button } from 'ant-design-vue';
import { modelIcons } from '@/utils/modelIcon'
import { systemConfigApi } from '@/apis/admin_api'
import { chatApi } from '@/apis/auth_api'


const configStore = useConfigStore()
const userStore = useUserStore()
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

// 用户管理相关状态
const userManagement = reactive({
  loading: false,
  users: [],
  error: null,
  modalVisible: false,
  modalTitle: '添加用户',
  editMode: false,
  editUserId: null,
  form: {
    username: '',
    password: '',
    confirmPassword: '',
    role: 'user' // 默认角色
  },
  displayPasswordFields: true, // 编辑时是否显示密码字段
})

// 筛选 modelStatus 中为真的key
const modelKeys = computed(() => {
  return Object.keys(modelStatus.value || {}).filter(key => modelStatus.value?.[key])
})

// 监听密码字段显示状态变化
watch(() => userManagement.displayPasswordFields, (newVal) => {
  // 当取消显示密码字段时，清空密码输入
  if (!newVal) {
    userManagement.form.password = ''
    userManagement.form.confirmPassword = ''
  }
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

// 获取模型提供商的模型列表
const fetchProviderModels = (provider) => {
  providerConfig.loading = true;
  chatApi.getProviderModels(provider)
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
    const data = await chatApi.updateProviderModels(providerConfig.provider, providerConfig.selectedModels);
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

// 获取用户列表
const fetchUsers = async () => {
  try {
    userManagement.loading = true
    const users = await userStore.getUsers()
    userManagement.users = users
    userManagement.error = null
  } catch (error) {
    console.error('获取用户列表失败:', error)
    userManagement.error = '获取用户列表失败'
  } finally {
    userManagement.loading = false
  }
}

// 打开添加用户模态框
const showAddUserModal = () => {
  userManagement.modalTitle = '添加用户'
  userManagement.editMode = false
  userManagement.editUserId = null
  userManagement.form = {
    username: '',
    password: '',
    confirmPassword: '',
    role: 'user'  // 默认角色为普通用户
  }
  userManagement.displayPasswordFields = true
  userManagement.modalVisible = true
}

// 打开编辑用户模态框
const showEditUserModal = (user) => {
  userManagement.modalTitle = '编辑用户'
  userManagement.editMode = true
  userManagement.editUserId = user.id
  userManagement.form = {
    username: user.username,
    password: '',
    confirmPassword: '',
    role: user.role
  }
  userManagement.displayPasswordFields = true // 默认显示密码字段
  userManagement.modalVisible = true
}

// 处理用户表单提交
const handleUserFormSubmit = async () => {
  try {
    // 简单验证
    if (!userManagement.form.username) {
      notification.error({ message: '用户名不能为空' })
      return
    }

    if (userManagement.displayPasswordFields) {
      if (!userManagement.form.password) {
        notification.error({ message: '密码不能为空' })
        return
      }

      if (userManagement.form.password !== userManagement.form.confirmPassword) {
        notification.error({ message: '两次输入的密码不一致' })
        return
      }
    }

    userManagement.loading = true

    // 根据模式决定创建还是更新用户
    if (userManagement.editMode) {
      // 创建更新数据对象
      const updateData = {
        username: userManagement.form.username,
        role: userManagement.form.role
      }

      // 如果显示了密码字段并且填写了密码，才更新密码
      if (userManagement.displayPasswordFields && userManagement.form.password) {
        updateData.password = userManagement.form.password
      }

      await userStore.updateUser(userManagement.editUserId, updateData)
      notification.success({ message: '用户更新成功' })
    } else {
      await userStore.createUser({
        username: userManagement.form.username,
        password: userManagement.form.password,
        role: userManagement.form.role
      })
      notification.success({ message: '用户创建成功' })
    }

    // 重新获取用户列表
    await fetchUsers()
    userManagement.modalVisible = false
  } catch (error) {
    console.error('用户操作失败:', error)
    notification.error({
      message: '操作失败',
      description: error.message || '请稍后重试'
    })
  } finally {
    userManagement.loading = false
  }
}

// 切换是否显示密码字段（编辑用户时使用）
const togglePasswordFields = () => {
  userManagement.displayPasswordFields = !userManagement.displayPasswordFields
  if (!userManagement.displayPasswordFields) {
    userManagement.form.password = ''
    userManagement.form.confirmPassword = ''
  }
}

// 删除用户
const confirmDeleteUser = (user) => {
  // 自己不能删除自己
  if (user.id === userStore.userId) {
    notification.error({ message: '不能删除自己的账户' })
    return
  }

  // 确认对话框
  const { modal } = notification

  modal.confirm({
    title: '确认删除用户',
    content: `确定要删除用户 "${user.username}" 吗？此操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        userManagement.loading = true
        await userStore.deleteUser(user.id)
        notification.success({ message: '用户删除成功' })
        // 重新获取用户列表
        await fetchUsers()
      } catch (error) {
        console.error('删除用户失败:', error)
        notification.error({
          message: '删除失败',
          description: error.message || '请稍后重试'
        })
      } finally {
        userManagement.loading = false
      }
    }
  })
}

// 在组件挂载时，如果选择了用户管理部分，则获取用户列表
const loadUserManagement = async () => {
  if (state.section === 'user') {
    await fetchUsers()
  }
}

// 监听部分切换
watch(() => state.section, async (newSection) => {
  if (newSection === 'user') {
    await fetchUsers()
  }
})

// 用户表格列定义
const userColumns = [
  {
    title: 'ID',
    dataIndex: 'id',
    key: 'id',
    width: 80
  },
  {
    title: '用户名',
    dataIndex: 'username',
    key: 'username'
  },
  {
    title: '角色',
    dataIndex: 'role',
    key: 'role',
    width: 120
  },
  {
    title: '创建时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 180
  },
  {
    title: '最后登录',
    dataIndex: 'last_login',
    key: 'last_login',
    width: 180
  },
  {
    title: '操作',
    key: 'action',
    width: 120
  }
]

// 角色显示辅助函数
const getRoleLabel = (role) => {
  switch (role) {
    case 'superadmin': return '超级管理员'
    case 'admin': return '管理员'
    case 'user': return '普通用户'
    default: return role
  }
}

// 角色标签颜色
const getRoleColor = (role) => {
  switch (role) {
    case 'superadmin': return 'red'
    case 'admin': return 'blue'
    case 'user': return 'green'
    default: return 'default'
  }
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
