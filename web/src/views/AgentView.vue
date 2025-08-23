<template>
  <div class="agent-view">
    <div class="agent-view-header">
      <div class="header-left">
        <div class="header-item">
          <a-button class="header-button" @click="openAgentModal">
            <Bot size="18" stroke-width="1.75" />
            选择：{{ selectedAgent.name || '选择智能体' }}
          </a-button>
        </div>
      </div>
      <div class="header-center">
      </div>
      <div class="header-right">
        <div class="header-item">
          <a-button class="header-button" @click="toggleConf" :icon="h(SettingOutlined)"> 配置 </a-button>
        </div>
        <div class="header-item">
          <a-button
            class="header-button"
            @click="goToAgentPage"
            v-if="selectedAgentId"
          >
            <template #icon><LinkOutlined /></template>
            独立页面
          </a-button>
        </div>
      </div>
    </div>
    <div class="agent-view-body">
      <!-- 智能体选择弹窗 -->
      <a-modal
        v-model:open="state.agentModalOpen"
        title="选择智能体"
        :width="800"
        :footer="null"
        :maskClosable="true"
        class="agent-modal"
      >
        <div class="agent-modal-content">
          <div class="agents-grid">
            <div
              v-for="(agent, id) in agents"
              :key="id"
              class="agent-card"
              :class="{ 'selected': id === selectedAgentId }"
              @click="selectAgentFromModal(id)"
            >
              <div class="agent-card-header">
                <div class="agent-card-title">
                  <span class="agent-card-name">{{ agent.name }}</span>
                  <StarFilled v-if="id === defaultAgentId" class="default-icon" />
                  <StarOutlined v-else @click.prevent="setAsDefaultAgent" class="default-icon" />
                </div>
              </div>
              <div class="agent-card-description">{{ agent.description }}</div>
            </div>
          </div>
        </div>
      </a-modal>

      <!-- 中间内容区域 -->
      <div class="content">
        <AgentChatComponent
          :agent-id="selectedAgentId"
          :config="agentConfig"
          :state="state"
          :single-mode="false"
          @open-config="toggleConf"
          @open-agent-modal="openAgentModal"
          @close-config-sidebar="() => state.isConfigSidebarOpen = false"
        >
        </AgentChatComponent>
      </div>

      <!-- 配置侧边栏 -->
      <AgentConfigSidebar
        :isOpen="state.isConfigSidebarOpen"
        :selectedAgent="selectedAgent"
        :selectedAgentId="selectedAgentId"
        :agentConfig="agentConfig"
        @close="() => state.isConfigSidebarOpen = false"
        @update:agentConfig="(config) => agentConfig = config"
        @config-saved="loadAgentConfig"
        @config-reset="loadAgentConfig"
      />
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
  StarFilled,
  CheckCircleOutlined,
  PlusCircleOutlined
} from '@ant-design/icons-vue';
import { message } from 'ant-design-vue';
import { Bot } from 'lucide-vue-next';
import AgentChatComponent from '@/components/AgentChatComponent.vue';
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue';
import AgentConfigSidebar from '@/components/AgentConfigSidebar.vue';
import { useUserStore } from '@/stores/user';
import { chatApi } from '@/apis/auth_api';
import { agentConfigApi } from '@/apis/system_api';

// 路由
const router = useRouter();
const userStore = useUserStore();

// 状态
const agents = ref({});
const selectedAgentId = ref(null);
const defaultAgentId = ref(null); // 存储默认智能体ID
const state = reactive({
  debug_mode: false,
  agentModalOpen: false,
  isConfigSidebarOpen: false,
  isEmptyConfig: computed(() =>
    !selectedAgentId.value ||
    Object.keys(configurableItems.value).length === 0
  )
});



