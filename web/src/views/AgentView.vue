<template>
  <div class="agent-view">
    <div class="agent-view-header">
      <div class="header-left">
        <div class="header-item">
          <a-button class="header-button" @click="toggleSidebar">
            <template #icon><MenuOutlined /></template>
          </a-button>
        </div>
        <div class="header-item">
          <a-select
            v-model:value="selectedAgentId"
            class="agent-list"
            style="width: 200px"
            @change="selectAgent"
          >
            <a-select-option
              v-for="(agent, name) in agents"
              :key="name"
              :value="name"
            >
              <div class="agent-option">
                智能体：{{ agent.name }}
                <StarFilled v-if="name === defaultAgentId" class="default-icon" />
              </div>
            </a-select-option>
          </a-select>
        </div>
      </div>
      <div class="header-center">
      </div>
      <div class="header-right">
        <div class="header-item">
          <a-button
            class="header-button"
            @click="goToAgentPage"
            v-if="selectedAgentId"
          >
            <template #icon><LinkOutlined /></template>
            打开独立页面
          </a-button>

          <a-tooltip :title="isDefaultAgent ? '当前为默认智能体' : '设为默认智能体'" placement="left">
            <a-button
              class="header-button primary-action"
              @click="setAsDefaultAgent"
              v-if="selectedAgentId && userStore.isAdmin"
              :disabled="isDefaultAgent"
          >
              <template #icon><StarOutlined /></template>
            </a-button>
          </a-tooltip>

        </div>
      </div>
    </div>
    <div class="agent-view-body">
      <!-- 左侧智能体列表侧边栏 -->
      <div class="sidebar" :class="{ 'is-open': state.agentSiderbarConfigOpen }">
        <div class="agent-info">
          <h3 @click="toggleDebugMode">描述</h3>
          <p>{{ selectedAgent.description }}</p>
          <pre v-if="state.debug_mode">{{ selectedAgent }}</pre>

          <div v-if="selectedAgentId && configSchema" class="config-modal-content">
            <!-- 配置表单 -->
            <a-form :model="agentConfig" layout="vertical">
              <a-alert  v-if="state.isEmptyConfig" type="warning" message="该智能体没有配置项" show-icon/>
              <a-alert v-if="!selectedAgent.has_checkpointer" type="error" message="该智能体没有配置 Checkpointer，功能无法正常使用，参考：https://langchain-ai.github.io/langgraph/concepts/persistence/" show-icon/>
              <!-- 统一显示所有配置项 -->
              <template v-for="(value, key) in configurableItems" :key="key">
                <a-form-item
                  :label="getConfigLabel(key, value)"
                  :name="key"
                  class="config-item"
                >
                  <p v-if="value.description" class="description">{{ value.description }}</p>

                  <div v-if="key === 'model'" class="agent-model">
                    <p><small>注意，部分模型对于 Tool Calling 的支持不稳定，建议采用{{ value.options }} </small></p>
                    <ModelSelectorComponent
                      @select-model="handleModelChange"
                      :model_name="agentConfig[key] ? agentConfig[key].split('/').slice(1).join('/') : ''"
                      :model_provider="agentConfig[key] ? agentConfig[key].split('/')[0] : ''"
                    />
                  </div>
                  <a-switch
                    v-else-if="typeof agentConfig[key] === 'boolean'"
                    v-model:checked="agentConfig[key]"
                  />
                  <a-textarea
                    v-else-if="key === 'system_prompt'"
                    v-model:value="agentConfig[key]"
                    :rows="4"
                    :placeholder="getPlaceholder(key, value)"
                  />
                  <a-select
                    v-else-if="value?.options && value?.type === 'str'"
                    v-model:value="agentConfig[key]"
                  >
                    <a-select-option v-for="option in value.options" :key="option" :value="option"></a-select-option>
                  </a-select>
                  <a-select
                    v-else-if="value?.options && value?.type === 'list'"
                    v-model:value="agentConfig[key]"
                    mode="multiple"
                  >
                    <a-select-option v-for="option in value.options" :key="option" :value="option"></a-select-option>
                  </a-select>
                  <a-input
                    v-else
                    v-model:value="agentConfig[key]"
                    :placeholder="getPlaceholder(key, value)"
                  />
                </a-form-item>
              </template>

              <!-- 弹窗底部按钮 -->
              <div class="form-actions" v-if="!state.isEmptyConfig">
                <div class="form-actions-left">
                  <a-button type="primary" @click="saveConfig">保存并发布配置</a-button>
                  <a-button @click="resetConfig">重置</a-button>
                </div>
              </div>
            </a-form>
          </div>

          <!-- 添加requirements显示部分 -->
          <div v-if="agents[selectedAgentId]?.requirements && agents[selectedAgentId]?.requirements.length > 0" class="info-section">
            <h3>所需环境变量:</h3>
            <div class="requirements-list">
              <a-tag v-for="req in agents[selectedAgentId].requirements" :key="req">
                {{ req }}
              </a-tag>
            </div>
          </div>
        </div>
      </div>

      <!-- 中间内容区域 -->
      <div class="content">
        <AgentChatComponent
          :agent-id="selectedAgentId"
          :config="agentConfig"
          :state="state"
          @open-config="toggleConfigSidebar(true)"
        >
        </AgentChatComponent>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch, computed, h } from 'vue';
