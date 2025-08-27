<template>
  <div class="chat-container" ref="chatContainerRef">
    <ChatSidebarComponent
      :current-chat-id="currentChatId"
      :chats-list="chatsList"
      :is-sidebar-open="state.isSidebarOpen"
      :is-initial-render="state.isInitialRender"
      :single-mode="props.singleMode"
      :agents="agents"
      :selected-agent-id="agentStore.selectedAgentId"
      @create-chat="createNewChat"
      @select-chat="selectChat"
      @delete-chat="deleteChat"
      @rename-chat="renameChat"
      @toggle-sidebar="toggleSidebar"
      @open-agent-modal="openAgentModal"
      :class="{
        'floating-sidebar': isSmallContainer,
        'sidebar-open': state.isSidebarOpen,
        'no-transition': state.isInitialRender,
        'collapsed': isSmallContainer && !state.isSidebarOpen
      }"
    />
    <div class="sidebar-backdrop" v-if="state.isSidebarOpen && isSmallContainer" @click="toggleSidebar"></div>
    <div class="chat">
      <div class="chat-header">
        <div class="header__left">
          <slot name="header-left" class="nav-btn"></slot>
          <div class="toggle-sidebar nav-btn" v-if="!state.isSidebarOpen" @click="toggleSidebar">
            <PanelLeftOpen size="20" color="var(--gray-800)"/>
          </div>
          <div class="newchat nav-btn" v-if="!state.isSidebarOpen" @click="createNewChat" :disabled="state.isProcessingRequest || state.creatingNewChat">
            <MessageSquarePlus size="20" color="var(--gray-800)"/> <span class="text" :class="{'hide-text': isMediumContainer}">新对话</span>
          </div>
        </div>
        <div class="header__center" @mouseenter="uiState.showRenameButton = true" @mouseleave="uiState.showRenameButton = false">
          <div @click="logConversationInfo" class="center-title">
            {{ agentStore.currentThread?.title }}
          </div>
          <div class="rename-button" v-if="currentChatId" :class="{ 'visible': uiState.showRenameButton }" @click="handleRenameChat">
            <EditOutlined style="font-size: 14px; color: var(--gray-600);"/>
          </div>
          <slot name="header-center"></slot>
        </div>
        <div class="header__right">
          <!-- 分享按钮 -->
          <div class="nav-btn" @click="shareChat" v-if="currentChatId && currentAgent">
            <ShareAltOutlined style="font-size: 18px;"/>
          </div>
          <!-- <div class="nav-btn test-history" @click="getAgentHistory" v-if="currentChatId && currentAgent">
            <ThunderboltOutlined />
          </div> -->
          <slot name="header-right"></slot>
        </div>
      </div>

      <div v-if="isLoadingThreads || isLoadingMessages" class="chat-loading">
        <LoadingOutlined />
        <span>正在加载历史记录...</span>
      </div>

      <div v-else-if="!conversations.length" class="chat-examples">
        <h1>{{ currentAgent ? currentAgent.name : '请选择一个智能体开始对话' }}</h1>
        <p>{{ currentAgent ? currentAgent.description : '不同的智能体有不同的专长和能力' }}</p>
        <div class="inputer-init">
          <MessageInputComponent
            v-model="userInput"
            :is-loading="isProcessing"
            :disabled="!currentAgent"
            :send-button-disabled="!userInput || !currentAgent || isProcessing"
            :placeholder="'输入问题...'"
            @send="handleSendMessage"
            @keydown="handleKeyDown"
          />
        </div>
      </div>
      <div class="chat-box" ref="messagesContainer">
        <div class="conv-box" v-for="(conv, index) in conversations" :key="index">
          <AgentMessageComponent
            v-for="(message, msgIndex) in conv.messages"
            :message="message"
            :key="msgIndex"
            :is-processing="isProcessing && conv.status === 'streaming' && msgIndex === conv.messages.length - 1"
            :debug-mode="state.debug_mode"
            :show-refs="showMsgRefs(message)"
            @retry="retryMessage(message)"
          >
          </AgentMessageComponent>
          <!-- 显示对话最后一个消息使用的模型 -->
          <RefsComponent
            v-if="getLastMessage(conv) && conv.status !== 'streaming'"
            :message="getLastMessage(conv)"
            :show-refs="['model', 'copy']"
            :is-latest-message="false"
          />
        </div>

        <!-- 生成中的加载状态 -->
        <div class="generating-status" v-if="isProcessing && conversations.length > 0">
          <div class="generating-indicator">
            <div class="loading-dots">
              <div></div>
              <div></div>
              <div></div>
            </div>
            <span class="generating-text">正在生成回复...</span>
          </div>
        </div>
      </div>
      <div class="bottom">
        <div class="message-input-wrapper" v-if="conversations.length > 0">
          <MessageInputComponent
            v-model="userInput"
            :is-loading="isProcessing"
            :disabled="!currentAgent"
            :send-button-disabled="!userInput || !currentAgent || isProcessing"
            :placeholder="'输入问题...'"
            @send="handleSendMessage"
            @keydown="handleKeyDown"
          />
          <div class="bottom-actions">
            <p class="note">请注意辨别内容的可靠性</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch, nextTick, computed, onUnmounted, h } from 'vue';
