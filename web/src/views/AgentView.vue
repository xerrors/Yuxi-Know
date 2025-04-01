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

        <!-- 添加requirements显示部分 -->
        <div v-if="agents[selectedAgentId]?.requirements && agents[selectedAgentId]?.requirements.length > 0" class="requirements-section">
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
        @open-config="toggleConfigSidebar(true)"
      >
        <template #header-left>
          <div class="toggle-sidebar nav-btn" @click="toggleSidebar" v-if="!state.isSidebarOpen">
            <img src="@/assets/icons/sidebar_left.svg" class="iconfont icon-20" alt="设置" />
          </div>
        </template>
        <template #header-right>
          <div class="toggle-sidebar nav-btn" @click="toggleConfigSidebar()">
            <SettingOutlined class="iconfont icon-20" />
            <span class="text">配置</span>
          </div>
        </template>
      </AgentChatComponent>
    </div>

    <!-- 右侧配置侧边栏 -->
    <div class="config-sidebar" :class="{ 'is-open': state.isConfigSidebarOpen }">
      <h2 class="sidebar-title">
        智能体配置
        <div class="toggle-sidebar" @click="toggleConfigSidebar(false)">
          <CloseOutlined class="iconfont icon-20" />
        </div>
      </h2>
      <div v-if="selectedAgentId && configSchema" class="config-form">
        <!-- 配置表单 -->
        <a-form :model="agentConfig" layout="vertical">
          <!-- 系统提示词 -->

          <div class="empty-config" v-if="state.isEmptyConfig">
            <a-alert type="warning" message="该智能体没有配置项" show-icon/>
          </div>
          <a-form-item v-if="configSchema.system_prompt" label="系统提示词" name="system_prompt">
            <a-textarea
              v-model:value="agentConfig.system_prompt"
              :rows="4"
              placeholder="设置智能体的系统提示词"
            />
          </a-form-item>

          <!-- 模型选择 -->
          <a-form-item v-if="configSchema.model" :label="`模型 (默认: ${configSchema.model})`" name="model">
            <a-input
              v-model:value="agentConfig.model"
              placeholder="provider/model-name"
            />
          </a-form-item>

          <!-- 工具选择: 多选，默认全选 -->
          <a-form-item v-if="configSchema.tools" :label="`工具`" name="tools">
            <a-select
              v-model:value="agentConfig.tools"
              placeholder="选择工具"
              mode="multiple"
            >
              <a-select-option v-for="tool in configSchema.tools" :key="tool">
                {{ tool }}
              </a-select-option>
            </a-select>
          </a-form-item>

          <!-- 其他配置项，可按需扩展 -->
          <div v-if="Object.keys(additionalConfig).length > 0">
            <a-divider>其他配置</a-divider>
            <a-form-item
              v-for="(value, key) in additionalConfig"
              :key="key"
              :label="key"
              :name="key"
            >
              <a-input
                v-model:value="additionalConfig[key]"
                :placeholder="`设置${key}`"
              />
            </a-form-item>
          </div>

          <!-- 保存和重置按钮 -->
          <div class="form-actions" v-if="!state.isEmptyConfig">
            <a-button type="primary" @click="saveConfig">保存配置</a-button>
            <a-button @click="resetConfig">重置</a-button>
          </div>
        </a-form>
      </div>
      <div v-else class="no-agent-selected">
        请先选择一个智能体
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch, computed, h } from 'vue';
import {
  RobotOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  CloseOutlined,
  SettingOutlined
} from '@ant-design/icons-vue';
import { message } from 'ant-design-vue';
import AgentChatComponent from '@/components/AgentChatComponent.vue';

// 状态
const agents = ref({});
const selectedAgentId = ref(null);
const state = reactive({
  isSidebarOpen: JSON.parse(localStorage.getItem('agent-sidebar-open') || 'true'),
  isConfigSidebarOpen: false,
  isEmptyConfig: computed(() => Object.keys(agents.value[selectedAgentId.value]?.config_schema || {}).length === 0),
});
const configSchema = computed(() => agents.value[selectedAgentId.value]?.config_schema || {});

// 配置状态
const agentConfig = ref({
  system_prompt: '',
  model: '',
  debug_mode: false,
});

// 存储额外配置项
const additionalConfig = ref({});

// 根据选中的智能体加载配置
const loadAgentConfig = () => {
  if (!selectedAgentId.value || !agents.value[selectedAgentId.value]) return;

  const agent = agents.value[selectedAgentId.value];
  const configSchema = agent.config_schema || {};

  // 重置配置
  agentConfig.value = {
    system_prompt: configSchema.system_prompt || '',
    model: configSchema.model || '',
    // 默认全选所有工具
    tools: configSchema.tools || [],
  };

  // 清空额外配置
  additionalConfig.value = {};

  // 加载存储的配置
  const savedConfig = JSON.parse(localStorage.getItem(`agent-config-${selectedAgentId.value}`) || '{}');

  // 合并已保存的配置
  if (savedConfig) {
    Object.assign(agentConfig.value, savedConfig);
  }

  // 如果没有保存过tools配置，则默认全选
  if (!savedConfig.tools && configSchema.tools) {
    agentConfig.value.tools = [...configSchema.tools];
  }

  // 加载额外配置项
  Object.keys(configSchema).forEach(key => {
    if (!['system_prompt', 'model', 'tools'].includes(key)) {
      additionalConfig.value[key] = savedConfig[key] || configSchema[key] || '';
    }
  });
};

// 保存配置
const saveConfig = () => {
  // 合并所有配置
  const fullConfig = {
    ...agentConfig.value,
    ...additionalConfig.value
  };

  // 保存配置到本地存储
  localStorage.setItem(`agent-config-${selectedAgentId.value}`, JSON.stringify(fullConfig));

  // 提示保存成功
  message.success('配置已保存');
};

// 重置配置
const resetConfig = () => {
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
      console.log("agents", agents.value);

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
</script>

<style lang="less" scoped>
.agent-view {
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  --agent-sidebar-width: 230px;
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
  }

  .form-actions {
    display: flex;
    justify-content: space-between;
    margin-top: 20px;
  }

  .no-agent-selected {
    padding: 16px;
    color: var(--gray-500);
    text-align: center;
    margin-top: 20px;
  }
}

.sidebar-title {
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
.requirements-section {
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
</style>


