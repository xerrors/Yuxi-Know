<template>
  <div class="agent-view">
    <!-- 左侧智能体列表侧边栏 -->
    <div class="sidebar" :class="{ 'is-open': state.isSidebarOpen }">
      <h2 class="sidebar-title">
        智能体列表
        <div class="toggle-sidebar" @click="toggleSidebar">
          <img src="@/assets/icons/sidebar_left.svg" class="iconfont icon-20" alt="设置" />
        </div>
      </h2>
      <div class="agent-info">
        <a-select
          v-model:value="selectedAgentId"
          class="agent-list"
          style="width: 100%"
          @change="selectAgent"
        >
          <a-select-option
            v-for="(agent, name) in agents"
            :key="name"
            :value="name"
          >
            {{ agent.name }}
          </a-select-option>
        </a-select>
        <p style="padding: 0 4px;">
          {{ agents[selectedAgentId]?.description }}
        </p>

        <!-- 添加配置按钮 -->
        <div class="agent-action-buttons">
          <a-button
            class="action-button"
            @click="openConfigModal"
          >
            <template #icon><SettingOutlined /></template>
            智能体配置
          </a-button>

          <a-button
            class="action-button"
            @click="openTokenModal"
          >
            <template #icon><KeyOutlined /></template>
            访问令牌
          </a-button>

          <a-button
            class="action-button"
            @click="goToAgentPage"
            v-if="selectedAgentId"
          >
            <template #icon><LinkOutlined /></template>
            打开独立页面
          </a-button>
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

        <!-- 添加all_tools显示部分 -->
        <div v-if="agents[selectedAgentId]?.all_tools && agents[selectedAgentId]?.all_tools.length > 0" class="info-section">
          <h3>可用工具:</h3>
          <div class="all-tools-list">
            <a-tag v-for="tool in agents[selectedAgentId].all_tools" :key="tool">
              {{ tool }}
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
        <template #header-left>
          <div class="toggle-sidebar nav-btn" @click="toggleSidebar" v-if="!state.isSidebarOpen">
            <img src="@/assets/icons/sidebar_left.svg" class="iconfont icon-20" alt="设置" />
          </div>
        </template>
        <!-- <template #header-right>
          <div class="toggle-sidebar nav-btn" @click="toggleConfigSidebar()">
            <SettingOutlined class="iconfont icon-20" />
            <span class="text">配置</span>
          </div>
        </template> -->
      </AgentChatComponent>
    </div>

    <!-- 右侧配置侧边栏 -->
    <div class="config-sidebar" :class="{ 'is-open': state.isConfigSidebarOpen }">
      <h2 class="sidebar-title">
        <div class="sidebar-title-text" @click="toggleDebugMode">智能体配置</div>
        <div class="toggle-sidebar" @click="toggleConfigSidebar(false)">
          <CloseOutlined class="iconfont icon-20" />
        </div>
      </h2>
      <div v-if="selectedAgentId" class="config-form">
        <!-- 已将按钮移至左侧边栏 -->
      </div>
      <div v-else class="no-agent-selected">
        请先选择一个智能体
      </div>
      <p>你好，智能体</p>
    </div>


    <!-- 配置弹窗 -->
    <a-modal
      v-model:open="state.configModalVisible"
      title="智能体配置"
      width="650px"
      :footer="null"
      @cancel="closeConfigModal"
    >
      <div v-if="selectedAgentId && configSchema" class="config-modal-content">
        <!-- 配置表单 -->
        <a-form :model="agentConfig" layout="vertical">
          <div class="empty-config" v-if="state.isEmptyConfig">
            <a-alert type="warning" message="该智能体没有配置项" show-icon/>
          </div>
          <!-- 统一显示所有配置项 -->
          <template v-for="(value, key) in configurableItems" :key="key">
            <a-form-item
              :label="getConfigLabel(key, value)"
              :name="key"
              class="config-item"
            >
              <p v-if="value.description" class="description">{{ value.description }}</p>
              <a-switch
                v-if="typeof agentConfig[key] === 'boolean'"
                v-model:checked="agentConfig[key]"
              />
              <a-textarea
                v-else-if="key === 'system_prompt'"
                v-model:value="agentConfig[key]"
                :rows="4"
                :placeholder="getPlaceholder(key, value)"
              />
              <a-select
                v-else-if="value?.options"
                v-model:value="agentConfig[key]"
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

          <!-- 添加工具选择部分 -->
          <a-form-item label="可用工具" name="tools" class="config-item">
            <p class="description">选择要启用的工具（注：retrieve 工具仅展现了与当前向量模型匹配的知识库，详情请查看 docker 日志。）</p>
            <a-form-item-rest>
              <div class="tools-switches">
                <div v-for="tool in availableTools" :key="tool" class="tool-switch-item">
                  <span class="tool-name">{{ tool }}</span>
                  <a-switch
                    size="small"
                    :checked="isToolActive(tool)"
                    @change="(checked) => toggleTool(tool, checked)"
                  />
                </div>
              </div>
            </a-form-item-rest>
          </a-form-item>

          <!-- 弹窗底部按钮 -->
          <div class="form-actions" v-if="!state.isEmptyConfig">
            <a-button type="primary" @click="saveConfig">保存配置</a-button>
            <a-button @click="resetConfig">重置</a-button>
            <a-button @click="closeConfigModal">取消</a-button>
          </div>
        </a-form>
      </div>
    </a-modal>

    <!-- 令牌管理弹窗 -->
    <a-modal
      v-model:open="state.tokenModalVisible"
      title="访问令牌管理"
      width="650px"
      :footer="null"
      @cancel="closeTokenModal"
    >
      <TokenManagerComponent v-if="selectedAgentId" :agent-id="selectedAgentId" />
    </a-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch, computed, h } from 'vue';
