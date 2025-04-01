<template>
  <div class="agent-view">
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
    <div class="content">
      <AgentChatComponent :agent-id="selectedAgentId">
        <template #header-left>
          <div class="toggle-sidebar nav-btn" @click="toggleSidebar" v-if="!state.isSidebarOpen">
            <img src="@/assets/icons/sidebar_left.svg" class="iconfont icon-20" alt="设置" />
          </div>
        </template>
      </AgentChatComponent>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch } from 'vue';
import { RobotOutlined, MenuFoldOutlined, MenuUnfoldOutlined, CloseOutlined } from '@ant-design/icons-vue';
import AgentChatComponent from '@/components/AgentChatComponent.vue';

// 状态
const agents = ref({});
const selectedAgentId = ref(null);
const state = reactive({
  isSidebarOpen: JSON.parse(localStorage.getItem('agent-sidebar-open') || 'true'),
});

// 监听侧边栏状态变化并保存到localStorage
watch(
  () => state.isSidebarOpen,
  (newValue) => {
    localStorage.setItem('agent-sidebar-open', JSON.stringify(newValue));
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
    } else {
      console.error('获取智能体失败');
    }
  } catch (error) {
    console.error('获取智能体错误:', error);
  }
};

// 切换侧边栏
const toggleSidebar = () => {
  state.isSidebarOpen = !state.isSidebarOpen;
};

// 选择智能体
const selectAgent = (agentId) => {
  selectedAgentId.value = agentId;
  // 保存选择到本地存储
  localStorage.setItem('last-selected-agent', agentId);
};

// 生成智能体头像颜色
const getAgentColor = (name) => {
  // 简单的哈希函数生成颜色
  const hash = name.split('').reduce((acc, char) => {
    return char.charCodeAt(0) + ((acc << 5) - acc);
  }, 0);
  return `hsl(${Math.abs(hash) % 360}, 70%, 60%)`;
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
});
</script>

<style lang="less" scoped>
.agent-view {
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  --agent-sidebar-width: 230px;
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
}
</style>


