<template>
  <div class="chat-sidebar" :class="{'sidebar-open': isSidebarOpen, 'no-transition': isInitialRender}">
    <div class="sidebar-header">
      <div class="header-title" v-if="singleMode">{{ selectedAgentName }}</div>
      <div
        v-else
        class="agent-selector"
        @click="openAgentModal"
      > {{ selectedAgentName || '选择智能体' }}</div>
      <div class="header-actions">
        <div class="toggle-sidebar nav-btn" v-if="isSidebarOpen" @click="toggleCollapse">
          <PanelLeftClose size="20" color="var(--gray-800)"/>
        </div>
      </div>
    </div>
    <div class="conversation-list-top">
      <button type="text" @click="createNewChat" class="new-chat-btn">
       <MessageSquarePlus size="20" /> 创建新对话
      </button>
    </div>
    <div class="conversation-list">
      <a-spin v-if="loading" />
      <template v-else-if="Object.keys(groupedChats).length > 0">
        <div v-for="(group, groupName) in groupedChats" :key="groupName" class="chat-group">
          <div class="chat-group-title">{{ groupName }}</div>
          <div
            v-for="chat in group"
            :key="chat.id"
            class="conversation-item"
            :class="{ 'active': currentChatId === chat.id }"
            @click="selectChat(chat)"
          >
            <div class="conversation-title">{{ chat.title || '新的对话' }}</div>
            <div class="actions-mask"></div>
            <div class="conversation-actions">
              <a-dropdown :trigger="['click']" @click.stop>
                <template #overlay>
                  <a-menu>
                    <a-menu-item key="rename" @click.stop="renameChat(chat.id)">
                      <EditOutlined /> 重命名
                    </a-menu-item>
                    <a-menu-item key="delete" @click.stop="deleteChat(chat.id)" v-if="chat.id !== currentChatId">
                      <DeleteOutlined /> 删除
                    </a-menu-item>
                  </a-menu>
                </template>
                <a-button type="text" class="more-btn" @click.stop>
                  <MoreOutlined />
                </a-button>
              </a-dropdown>
            </div>
          </div>
        </div>
      </template>
      <div v-else class="empty-list">
        暂无对话历史
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, h } from 'vue';
import {
  DeleteOutlined,
  EditOutlined,
  MoreOutlined
} from '@ant-design/icons-vue';
import { message, Modal } from 'ant-design-vue';
import { PanelLeftClose, MessageSquarePlus } from 'lucide-vue-next';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

const props = defineProps({
  currentAgentId: {
    type: String,
    default: null
  },
  currentChatId: {
    type: String,
    default: null
  },
  chatsList: {
    type: Array,
    default: () => []
  },
  isSidebarOpen: {
    type: Boolean,
    default: false
  },
  isInitialRender: {
    type: Boolean,
    default: false
  },
  singleMode: {
    type: Boolean,
    default: true
  },
  agents: {
    type: Object,
    default: () => ({})
  },
  selectedAgentId: {
    type: String,
    default: null
  }
});

const emit = defineEmits(['create-chat', 'select-chat', 'delete-chat', 'rename-chat', 'toggle-sidebar', 'open-agent-modal']);

const loading = ref(false);

const selectedAgentName = computed(() => {
  if (props.selectedAgentId && props.agents && props.agents[props.selectedAgentId]) {
    return props.agents[props.selectedAgentId].name;
  }
  return '';
});

const groupedChats = computed(() => {
  const groups = {
    '今天': [],
    '七天内': [],
    '三十天内': [],
  };

  const now = dayjs();
  const today = now.startOf('day');
  const sevenDaysAgo = now.subtract(7, 'day').startOf('day');
  const thirtyDaysAgo = now.subtract(30, 'day').startOf('day');

  // Sort chats by creation date, newest first
  const sortedChats = [...props.chatsList].sort((a, b) => dayjs(b.create_at).diff(dayjs(a.create_at)));

  sortedChats.forEach(chat => {
    const chatDate = dayjs(chat.create_at);
    if (chatDate.isAfter(today)) {
      groups['今天'].push(chat);
    } else if (chatDate.isAfter(sevenDaysAgo)) {
      groups['七天内'].push(chat);
    } else if (chatDate.isAfter(thirtyDaysAgo)) {
      groups['三十天内'].push(chat);
    } else {
      const monthKey = chatDate.format('YYYY-MM');
      if (!groups[monthKey]) {
        groups[monthKey] = [];
      }
      groups[monthKey].push(chat);
    }
  });

  // Remove empty groups
  for (const key in groups) {
    if (groups[key].length === 0) {
      delete groups[key];
    }
  }

  return groups;
});


const createNewChat = () => {
  emit('create-chat');
};

const selectChat = (chat) => {
  console.log(chat);
  emit('select-chat', chat.id);
};

const deleteChat = (chatId) => {
  emit('delete-chat', chatId);
};

