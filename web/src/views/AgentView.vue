<template>
  <div class="agent-view">
    <div class="sidebar">
      <h2 class="sidebar-title">智能体列表</h2>
      <div class="agent-list">
        <div v-for="(agent, name) in agents"
             :key="name"
             class="agent-item"
             :class="{ active: selectedAgentId === name }"
             @click="selectAgent(name)">
          <a-avatar :style="{ backgroundColor: getAgentColor(name) }">
            <template #icon><RobotOutlined /></template>
          </a-avatar>
          <div class="agent-info">
            <div class="agent-name">{{ agent.name }}</div>
            <div class="agent-desc">{{ agent.short_description || '智能助手' }}</div>
          </div>
        </div>
      </div>
    </div>
    <div class="content">
      <AgentChatComponent :agent-id="selectedAgentId" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { RobotOutlined } from '@ant-design/icons-vue';
import AgentChatComponent from '@/components/AgentChatComponent.vue';

// 状态
const agents = ref({});
const selectedAgentId = ref(null);

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
}

.sidebar {
  width: 230px;
  max-width: 230px;
  border-right: 1px solid var(--main-light-3);
  background-color: var(--bg-sider);
  padding: 16px;
  overflow-y: auto;
}

.sidebar-title {
  font-weight: bold;
  user-select: none;
  white-space: nowrap;
  overflow: hidden;
  padding-bottom: 1rem;
  font-size: 1rem;
  border-bottom: 1px solid var(--main-light-3);
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
  margin-left: 12px;
  overflow: hidden;
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
</style>