import { ShareAltOutlined, LoadingOutlined, EditOutlined } from '@ant-design/icons-vue';
import { message, Modal } from 'ant-design-vue';
import MessageInputComponent from '@/components/MessageInputComponent.vue'
import AgentMessageComponent from '@/components/AgentMessageComponent.vue'
import ChatSidebarComponent from '@/components/ChatSidebarComponent.vue'
import RefsComponent from '@/components/RefsComponent.vue'
import { PanelLeftOpen, MessageSquarePlus } from 'lucide-vue-next';
import { ChatExporter } from '@/utils/chatExporter';
import { ErrorHandler, handleChatError, handleValidationError } from '@/utils/errorHandler';
import { ScrollController } from '@/utils/scrollController';
import { AgentValidator } from '@/utils/agentValidator';
import { useAgentStore } from '@/stores/agent';
import { storeToRefs } from 'pinia';

// ==================== PROPS & EMITS ====================
const props = defineProps({
  state: { type: Object, default: () => ({}) },
  singleMode: { type: Boolean, default: true }
});
const emit = defineEmits(['open-config', 'open-agent-modal']);

// ==================== STORE MANAGEMENT ====================
const agentStore = useAgentStore();
const {
  agents,
  currentAgentThreads,
  currentThread,
  isLoadingThreads,
  isLoadingMessages,
  conversations, // New getter from store
  isStreaming,   // New state from store
} = storeToRefs(agentStore);

// ==================== LOCAL UI STATE ====================
const userInput = ref('');
const state = reactive({
  ...props.state,
  debug_mode: computed(() => props.state.debug_mode ?? false),
  isSidebarOpen: localStorage.getItem('chat_sidebar_open', 'true') === 'true',
  creatingNewChat: false,
  isInitialRender: true
});

const uiState = reactive({
  showRenameButton: false,
  containerWidth: 0,
});

// ==================== COMPUTED PROPERTIES ====================
const currentAgent = computed(() => agentStore.selectedAgent);
const currentChatId = computed(() => agentStore.currentThreadId);
const chatsList = computed(() => currentAgentThreads.value || []);
const isProcessing = computed(() => isStreaming.value || state.creatingNewChat);
const isSmallContainer = computed(() => uiState.containerWidth <= 520);
const isMediumContainer = computed(() => uiState.containerWidth <= 768);

// ==================== SCROLL & RESIZE HANDLING ====================
const chatContainerRef = ref(null);
const scrollController = new ScrollController('.chat');
let resizeObserver = null;

onMounted(() => {
  nextTick(() => {
    if (chatContainerRef.value) {
      uiState.containerWidth = chatContainerRef.value.offsetWidth;
      resizeObserver = new ResizeObserver(entries => {
        for (let entry of entries) {
          uiState.containerWidth = entry.contentRect.width;
        }
      });
      resizeObserver.observe(chatContainerRef.value);
    }
    const chatContainer = document.querySelector('.chat');
    if (chatContainer) {
      chatContainer.addEventListener('scroll', scrollController.handleScroll, { passive: true });
    }
  });
  setTimeout(() => { state.isInitialRender = false; }, 300);
});

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect();
  scrollController.cleanup();
});