const selectedAgent = computed(() => agents.value[selectedAgentId.value] || {});
const configSchema = computed(() => selectedAgent.value.config_schema || {});
const configurableItems = computed(() => {
  const items = configSchema.value.configurable_items || {};
  // 遍历所有的配置项，将所有的 x_oap_ui_config 的层级提升到上一层
  Object.keys(items).forEach(key => {
    const item = items[key];
    if (item.x_oap_ui_config) {
      items[key] = { ...item, ...item.x_oap_ui_config };
      delete items[key].x_oap_ui_config;
    }
  });
  return items;
});

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
    await agentConfigApi.setDefaultAgent(selectedAgentId.value);
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
    console.debug("Default agent ID:", defaultAgentId.value);
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
      acc[agent.id] = agent;
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
    } else if (item.type === 'list') {
      // 对于 list 类型，确保初始化为数组
      agentConfig.value[key] = Array.isArray(item.default) ? item.default : [];
    } else {
      agentConfig.value[key] = item.default || '';
    }
  });

  try {
    // 从服务器加载配置
    const response = await agentConfigApi.getAgentConfig(selectedAgentId.value);
    if (response.success && response.config) {
      // 合并服务器配置
      Object.keys(response.config).forEach(key => {
        if (key in agentConfig.value) {
          const item = items[key];
          // 对于 list 类型，确保是数组
          if (item && item.type === 'list') {
            agentConfig.value[key] = Array.isArray(response.config[key]) ? response.config[key] : [];
          } else {
            agentConfig.value[key] = response.config[key];
          }
        }
      });
      // console.log(`从服务器加载 ${selectedAgentId.value} 配置成功, ${JSON.stringify(agentConfig.value)}`);
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
    await agentConfigApi.saveAgentConfig(selectedAgentId.value, agentConfig.value);
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
    await agentConfigApi.saveAgentConfig(selectedAgentId.value, {});
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

// 打开智能体选择弹窗
const openAgentModal = () => {
  state.agentModalOpen = true;
};

// 从弹窗中选择智能体
const selectAgentFromModal = (agentId) => {
  selectAgent(agentId);
  state.agentModalOpen = false;
};



// 初始化
onMounted(async () => {
  // 获取默认智能体
  await fetchDefaultAgent();
  // 获取智能体列表
  await fetchAgents();
  // 加载工具列表


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
  if (value.description && value.name !== key) {
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

const toggleConf = () => {
  state.isConfigSidebarOpen = !state.isConfigSidebarOpen
}
</script>

<style lang="less" scoped>
.agent-view {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  --agent-view-header-height: 54px;
}

.agent-view-header {
  height: var(--agent-view-header-height);
  background-color: var(--bg-sider);
  border-bottom: 1px solid var(--gray-200);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 8px;

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

    button.header-button {
      border-radius: 6px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
  }
}

.agent-view-body {
  --gap-radius: 6px;
  display: flex;
  flex-direction: row;
  width: 100%;
  flex: 1;
  min-height: calc(100% - var(--agent-view-header-height));
  overflow: hidden;
  position: relative;
  // padding: var(--gap-radius);
  // gap: var(--gap-radius);

  // .content {
  //   border-radius: var(--gap-radius);
  //   border: 1px solid var(--gray-300);
  // }
}

.content {
  flex: 1;
  overflow: hidden;
}

// 配置弹窗内容样式
.conf-content {
  max-height: 70vh;
  overflow-y: auto;

  .agent-info {
    padding: 0;
    width: 100%;
    overflow-y: visible;
    max-height: none;
  }
}



.agent-model {
  width: 100%;
}

.config-modal-content {
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
  border: 1px solid var(--main-20);
  text-align: left;
  height: auto;
  padding: 8px 12px;

  &:hover {
    background-color: var(--main-20);
  }

  &.primary-action {
    color: var(--main-color);
    border-color: var(--main-color);

    &:disabled {
      color: var(--main-color);
      background-color: var(--main-20);
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
  align-items: flex-start;
  .agent-option-content {
    display: flex;
    flex-direction: column;
    gap: 2px;

    p {
      margin: 0;
    }

    .agent-option-description {
      font-size: 12px;
      color: var(--gray-700);
      word-break: break-word;
      white-space: pre-wrap;
    }
  }

  .default-icon {
    color: #faad14;
    font-size: 14px;
    margin-left: 4px;
  }
}
// 工具选择器样式（与项目风格一致）
.tools-selector {
  .tools-summary {
    display: flex;
    justify-content: space-between;
    align-items: center;
    // margin-bottom: 8px;
    padding: 8px 12px;
    background: var(--gray-50);
    border-radius: 8px;
    border: 1px solid var(--gray-200);
    font-size: 14px;
    color: var(--gray-700);
    transition: border-color 0.2s ease;

    .tools-summary-left {
      display: flex;
      align-items: center;
      gap: 8px;

      .tools-count {
        color: var(--gray-900);
      }
    }

    .select-tools-btn {
      background: var(--main-color);
      border: none;
      color: #fff;
      border-radius: 6px;
      padding: 4px 12px;
      font-size: 13px;
      font-weight: 500;
      height: 28px;
      transition: all 0.2s ease;

      &:hover {
        background: var(--main-color);
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
      }

      &:active {
        transform: translateY(0);
      }
    }
  }

  .selected-tools-preview {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 8px 0;
    background: none;
    border: none;
    min-height: 32px;
    :deep(.ant-tag) {
      margin: 0;
      padding: 4px 10px;
      border-radius: 6px;
      background: var(--gray-100);
      border: 1px solid var(--gray-300);
      color: var(--gray-900);
      font-size: 13px;
      font-weight: 400;
      .anticon-close {
        color: var(--gray-600);
        margin-left: 4px;
        &:hover {
          color: var(--gray-900);
        }
      }
    }
  }
}

// 工具选择弹窗样式（与项目风格一致）
.tools-modal {
  :deep(.ant-modal-content) {
    border-radius: 8px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    overflow: hidden;
  }
  :deep(.ant-modal-header) {
    background: #fff;
    border-bottom: 1px solid var(--gray-200);
    padding: 16px 20px;
    .ant-modal-title {
      font-size: 16px;
      font-weight: 600;
      color: var(--gray-900);
    }
  }
  :deep(.ant-modal-body) {
    padding: 20px;
    background: #fff;
  }
  .tools-modal-content {
    .tools-search {
      margin-bottom: 16px;
      :deep(.ant-input) {
        border-radius: 8px;
        border: 1px solid var(--gray-300);
        padding: 8px 12px;
        font-size: 14px;
        &:focus {
          border-color: var(--main-color);
          box-shadow: none;
        }
      }
    }
    .tools-list {
      max-height: 350px;
      overflow-y: auto;
      border: 1px solid var(--gray-200);
      border-radius: 8px;
      margin-bottom: 16px;
      background: #fff;
      .tool-item {
        padding: 14px 16px;
        border-bottom: 1px solid var(--gray-100);
        cursor: pointer;
        transition: background 0.2s, border 0.2s;
        border-left: 3px solid transparent;
        &:last-child { border-bottom: none; }
        &:hover {
          background: var(--gray-50);
        }
        &.selected {
          background: var(--main-10);
          border-left: 3px solid var(--main-color);
        }
        .tool-content {
          .tool-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
            .tool-name {
              font-weight: 500;
              color: var(--gray-900);
              font-size: 14px;
            }
            .tool-indicator { display: none; }
          }
          .tool-description {
            font-size: 13px;
            color: var(--gray-700);
            margin-bottom: 6px;
            line-height: 1.5;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            text-overflow: ellipsis;
          }

        }
      }
    }
    .tools-modal-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 0 0 0;
      border-top: 1px solid var(--gray-200);
      .selected-count {
        font-size: 13px;
        color: var(--gray-700);
        background: none;
        padding: 0;
        border: none;
      }
      .modal-actions {
        display: flex;
        gap: 10px;
        :deep(.ant-btn) {
          border-radius: 8px;
          font-weight: 500;
          padding: 6px 18px;
          height: 36px;
          font-size: 14px;
          &.ant-btn-default {
            border: 1px solid var(--gray-300);
            color: var(--gray-900);
            background: #fff;
            &:hover {
              border-color: var(--main-color);
              color: var(--main-color);
              background: var(--main-10);
            }
          }
          &.ant-btn-primary {
            background: var(--main-color);
            border: none;
            color: #fff;
            &:hover {
              background: var(--main-color);
            }
          }
        }
      }
    }
  }
}

// 多选卡片样式
.multi-select-cards {
  .multi-select-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    font-size: 12px;
    color: var(--gray-600);
    height: 24px;
  }

  .options-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 8px;
  }

  .option-card {
    border: 1px solid var(--gray-300);
    border-radius: 8px;
    padding: 8px 12px;
    cursor: pointer;
    transition: all 0.2s ease;
    background: white;
    user-select: none;

    &:hover {
      border-color: var(--main-color);
    }

    &.selected {
      border-color: var(--main-color);
      background: var(--main-10);

      .option-indicator {
        color: var(--main-color);
      }

      .option-text {
        color: var(--main-color);
        font-weight: 500;
      }
    }

    &.unselected {
      .option-indicator {
        color: var(--gray-400);
      }

      .option-text {
        color: var(--gray-700);
      }
    }

    .option-content {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }

    .option-text {
      flex: 1;
      font-size: 14px;
      line-height: 1.4;
      word-break: break-word;
    }

    .option-indicator {
      flex-shrink: 0;
      font-size: 16px;
      transition: color 0.2s ease;
    }
  }
}

// 响应式适配
@media (max-width: 768px) {
  .multi-select-cards {
    .options-grid {
      grid-template-columns: 1fr;
    }
  }

  .conf-content {
    max-height: 60vh;
  }
}

// 智能体选择器样式
.agent-selector {
  border: 1px solid var(--gray-300);
  border-radius: 8px;
  padding: 8px 12px;
  background: white;
  transition: border-color 0.2s ease;

  &:hover {
    border-color: var(--main-color);
  }

  .selected-agent-display {
    display: flex;
    justify-content: space-between;
    align-items: center;

    .agent-name {
      font-size: 14px;
      color: var(--gray-900);
      font-weight: 500;
    }

    .default-icon {
      color: #faad14;
      font-size: 14px;
    }
  }
}

// 智能体选择弹窗样式
.agent-modal {
  :deep(.ant-modal-content) {
    border-radius: 8px;
    overflow: hidden;
  }

  :deep(.ant-modal-header) {
    background: #fff;
    border-bottom: 1px solid var(--gray-200);
    padding: 16px 20px;

    .ant-modal-title {
      font-size: 16px;
      font-weight: 600;
      color: var(--gray-900);
    }
  }

  :deep(.ant-modal-body) {
    padding: 20px;
    background: #fff;
  }

  .agent-modal-content {
    .agents-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 12px;
      max-height: 500px;
      overflow-y: auto;
    }

    .agent-card {
      border: 1px solid var(--gray-200);
      border-radius: 8px;
      padding: 16px;
      cursor: pointer;
      transition: border-color 0.2s ease;
      background: white;

      &:hover {
        border-color: var(--main-color);
      }

      .agent-card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 12px;

        .agent-card-title {
          display: flex;
          align-items: center;
          gap: 8px;
          flex: 1;

          .agent-card-name {
            font-size: 16px;
            font-weight: 600;
            color: var(--gray-900);
            line-height: 1.4;
          }

          .default-icon {
            color: #faad14;
            font-size: 16px;
            flex-shrink: 0;
          }
        }
      }

      .agent-card-description {
        font-size: 14px;
        color: var(--gray-700);
        line-height: 1.5;
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
      }


      &.selected {
        border-color: var(--main-color);
        background: var(--main-20);
        // outline: 2px solid var(--main-color);

        .agent-card-header .agent-card-title .agent-card-name {
          color: var(--main-color);
        }

        .agent-card-description {
          color: var(--gray-900);
        }
      }

    }
  }
}

// 响应式适配智能体弹窗
@media (max-width: 768px) {
  .agent-modal {
    .agent-modal-content {
      .agents-grid {
        grid-template-columns: 1fr;
      }
    }
  }
}

</style>


<style lang="less">
.toggle-conf {
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
      background-color: var(--main-20);
    }

    .nav-btn-icon {
      width: 1.5rem;
      height: 1.5rem;
    }
  }
}


// 针对 Ant Design Select 组件的深度样式修复
:deep(.ant-select-item-option-content) {
  .agent-option-name {
    color: var(--main-color);
    font-size: 14px;
    font-weight: 500;
  }
}
</style>