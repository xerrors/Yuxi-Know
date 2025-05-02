<template>
  <div class="agent-single-view">
    <!-- 侧边栏 -->
    <div class="sidebar" :class="{ 'collapsed': isSidebarCollapsed }">
      <div class="sidebar-content">
        <div class="user-icon">
          <img :src="sidebarLeftIcon" alt="用户信息" @click="toggleUserInfo" />
        </div>
        <!-- 这里可以添加更多侧边栏内容 -->
         <UserInfoComponent />
      </div>
      <div class="toggle-button" @click="toggleSidebar">
        <img :src="isSidebarCollapsed ? sidebarRightIcon : sidebarLeftIcon" alt="折叠/展开" />
      </div>
    </div>

    <!-- 用户信息组件 -->
    <div class="user-info-wrapper">
      <UserInfoComponent />
    </div>

    <!-- 智能体聊天界面 -->
    <AgentChatComponent :agent-id="agentId" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import AgentChatComponent from '@/components/AgentChatComponent.vue';
import UserInfoComponent from '@/components/UserInfoComponent.vue';
import sidebarLeftIcon from '@/assets/icons/sidebar_left.svg';
import sidebarRightIcon from '@/assets/icons/sidebar_right.svg';

const route = useRoute();
const agentId = computed(() => route.params.agent_id);

// 侧边栏状态
const isSidebarCollapsed = ref(false);

// 切换侧边栏展开/折叠状态
const toggleSidebar = () => {
  isSidebarCollapsed.value = !isSidebarCollapsed.value;
};

// 用户信息点击事件
const toggleUserInfo = () => {
  // 此处可以添加用户信息相关的逻辑
  console.log('用户信息图标被点击');
};
</script>

<style lang="less" scoped>
.agent-single-view {
  width: 100%;
  height: 100vh;
  overflow: hidden;
  position: relative;
}

.user-info-wrapper {
  position: absolute;
  top: 10px;
  right: 20px;
  z-index: 10;
}

// 侧边栏样式
.sidebar {
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  width: 240px;
  background-color: #f5f5f5;
  transition: all 0.3s ease;
  z-index: 20;
  display: flex;

  &.collapsed {
    width: 60px;
  }

  .sidebar-content {
    flex: 1;
    padding: 20px 10px;
    overflow-y: auto;
  }

  .user-icon {
    cursor: pointer;
    margin-bottom: 20px;

    img {
      width: 32px;
      height: 32px;
    }
  }

  .toggle-button {
    position: absolute;
    right: -15px;
    top: 50%;
    transform: translateY(-50%);
    width: 30px;
    height: 30px;
    background-color: #fff;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

    img {
      width: 16px;
      height: 16px;
    }
  }
}
</style>