// ==================== CHAT ACTIONS (DELEGATE TO STORE) ====================

const createNewChat = async () => {
  if (!AgentValidator.validateAgentId(agentStore.selectedAgentId, '创建对话') || isProcessing.value) return;
  if (currentChatId.value && conversations.value.length === 0) return;

  state.creatingNewChat = true;
  try {
    await agentStore.createThread(agentStore.selectedAgentId, '新的对话');
  } catch (error) {
    handleChatError(error, 'create');
  } finally {
    state.creatingNewChat = false;
  }
};

const selectChat = async (chatId) => {
  if (!AgentValidator.validateAgentIdWithError(agentStore.selectedAgentId, '选择对话', handleValidationError)) return;
  agentStore.selectThread(chatId);
  await agentStore.fetchThreadMessages(chatId);
  await nextTick();
  scrollController.scrollToBottomStaticForce();
};

const deleteChat = async (chatId) => {
  if (!AgentValidator.validateAgentIdWithError(agentStore.selectedAgentId, '删除对话', handleValidationError)) return;
  try {
    await agentStore.deleteThread(chatId);
  } catch (error) {
    handleChatError(error, 'delete');
  }
};

const renameChat = async (data) => {
  let { chatId, title } = data;
  if (!AgentValidator.validateRenameOperation(chatId, title, agentStore.selectedAgentId, handleValidationError)) return;
  if (title.length > 30) title = title.slice(0, 30);
  try {
    await agentStore.updateThread(chatId, title);
  } catch (error) {
    handleChatError(error, 'rename');
  }
};

const handleSendMessage = async () => {
  const text = userInput.value.trim();
  if (!text || !currentAgent.value || isProcessing.value) return;

  userInput.value = '';
  // Enable auto scroll before sending message to ensure proper scrolling during streaming
  await nextTick();
  await scrollController.scrollToBottom(true);

  try {
    await agentStore.sendMessage(text);
  } catch (error) {
    // Error is already handled in the store, but you could add UI feedback here if needed
  }
};

// ==================== UI HANDLERS ====================

const handleRenameChat = () => {
  if (!currentChatId.value || !currentThread.value) {
    handleValidationError('请先选择对话');
    return;
  }
  let newTitle = currentThread.value.title;
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
    onOk: () => renameChat({ chatId: currentChatId.value, title: newTitle }),
  });
};

const handleKeyDown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSendMessage();
  }
};

const shareChat = async () => {
  if (!AgentValidator.validateShareOperation(currentChatId.value, currentAgent.value, handleValidationError)) return;
  try {
    const result = await ChatExporter.exportToHTML({
      chatTitle: agentStore.currentThread?.title || '新对话',
      agentName: currentAgent.value?.name || '智能助手',
      agentDescription: currentAgent.value?.description || '',
      messages: conversations.value, // Use the getter from store
      onGoingMessages: [] // This is now part of conversations
    });
    message.success(`对话已导出为HTML文件: ${result.filename}`);
  } catch (error) {
    handleChatError(error, 'export');
  }
};

const retryMessage = (msg) => { /* TODO */ };

const toggleSidebar = () => {
  state.isSidebarOpen = !state.isSidebarOpen;
  localStorage.setItem('chat_sidebar_open', state.isSidebarOpen);
};

const openAgentModal = () => emit('open-agent-modal');

// ==================== CONVERSATION INFO LOGGING ====================

const logConversationInfo = () => {
  console.log(agentStore.currentThread);

  // 输出对话历史消息
  console.group('📜 对话历史消息');
  console.log('原始消息数组:', agentStore.currentThreadMessages);
  console.log('消息总数:', agentStore.currentThreadMessages.length);
  console.groupEnd();

  // 输出流式对话状态
  if (agentStore.isStreaming || agentStore.onGoingConvMessages.length > 0) {
    console.log('进行中的消息:', agentStore.onGoingConvMessages);
    console.log('消息块:', agentStore.onGoingConv.msgChunks);
    console.groupEnd();
  }

  console.groupEnd();
};

