<template>
  <div class="agent-single-view">
    <!-- 智能体聊天界面 -->
    <AgentChatComponent ref="chatComponentRef" :agent-id="agentId" :single-mode="true">
      <template #header-right>
        <div type="button" class="agent-nav-btn" @click="handleShareChat">
          <Share2 size="18" class="nav-btn-icon" />
          <span class="text">分享</span>
        </div>
        <UserInfoComponent />
      </template>
    </AgentChatComponent>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { message } from 'ant-design-vue';
import { useRoute } from 'vue-router';
import { Share2 } from 'lucide-vue-next';
import AgentChatComponent from '@/components/AgentChatComponent.vue';
import UserInfoComponent from '@/components/UserInfoComponent.vue';
import { ChatExporter } from '@/utils/chatExporter';
import { handleChatError } from '@/utils/errorHandler';

const route = useRoute();
const agentId = computed(() => route.params.agent_id);
const chatComponentRef = ref(null);

const handleShareChat = async () => {
  try {
    const exportData = chatComponentRef.value?.getExportPayload?.();

    if (!exportData) {
      message.warning('当前没有可导出的对话内容');
      return;
    }

    const hasMessages = Boolean(exportData.messages?.length);
    const hasOngoingMessages = Boolean(exportData.onGoingMessages?.length);

    if (!hasMessages && !hasOngoingMessages) {
      message.warning('当前对话暂无内容可导出，请先进行对话');
      return;
    }

    const result = await ChatExporter.exportToHTML(exportData);
    message.success(`对话已导出为HTML文件: ${result.filename}`);
  } catch (error) {
    if (error?.message?.includes('没有可导出的对话内容')) {
      message.warning('当前对话暂无内容可导出，请先进行对话');
      return;
    }
    handleChatError(error, 'export');
  }
};
</script>

<style lang="less" scoped>
.agent-single-view {
  width: 100%;
  height: 100vh;
  overflow: hidden;
  position: relative;
  display: flex;
  flex-direction: row;
}

.user-info-wrapper {
  position: absolute;
  top: 10px;
  right: 20px;
  z-index: 10;
}

// 侧边栏样式
.sidebar {
  // position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  width: 240px;
  background-color: var(--gray-50);
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
    padding-left: 4px 8px;

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
    background-color: var(--gray-0);
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