import { useRouter } from 'vue-router';
import {
  RobotOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  CloseOutlined,
  SettingOutlined,
  KeyOutlined,
  LinkOutlined
} from '@ant-design/icons-vue';
import { message } from 'ant-design-vue';
import AgentChatComponent from '@/components/AgentChatComponent.vue';
import TokenManagerComponent from '@/components/TokenManagerComponent.vue';

// 路由
const router = useRouter();

// 状态
const agents = ref({});
const selectedAgentId = ref(null);
const availableTools = ref([]); // 存储所有可用的工具列表
const state = reactive({
  debug_mode: false,
  isSidebarOpen: JSON.parse(localStorage.getItem('agent-sidebar-open') || 'true'),
  isConfigSidebarOpen: false,
  configModalVisible: false,
  tokenModalVisible: false,
  isEmptyConfig: computed(() =>
    !selectedAgentId.value ||
    Object.keys(configurableItems.value).length === 0
  )
});
const configSchema = computed(() => agents.value[selectedAgentId.value]?.config_schema || {});
const configurableItems = computed(() => configSchema.value.configurable_items || {});

// 配置状态
const agentConfig = ref({});

// 调试模式
const toggleDebugMode = () => {
  state.debug_mode = !state.debug_mode;
};

// 打开配置弹窗
const openConfigModal = () => {
  state.configModalVisible = true;
};

// 关闭配置弹窗
const closeConfigModal = () => {
  state.configModalVisible = false;
};

// 打开令牌管理弹窗
const openTokenModal = () => {
  state.tokenModalVisible = true;
};

// 关闭令牌管理弹窗
const closeTokenModal = () => {
  state.tokenModalVisible = false;
};

// 获取智能体列表
const fetchAgents = async () => {
  try {
    const response = await fetch('/api/chat/agent');
    if (response.ok) {
      const data = await response.json();
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
    } else {
      console.error('获取智能体失败');
    }
  } catch (error) {
    console.error('获取智能体错误:', error);
  }
};

// 获取所有可用工具
const fetchTools = async () => {
  try {
    const response = await fetch('/api/chat/tools');
    if (response.ok) {
      const data = await response.json();
      availableTools.value = data.tools;
      console.log("Available tools:", availableTools.value);
    } else {
      console.error('获取工具列表失败');
    }
  } catch (error) {
    console.error('获取工具列表错误:', error);
  }
};