const renameChat = async (chatId) => {
  try {
    const chat = props.chatsList.find(c => c.id === chatId);
    if (!chat) return;

    let newTitle = chat.title;
    Modal.confirm({
      title: '重命名对话',
      content: h('div', { style: { marginTop: '12px' } }, [
        h('input', {
          value: newTitle,
          style: { width: '100%', padding: '4px 8px', border: '1px solid #d9d9d9', borderRadius: '4px' },
          onInput: (e) => { newTitle = e.target.value; }
        })
      ]),
      okText: '确认',
      cancelText: '取消',
      onOk: () => {
        if (!newTitle.trim()) {
          message.warning('标题不能为空');
          return Promise.reject();
        }
        emit('rename-chat', { chatId, title: newTitle });
      },
      onCancel: () => {}
    });
  } catch (error) {
    console.error('重命名对话失败:', error);
  }
};

const toggleCollapse = () => {
  emit('toggle-sidebar');
};

const openAgentModal = () => {
  emit('open-agent-modal');
};
</script>

<style lang="less" scoped>
.chat-sidebar {
  width: 0;
  height: 100%;
  background-color: var(--bg-sider);
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  border: none;
  overflow: hidden;

  &.no-transition {
    transition: none !important;
  }

  &.sidebar-open {
    width: 280px;
    max-width: 300px;
    border-right: 1px solid var(--gray-200);
  }

  .sidebar-header {
    height: var(--header-height);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
    border-bottom: 1px solid var(--gray-200);
    flex-shrink: 0;

    .header-title {
      font-weight: 500;
      font-size: 16px;
      color: var(--gray-900);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      flex: 1;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
  }

  .conversation-list-top {
    padding: 8px 12px;
    // border-bottom: 1px solid var(--gray-200);

    .new-chat-btn {
      width: 100%;
      padding: 8px 12px;
      border-radius: 6px;
      background-color: var(--gray-50);
      color: var(--main-color);
      border: none;
      transition: all 0.2s ease;
      font-weight: 500;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;

      &:hover {
        background-color: var(--gray-100);
      }
    }
  }

  .conversation-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;

    .chat-group {
      margin-bottom: 16px;
    }

    .chat-group-title {
      padding: 4px 8px;
      font-size: 12px;
      color: var(--gray-500);
      font-weight: 500;
      text-transform: uppercase;
    }

    .conversation-item {
      display: flex;
      align-items: center;
      padding: 8px 12px;
      border-radius: 6px;
      margin: 4px 0;
      cursor: pointer;
      transition: background-color 0.2s ease;
      position: relative;
      overflow: hidden;

      .conversation-title {
        flex: 1;
        font-size: 14px;
        color: var(--gray-800);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        transition: color 0.2s ease;
      }

      .actions-mask {
        position: absolute;
        right: 0;
        top: 0;
        bottom: 0;
        width: 60px;
        background: linear-gradient(to right, transparent, var(--bg-sider) 20px);
        opacity: 0;
        transition: opacity 0.3s ease;
        pointer-events: none;
      }

      .conversation-actions {
        display: flex;
        align-items: center;
        position: absolute;
        right: 8px;
        top: 50%;
        transform: translateY(-50%);
        opacity: 0;
        transition: opacity 0.3s ease;

        .more-btn {
          color: var(--gray-600);
          background-color: transparent !important;
          &:hover {
            color: var(--main-500);
            background-color: transparent !important;
          }
        }
      }

      &:hover {
        background-color: var(--gray-50);

        .actions-mask {
            background: linear-gradient(to right, transparent, var(--gray-100) 20px);
        }

        .actions-mask, .conversation-actions {
          opacity: 1;
        }
      }

      &.active {
        background-color: var(--gray-100);

        .conversation-title {
          color: var(--main-600);
          font-weight: 500;
        }
        .actions-mask {
          background: linear-gradient(to right, transparent, var(--gray-100) 20px);
        }
      }
    }

    .empty-list {
      text-align: center;
      margin-top: 20px;
      color: var(--gray-500);
      font-size: 14px;
    }
  }
}

// Scrollbar styling
.conversation-list::-webkit-scrollbar {
  width: 5px;
}
.conversation-list::-webkit-scrollbar-track {
  background: transparent;
}
.conversation-list::-webkit-scrollbar-thumb {
  background: var(--gray-300);
  border-radius: 5px;
}
.conversation-list::-webkit-scrollbar-thumb:hover {
  background: var(--gray-400);
}

.toggle-sidebar.nav-btn {
  cursor: pointer;
  height: 2.5rem;
  display: flex;
  justify-content: center;
  align-items: center;
  border-radius: 8px;
  color: var(--gray-500);
  // padding: 0.5rem;
  transition: background-color 0.3s;
  &:hover {
    color: var(--main-color);
  }
}

// 智能体选择器样式
.agent-selector {
  cursor: pointer;
  font-size: 14px;
  color: var(--gray-900);
  transition: color 0.2s ease;

  &:hover {
    color: var(--main-500);
  }
}
</style>
