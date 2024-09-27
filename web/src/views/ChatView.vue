<template>
  <div class="chat-container">
    <div class="conversations" :class="['conversations', { 'is-open': state.isSidebarOpen }]">
      <div class="actions">
        <!-- <div class="action new" @click="addNewConv"><FormOutlined /></div> -->
         <span style="font-weight: bold; user-select: none;">对话历史</span>
        <div class="action close" @click="state.isSidebarOpen = false"><MenuOutlined /></div>
      </div>
      <div class="conversation-list">
        <div class="conversation"
          v-for="(state, index) in convs"
          :key="index"
          :class="{ active: curConvId === index }"
          @click="goToConversation(index)">
          <div class="conversation__title"><CommentOutlined /> &nbsp;{{ state.title }}</div>
          <div class="conversation__delete" @click.stop="delConv(index)"><DeleteOutlined /></div>
        </div>
      </div>
    </div>
    <ChatComponent
      :conv="convs[curConvId]"
      :state="state"
      @rename-title="renameTitle"
      @newconv="addNewConv"/>
  </div>
</template>

<script setup>
import { reactive, ref, watch, onMounted } from 'vue'
import { FormOutlined, MenuOutlined, DeleteOutlined, CommentOutlined } from '@ant-design/icons-vue'
import ChatComponent from '@/components/ChatComponent.vue'

const convs = reactive(JSON.parse(localStorage.getItem('chat-convs')) || [
  {
    id: 0,
    title: '新对话',
    history: [],
    messages: [],
    inputText: ''
  },
])

const state = reactive({
  isSidebarOpen: true,
})

const curConvId = ref(0)

const generateRandomHash = (length) => {
    let chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let hash = '';
    for (let i = 0; i < length; i++) {
        hash += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return hash;
}

const renameTitle = (newTitle) => {
  convs[curConvId.value].title = newTitle
}

const goToConversation = (index) => {
  curConvId.value = index
  console.log(convs[curConvId.value])
}

const addNewConv = () => {
  curConvId.value = 0
  if (convs.length > 0 && convs[0].messages.length === 0) {
    return
  }
  convs.unshift({
    id: generateRandomHash(8),
    title: `新对话`,
    history: [],
    messages: [],
    inputText: ''
  })
}

const delConv = (index) => {
  convs.splice(index, 1)

  if (index < curConvId.value) {
    curConvId.value -= 1
  } else if (index === curConvId.value) {
    curConvId.value = 0
  }

  if (convs.length === 0) {
    addNewConv()
  }
}

// Watch convs and save to localStorage
watch(
  () => convs,
  (newStates) => {
    localStorage.setItem('chat-convs', JSON.stringify(newStates))
  },
  { deep: true }
)

// Load convs from localStorage on mount
onMounted(() => {
  const savedSonvs = JSON.parse(localStorage.getItem('chat-convs'))
  if (savedSonvs) {
    for (let i = 0; i < savedSonvs.length; i++) {
      convs[i] = savedSonvs[i]
    }
  }
})
</script>

<style lang="less" scoped>
@import '@/assets/main.css';

.chat-container {
  display: flex;
  width: 100%;
  height: 100%;
  position: relative;
}

.chat-container .conversations:not(.is-open) {
  width: 0;
  opacity: 0;
  flex: 0 0 0;
}

.chat-container .conversations.is-open {
  overflow: hidden; /* 确保内容不溢出 */
  white-space: nowrap; /* 防止文本换行 */
  flex: 1 1 auto; /* 当侧边栏打开时，占据可用空间 */
}
.conversations {
  width: 230px; /* 初始宽度 */
  max-width: 230px;
  border-right: 1px solid var(--main-light-3);
  overflow: hidden; /* 确保内容不溢出 */
  max-height: 100%;
  background-color: var(--bg-sider);

  & .actions {
    height: var(--header-height);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    z-index: 9;
    border-bottom: 1px solid var(--main-light-3);

    .action {
      font-size: 1.2rem;
      width: 2.5rem;
      height: 2.5rem;
      display: flex;
      justify-content: center;
      align-items: center;
      border-radius: 8px;
      color: var(--gray-800);
      cursor: pointer;

      &:hover {
        background-color: var(--main-light-3);
      }
    }
  }

  .conversation-list {
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    max-height: 100%;
  }

  .conversation-list .conversation {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    cursor: pointer;
    width: 100%;
    user-select: none;
    transition: background-color 0.2s ease-in-out;

    &__title {
      color: var(--gray-700);
      white-space: nowrap; /* 禁止换行 */
      overflow: hidden;    /* 超出部分隐藏 */
      text-overflow: ellipsis; /* 显示省略号 */
    }

    &__delete {
      display: none;
      color: var(--gray-500);
      transition: all 0.2s ease-in-out;

      &:hover {
        color: #F93A37;
        background-color: #EEE;
      }
    }

    &.active {
      border-right: 3px solid var(--main-500);
      padding-right: 13px;
      background-color: var(--gray-200);

      & .conversation__title {
        color: var(--gray-1000);
      }
    }

    &:not(.active):hover {
      background-color: var(--main-light-3);

      & .conversation__delete {
        display: block;
      }
    }

  }
}

.conversation-list::-webkit-scrollbar {
  position: absolute;
  width: 4px;
}

.conversation-list::-webkit-scrollbar-track {
  background: transparent;
  border-radius: 4px;
}

.conversation-list::-webkit-scrollbar-thumb {
  background: var(--gray-400);
  border-radius: 4px;
}

.conversation-list::-webkit-scrollbar-thumb:hover {
  background: rgb(100, 100, 100);
  border-radius: 4px;
}

.conversation-list::-webkit-scrollbar-thumb:active {
  background: rgb(68, 68, 68);
  border-radius: 4px;
}

@media (max-width: 520px) {
  .conversation {
    position: absolute;
    z-index: 101;
    width: 300px;
    border-radius: 0 16px 16px 0;
    box-shadow: 0 0 10px 1px rgba(0, 0, 0, 0.05);
  }
}
</style>