// ==================== HELPER FUNCTIONS ====================

const getLastMessage = (conv) => {
  if (!conv?.messages?.length) return null;
  for (let i = conv.messages.length - 1; i >= 0; i--) {
    if (conv.messages[i].type === 'ai') return conv.messages[i];
  }
  return null;
};

const showMsgRefs = (msg) => {
  if (msg.isLast) return ['copy'];
  return false;
};

// ==================== LIFECYCLE & WATCHERS ====================

const initAll = async () => {
  try {
    if (!agentStore.isInitialized) {
      await agentStore.initialize();
    }
    await loadChatsList();
  } catch (error) {
    handleChatError(error, 'load');
  }
};

const loadChatsList = async () => {
  try {
    if (!AgentValidator.validateLoadOperation(agentStore.selectedAgentId, '加载对话列表')) return;
    await agentStore.fetchThreads(agentStore.selectedAgentId);

    if (currentAgentThreads.value && currentAgentThreads.value.length > 0) {
      const threadToSelect = currentAgentThreads.value[0].id;
      agentStore.selectThread(threadToSelect);
      await agentStore.fetchThreadMessages(threadToSelect);
    } else {
      await createNewChat();
    }
  } catch (error) {
    handleChatError(error, 'load');
  }
};

onMounted(async () => {
  await initAll();
  scrollController.enableAutoScroll();
  watch(() => agentStore.selectedAgentId, (newAgentId, oldAgentId) => {
    if (newAgentId && newAgentId !== oldAgentId) {
      initAll();
    }
  });

  // 只监听streaming状态，用于流式消息的智能滚动
  watch(conversations, () => {
    if (isProcessing.value) {
      scrollController.scrollToBottom();
    }
  }, { deep: true, flush: 'post' });
});

</script>

<style lang="less" scoped>
@import '@/assets/css/main.css';

.chat-container {
  display: flex;
  width: 100%;
  height: 100%;
  position: relative;
}

.sidebar-backdrop {
  display: none; /* 默认隐藏，通过v-if控制显示 */
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.4);
  z-index: 99;
  animation: fadeIn 0.3s ease;
}

.floating-sidebar {
  position: absolute !important;
  z-index: 100;
  height: 100%;
  left: 0;
  top: 0;
  transform: translateX(0);
  transition: transform 0.3s ease;
  width: 80% !important;
  max-width: 300px;

  &.no-transition {
    transition: none !important;
  }

  &.collapsed {
    transform: translateX(-100%);
  }
}