import { useRouter } from 'vue-router';
import {
  CloseOutlined,
  SettingOutlined,
  LinkOutlined,
  StarOutlined,
  MenuOutlined,
  StarFilled
} from '@ant-design/icons-vue';
import { message } from 'ant-design-vue';
import AgentChatComponent from '@/components/AgentChatComponent.vue';
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue';
import { useUserStore } from '@/stores/user';
import { chatApi } from '@/apis/auth_api';
import { systemConfigApi } from '@/apis/admin_api';

// 路由
const router = useRouter();
const userStore = useUserStore();

// 状态
const agents = ref({});
const selectedAgentId = ref(null);
const defaultAgentId = ref(null); // 存储默认智能体ID
const state = reactive({
  agentSiderbarConfigOpen: true,
  debug_mode: false,
  isEmptyConfig: computed(() =>
    !selectedAgentId.value ||
    Object.keys(configurableItems.value).length === 0
  )
});

const selectedAgent = computed(() => agents.value[selectedAgentId.value] || {});
const configSchema = computed(() => selectedAgent.value.config_schema || {});
const configurableItems = computed(() => configSchema.value.configurable_items || {});

// 配置状态
const agentConfig = ref({});

// 检查是否为默认智能体
const isDefaultAgent = computed(() => {
  return selectedAgentId.value === defaultAgentId.value;
});

// 设置为默认智能体
const setAsDefaultAgent = async () => {
  if (!selectedAgentId.value || !userStore.isAdmin) return;

  try {
    await systemConfigApi.setDefaultAgent(selectedAgentId.value);
    defaultAgentId.value = selectedAgentId.value;
    message.success('已将当前智能体设为默认');
  } catch (error) {
    console.error('设置默认智能体错误:', error);
    message.error(error.message || '设置默认智能体时发生错误');
  }
};

// 获取默认智能体ID
const fetchDefaultAgent = async () => {
  try {
    const data = await chatApi.getDefaultAgent();
    defaultAgentId.value = data.default_agent_id;
    console.log("Default agent ID:", defaultAgentId.value);
  } catch (error) {
    console.error('获取默认智能体错误:', error);
  }
};

// 获取智能体列表
const fetchAgents = async () => {
  try {
    const data = await chatApi.getAgents();
    // 将数组转换为对象
    agents.value = data.agents.reduce((acc, agent) => {
      acc[agent.name] = agent;
      return acc;
    }, {});
    // console.log("agents", agents.value);

    // 加载当前选中智能体的配置
    if (selectedAgentId.value) {
      loadAgentConfig();
    }
  } catch (error) {
    console.error('获取智能体错误:', error);
  }
};

// 根据选中的智能体加载配置
const loadAgentConfig = async () => {
  // BUG: 目前消息重置有问题，需要重置消息
  if (!selectedAgentId.value || !agents.value[selectedAgentId.value]) return;

  const agent = agents.value[selectedAgentId.value];
  const schema = agent.config_schema || {};
  const items = schema.configurable_items || {};

  // 重置配置
  agentConfig.value = {};

  // 初始化基础配置项
  if (schema.system_prompt) {
    agentConfig.value.system_prompt = schema.system_prompt;
  }

  if (schema.model) {
    agentConfig.value.model = schema.model;
  }

  if (schema.tools && schema.tools.length > 0 && schema.tools[0] != 'undefined') {
    agentConfig.value.tools = schema.tools;
  }

  // 初始化可配置项
  Object.keys(items).forEach(key => {
    const item = items[key];

    // 根据类型设置默认值
    if (typeof item.default === 'boolean') {
      agentConfig.value[key] = item.default;
    } else {
      agentConfig.value[key] = item.default || '';
    }
  });

  try {
    // 从服务器加载配置
    const response = await systemConfigApi.getAgentConfig(selectedAgentId.value);
    if (response.success && response.config) {
      // 合并服务器配置
      Object.keys(response.config).forEach(key => {
        if (key in agentConfig.value) {
          agentConfig.value[key] = response.config[key];
        }
      });
      console.log(`从服务器加载 ${selectedAgentId.value} 配置成功, ${JSON.stringify(agentConfig.value)}`);
    }
  } catch (error) {
    console.error('从服务器加载配置出错:', error);
  }
};