// 根据选中的智能体加载配置
const loadAgentConfig = () => {
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

  if (schema.tools) {
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

  // 加载存储的配置
  const savedConfig = JSON.parse(localStorage.getItem(`agent-config-${selectedAgentId.value}`) || '{}');

  // 合并已保存的配置
  if (savedConfig) {
    Object.keys(savedConfig).forEach(key => {
      if (key in agentConfig.value) {
        agentConfig.value[key] = savedConfig[key];
      }
    });
  }
};

// 保存配置
const saveConfig = () => {
  // 保存配置到本地存储
  localStorage.setItem(`agent-config-${selectedAgentId.value}`, JSON.stringify(agentConfig.value));

  // 提示保存成功
  message.success('配置已保存');
  console.log("agentConfig.value", agentConfig.value);
  closeConfigModal();
};

// 重置配置
const resetConfig = () => {
  // 清除本地存储中的配置
  localStorage.removeItem(`agent-config-${selectedAgentId.value}`);
  // 重新加载默认配置
  loadAgentConfig();
  message.info('配置已重置');
};

// 监听侧边栏状态变化并保存到localStorage
watch(
  () => state.isSidebarOpen,
  (newValue) => {
    localStorage.setItem('agent-sidebar-open', JSON.stringify(newValue));
  }
);

// 监听智能体选择变化
watch(
  () => selectedAgentId.value,
  () => {
    loadAgentConfig();
  }
);

// 切换左侧侧边栏
const toggleSidebar = () => {
  state.isSidebarOpen = !state.isSidebarOpen;
};

// 切换配置侧边栏
const toggleConfigSidebar = (forceOpen) => {
  if (forceOpen !== undefined) {
    state.isConfigSidebarOpen = forceOpen;
  } else {
    state.isConfigSidebarOpen = !state.isConfigSidebarOpen;
  }
};

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
  // 获取智能体列表
  await fetchAgents();
  // 获取工具列表
  await fetchTools();

  // 恢复上次选择的智能体
  const lastSelectedAgent = localStorage.getItem('last-selected-agent');
  if (lastSelectedAgent && agents.value[lastSelectedAgent]) {
    selectedAgentId.value = lastSelectedAgent;
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

// 检查工具是否激活
const isToolActive = (tool) => {
  if (!agentConfig.value.tools) {
    agentConfig.value.tools = [];
  }
  return agentConfig.value.tools.includes(tool);
};

// 切换工具状态
const toggleTool = (tool, checked) => {
  if (!agentConfig.value.tools) {
    agentConfig.value.tools = [];
  }

  if (checked) {
    // 添加工具到列表
    if (!agentConfig.value.tools.includes(tool)) {
      agentConfig.value.tools.push(tool);
    }
  } else {
    // 从列表中移除工具
    agentConfig.value.tools = agentConfig.value.tools.filter(item => item !== tool);
  }
};
</script>

<style lang="less" scoped>
.agent-view {
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  --agent-sidebar-width: 300px;
  --config-sidebar-width: 350px;
}

.sidebar {
  width: 0;
  max-width: var(--agent-sidebar-width);
  border-right: 1px solid var(--main-light-3);
  background-color: var(--bg-sider);
  box-sizing: content-box;
  overflow-y: auto;
  transition: width 0.3s ease;
  overflow: hidden;

  &.is-open {
    width: var(--agent-sidebar-width);
  }
}

// 配置侧边栏样式
.config-sidebar {
  width: 0;
  max-width: var(--config-sidebar-width);
  border-left: 1px solid var(--main-light-3);
  background-color: var(--bg-sider);
  box-sizing: content-box;
  overflow-y: auto;
  transition: width 0.3s ease;
  overflow: hidden;
  position: relative;
  z-index: 100;

  &.is-open {
    width: var(--config-sidebar-width);
  }

  .config-form {
    padding: 16px;
    min-width: calc(var(--config-sidebar-width) - 16px);
    overflow-y: auto;
    max-height: calc(100vh - 100px);

    .token-section {
      margin-top: 1.5rem;
      border-top: 1px solid var(--main-light-3);
      padding-top: 1rem;
    }
  }

  .no-agent-selected {
    padding: 16px;
    color: var(--gray-500);
    text-align: center;
    margin-top: 20px;
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

.agent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 1rem;
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

  .description {
    font-size: 12px;
    color: var(--gray-700);
  }

  .form-actions {
    display: flex;
    justify-content: space-between;
    margin-top: 20px;
    gap: 10px;
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

  .anticon {
    margin-right: 8px;
  }
}

.tools-switches {
  display: flex;
  flex-direction: column;
  gap: 12px;

  .tool-switch-item {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .tool-name {
      margin-left: 10px;
    }
  }
}
</style>