.chat {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
  background: white;
  position: relative;
  box-sizing: border-box;
  overflow-y: scroll;
  transition: all 0.3s ease;

  .chat-header {
    user-select: none;
    position: sticky;
    top: 0;
    z-index: 10;
    background-color: white;
    height: var(--header-height);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 8px;
    border-bottom: 1px solid var(--main-20);

    .header__left, .header__right, .header__center {
      display: flex;
      align-items: center;
    }

    .header__center {
      position: relative;
      display: flex;
      align-items: center;
      gap: 8px;

      .center-title {
        max-width: 200px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .rename-button {
         display: flex;
         align-items: center;
         justify-content: center;
         width: 24px;
         height: 24px;
         border-radius: 4px;
         cursor: pointer;
         opacity: 0;
         transition: all 0.2s ease;

         &.visible {
           opacity: 1;
         }

         &:hover {
           background-color: var(--gray-100);
         }
       }
    }
  }

  .nav-btn {
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

.chat-examples {
  padding: 0 50px;
  text-align: center;
  position: absolute;
  top: 20%;
  width: 100%;
  z-index: 9;
  animation: slideInUp 0.5s ease-out;

  h1 {
    margin-bottom: 20px;
    font-size: 1.3rem;
    color: var(--gray-1000);
  }

  p {
    font-size: 1.1rem;
    color: var(--gray-700);
  }

  .inputer-init {
    margin: 40px auto;
    width: 90%;
    max-width: 800px;
  }
}

.chat-loading {
  padding: 0 50px;
  text-align: center;
  position: absolute;
  top: 20%;
  width: 100%;
  z-index: 9;
  animation: slideInUp 0.5s ease-out;

  span {
    margin-left: 8px;
    color: var(--gray-700);
  }
}

.chat-box {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  flex-grow: 1;
  padding: 1rem 2rem;
  display: flex;
  flex-direction: column;
}

.conv-box {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bottom {
  position: sticky;
  bottom: 0;
  width: 100%;
  margin: 0 auto;
  padding: 4px 2rem 0 2rem;
  background: white;

  .message-input-wrapper {
    width: 100%;
    max-width: 800px;
    margin: 0 auto;

    .bottom-actions {
      display: flex;
      justify-content: center;
      align-items: center;
    }

    .note {
      font-size: small;
      color: #ccc;
      margin: 4px 0;
      user-select: none;
    }
  }
}

.conversation-list::-webkit-scrollbar {
  position: absolute;
  width: 4px;
  height: 4px;
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

.chat::-webkit-scrollbar {
  position: absolute;
  width: 4px;
  height: 4px;
}

.chat::-webkit-scrollbar-track {
  background: transparent;
  border-radius: 4px;
}

.chat::-webkit-scrollbar-thumb {
  background: var(--gray-400);
  border-radius: 4px;
}

.chat::-webkit-scrollbar-thumb:hover {
  background: rgb(100, 100, 100);
  border-radius: 4px;
}

.loading-dots {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
}

.loading-dots div {
  width: 6px;
  height: 6px;
  background: linear-gradient(135deg, var(--main-color), var(--main-700));
  border-radius: 50%;
  animation: dotPulse 1.4s infinite ease-in-out both;
  box-shadow: 0 1px 3px rgba(59, 130, 246, 0.3);
}

.loading-dots div:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots div:nth-child(2) {
  animation-delay: -0.16s;
}

.loading-dots div:nth-child(3) {
  animation-delay: 0s;
}

.generating-status {
  display: flex;
  justify-content: flex-start;
  padding: 1rem 0;
  animation: fadeInUp 0.4s ease-out;
  transition: all 0.2s;
}

.generating-indicator {
  display: flex;
  align-items: center;
  padding: 0.75rem 0rem;

  .generating-text {
    margin-left: 12px;
    color: var(--gray-700);
    font-size: 14px;
    font-weight: 500;
    letter-spacing: 0.025em;
  }
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
      background-color: var(--main-20);
    }

    .nav-btn-icon {
      width: 1.5rem;
      height: 1.5rem;
    }
  }
}

@keyframes dotPulse {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  40% {
    transform: scale(1.1);
    opacity: 1;
  }
}

@keyframes shimmer {
  0% {
    left: -100%;
  }
  100% {
    left: 100%;
  }
}

@keyframes swing-in-top-fwd {
  0% {
    transform: rotateX(-100deg);
    transform-origin: top;
    opacity: 0;
  }
  100% {
    transform: rotateX(0deg);
    transform-origin: top;
    opacity: 1;
  }
}

@keyframes slideInUp {
  from {
    transform: translateY(20px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

@media (max-width: 768px) {
  .chat-sidebar.collapsed {
    width: 0;
    border: none;
  }

  .chat-header {
    .header__left {
      .text {
        display: none;
      }
    }
  }
}

@media (max-width: 520px) {
  .sidebar-backdrop {
    display: block;
  }

  .chat-box {
    padding: 1rem 1rem;
  }

  .bottom {
    padding: 0.5rem 0.5rem;
  }

  .chat-header {
    padding: 0.5rem 0 !important;

    .nav-btn {
      font-size: 14px !important;
      padding: 0.4rem 0.8rem !important;
    }
  }

  .floating-sidebar {
    position: fixed;
    z-index: 100;
    height: 100%;
    left: 0;
    top: 0;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    transform: translateX(0);
    transition: transform 0.3s ease;
    width: 80% !important;
    max-width: 300px;

    &.collapsed {
      transform: translateX(-100%);
    }
  }
}

.hide-text {
  display: none;
}
</style>