const handleModelChange = (data) => {
  agentConfig.value.model = `${data.provider}/${data.name}`;
}

// 保存配置
const saveConfig = async () => {
  if (!selectedAgentId.value) {
    message.error('没有选择智能体');
    return;
  }

  try {
    // 保存配置到服务器
    await systemConfigApi.saveAgentConfig(selectedAgentId.value, agentConfig.value);
    // 提示保存成功
    message.success('配置已保存到服务器');
    console.log("保存配置:", agentConfig.value);
  } catch (error) {
    console.error('保存配置到服务器出错:', error);
    message.error('保存配置到服务器失败');
  }
};

// 重置配置
const resetConfig = async () => {
  if (!selectedAgentId.value) {
    message.error('没有选择智能体');
    return;
  }

  try {
    // 保存空配置到服务器，相当于重置
    await systemConfigApi.saveAgentConfig(selectedAgentId.value, {});
    // 重新加载默认配置
    await loadAgentConfig();
    message.info('配置已重置');
  } catch (error) {
    console.error('重置配置出错:', error);
    message.error('重置配置失败');
  }
};

// 监听智能体选择变化
watch(
  () => selectedAgentId.value,
  () => {
    loadAgentConfig();
  }
);

// 选择智能体
const selectAgent = (agentId) => {
  selectedAgentId.value = agentId;
  // 保存选择到本地存储
  localStorage.setItem('last-selected-agent', agentId);
  // 加载该智能体的配置
  loadAgentConfig();
};

// 初始化
onMounted(async () => {
  // 获取默认智能体
  await fetchDefaultAgent();
  // 获取智能体列表
  await fetchAgents();

  // 恢复上次选择的智能体
  const lastSelectedAgent = localStorage.getItem('last-selected-agent');
  if (lastSelectedAgent && agents.value[lastSelectedAgent]) {
    selectedAgentId.value = lastSelectedAgent;
  } else if (defaultAgentId.value && agents.value[defaultAgentId.value]) {
    // 如果有默认智能体，优先选择默认智能体
    selectedAgentId.value = defaultAgentId.value;
  } else if (Object.keys(agents.value).length > 0) {
    // 默认选择第一个智能体
    selectedAgentId.value = Object.keys(agents.value)[0];
  }

  // 加载配置
  loadAgentConfig();
});

// 获取配置标签
const getConfigLabel = (key, value) => {
  // 根据配置项属性选择合适的显示文本
  if (value.description) {
    return `${value.name}（${key}）`;
  }
  return key;
};

// 获取占位符
const getPlaceholder = (key, value) => {
  // 返回描述作为占位符
  return `（默认: ${value.default}）` ;
};

// 跳转到独立智能体页面
const goToAgentPage = () => {
  if (selectedAgentId.value) {
    window.open(`/agent/${selectedAgentId.value}`, '_blank');
  }
};

const toggleDebugMode = () => {
  state.debug_mode = !state.debug_mode;
  console.log("debug_mode", state.debug_mode);
};

const toggleSidebar = () => {
  state.agentSiderbarConfigOpen = !state.agentSiderbarConfigOpen
}
</script>

<style lang="less" scoped>
.agent-view {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  --agent-view-header-height: 60px;
  --agent-sidebar-width: 450px;
}

.agent-view-header {
  height: var(--agent-view-header-height);
  background-color: var(--bg-sider);
  border-bottom: 1px solid var(--main-light-3);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px;

  .header-left,
  .header-right,
  .header-center {
    display: flex;
    flex-direction: row;
    gap: 10px;
  }

  .header-item {
    display: flex;
    align-items: center;
    gap: 10px;
  }
}

