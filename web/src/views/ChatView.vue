<template>
  <div class="chat-container">
    <div v-if="state.isSidebarOpen" class="conversations">
      <div class="actions">
        <div class="action new" @click="addNewConv"><FormOutlined /></div>
        <div class="action close" @click="state.isSidebarOpen = false"><MenuOutlined /></div>
      </div>
      <div class="conversation"
        v-for="(state, index) in convs"
        :key="index"
        :class="{ active: curConvId === index }"
        @click="goToConversation(index)">
        <div class="conversation__title">{{ state.title }}</div>
        <div class="conversation__delete" @click.prevent="delConv(index)"><DeleteOutlined /></div>
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
import { FormOutlined, MenuOutlined, DeleteOutlined } from '@ant-design/icons-vue'
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
  if (index === curConvId.value) {
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

.chat-container .conversations {
  flex: 1 1 auto;
}

.conversations {
  display: flex;
  flex-direction: column;
  width: 100px;
  height: 100%;
  overflow-y: auto;
  border-right: 1px solid #EDF4F5;
  min-width: var(--min-sider-width);
  max-width: 200px;

  & .actions {
    height: var(--header-height);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    margin-bottom: 16px;
    position: sticky;
    top: 0;
    background-color: white;
    z-index: 9;

    .action {
      font-size: 1.2rem;
      width: 2.5rem;
      height: 2.5rem;
      display: flex;
      justify-content: center;
      align-items: center;
      border-radius: 8px;
      color: #6D6D6D;
      cursor: pointer;

      &:hover {
        background-color: #ECECEC;
      }
    }
  }
}

.conversation {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  cursor: pointer;
  width: 100%;

  &__title {
    white-space: nowrap; /* 禁止换行 */
    overflow: hidden;    /* 超出部分隐藏 */
    text-overflow: ellipsis; /* 显示省略号 */
  }

  &__delete {
    display: none;
    color: #7D7D7D;

    &:hover {
      color: #F93A37;
      background-color: #EEE;
    }
  }

  &.active {
    background-color: #EDF4F5;
  }

  &:hover {
    background-color: #EDF4F5;

    & .conversation__delete {
      display: block;
    }
  }
}

</style>