.agent-view-body {
  --gap-radius: 6px;
  display: flex;
  width: 100%;
  flex: 1;
  min-height: calc(100% - var(--agent-view-header-height));
  overflow: hidden;
  padding: var(--gap-radius);
  gap: var(--gap-radius);

  .sidebar.is-open,
  .content {
    border-radius: var(--gap-radius);
    border: 1px solid var(--gray-300);
  }
}

.sidebar {
  width: 0;
  max-width: var(--agent-sidebar-width);
  background-color: var(--bg-sider);
  overflow-y: auto;
  transition: width 0.3s ease;
  overflow: hidden;

  &.is-open {
    width: var(--agent-sidebar-width);
    box-sizing: content-box;
  }
}

.sidebar-title {
  height: var(--header-height);
  font-weight: bold;
  user-select: none;
  white-space: nowrap;
  overflow: hidden;
  padding-bottom: 1rem;
  font-size: 1rem;
  border-bottom: 1px solid var(--main-light-3);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  margin: 0;
}


.agent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-item {
  display: flex;
  align-items: center;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.3s;

  &:hover {
    background-color: var(--main-light-4);
  }

  &.active {
    background-color: var(--main-light-3);
  }
}

.agent-info {
  padding: 16px;
  min-width: calc(var(--agent-sidebar-width) - 16px);
  overflow-y: auto;
  max-height: calc(100vh - 60px); /* 减去标题栏的高度 */
  scrollbar-width: thin;

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background-color: var(--main-light-4);
    border-radius: 4px;
  }
}

.agent-name {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-desc {
  font-size: 12px;
  color: #666;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-model {
  width: 100%;
}

.content {
  flex: 1;
  overflow: hidden;
}

// 添加requirements相关样式
.info-section {
  margin-top: 16px;
  border-top: 1px solid var(--main-light-3);
  padding-top: 12px;

  h3 {
    font-size: 14px;
    margin-bottom: 8px;
    font-weight: 500;
  }
}

.requirements-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;

  .ant-tag {
    user-select: all;
  }
}

@media (max-width: 520px) {
  .sidebar {
    position: absolute;
    z-index: 101;
    width: 0;
    height: 100%;
    border-radius: 0 16px 16px 0;
    box-shadow: 0 0 10px 1px rgba(0, 0, 0, 0.05);

    &.is-open {
      width: var(--agent-sidebar-width);
      padding: 16px;
    }
  }

  .config-sidebar {
    position: absolute;
    z-index: 101;
    right: 0;
    width: 0;
    height: 100%;
    border-radius: 16px 0 0 16px;
    box-shadow: 0 0 10px 1px rgba(0, 0, 0, 0.05);

    &.is-open {
      width: 90%;
      max-width: var(--config-sidebar-width);
    }
  }
}

.config-modal-content {
  max-height: 70vh;
  overflow-y: auto;
  user-select: text;

  div[role="alert"] {
    margin-bottom: 10px;
  }

  .description {
    font-size: 12px;
    color: var(--gray-700);
  }

  .form-actions {
    display: flex;
    justify-content: space-between;
    margin-top: 20px;
    gap: 10px;

    .form-actions-left,
    .form-actions-right {
      display: flex;
      gap: 10px;
    }
  }
}

// 添加新按钮的样式
.agent-action-buttons {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.action-button {
  background-color: white;
  border: 1px solid var(--main-light-3);
  text-align: left;
  height: auto;
  padding: 8px 12px;

  &:hover {
    background-color: var(--main-light-4);
  }

  &.primary-action {
    color: var(--main-color);
    border-color: var(--main-color);

    &:disabled {
      color: var(--main-600);
      background-color: var(--main-light-4);
      cursor: not-allowed;
      opacity: 0.7;
    }
  }

  .anticon {
    margin-right: 8px;
  }
}

.agent-option {
  display: flex;
  justify-content: space-between;
  align-items: center;

  .default-icon {
    color: #faad14;
    font-size: 14px;
  }
}
</style>


<style lang="less">
.toggle-sidebar {
  cursor: pointer;

  &.nav-btn {
    height: 2.5rem;
    display: flex;
    justify-content: center;
    align-items: center;
    border-radius: 8px;
    color: var(--gray-900);
    cursor: pointer;
    font-size: 15px;
    width: auto;
    padding: 0.5rem 1rem;
    transition: background-color 0.3s;
    overflow: hidden;

    .text {
      margin-left: 10px;
    }

    &:hover {
      background-color: var(--main-light-3);
    }

    .nav-btn-icon {
      width: 1.5rem;
      height: 1.5rem;
    }
  }
}
</style>