<template>
  <div class="chat-container" ref="chatContainerRef">
    <ChatSidebarComponent
      :current-chat-id="currentChatId"
      :chats-list="chatsList"
      :is-sidebar-open="uiState.isSidebarOpen"
      :is-initial-render="uiState.isInitialRender"
      :single-mode="props.singleMode"
      :agents="agents"
      :selected-agent-id="currentAgentId"
      @create-chat="createNewChat"
      @select-chat="selectChat"
      @delete-chat="deleteChat"
      @rename-chat="renameChat"
      @toggle-sidebar="toggleSidebar"
      @open-agent-modal="openAgentModal"
      :class="{
        'floating-sidebar': isSmallContainer,
        'sidebar-open': uiState.isSidebarOpen,
        'no-transition': uiState.isInitialRender,
        'collapsed': isSmallContainer && !uiState.isSidebarOpen
      }"
    />
    <div class="sidebar-backdrop" v-if="uiState.isSidebarOpen && isSmallContainer" @click="toggleSidebar"></div>
    <div class="chat">
      <div class="chat-header">
        <div class="header__left">
          <slot name="header-left" class="nav-btn"></slot>
          <div class="toggle-sidebar nav-btn" v-if="!uiState.isSidebarOpen" @click="toggleSidebar">
            <PanelLeftOpen size="20" color="var(--gray-800)"/>
          </div>
          <div class="newchat nav-btn" v-if="!uiState.isSidebarOpen" @click="createNewChat" :disabled="isProcessing">
            <MessageSquarePlus size="20" color="var(--gray-800)"/> <span class="text" :class="{'hide-text': isMediumContainer}">新对话</span>
          </div>
        </div>
        <div class="header__center" @mouseenter="uiState.showRenameButton = true" @mouseleave="uiState.showRenameButton = false">
          <div @click="logConversationInfo" class="center-title">
            {{ currentThread?.title }}
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
        <img v-if="currentAgentMetadata?.icon" class="agent-icons" :src="currentAgentMetadata?.icon" alt="智能体图标" />
        <div v-else style="margin-bottom: 150px"></div>
        <h1>您好，我是{{ currentAgentName }}！有什么可以帮您？</h1>
        <!-- <h1>{{ currentAgent ? currentAgent.name : '请选择一个智能体开始对话' }}</h1>
        <p>{{ currentAgent ? currentAgent.description : '不同的智能体有不同的专长和能力' }}</p> -->

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

          <!-- 示例问题 -->
          <div class="example-questions" v-if="exampleQuestions.length > 0">
            <div class="example-title">或试试这些问题：</div>
            <div class="example-chips">
              <div
                v-for="question in exampleQuestions"
                :key="question.id"
                class="example-chip"
                @click="handleExampleClick(question.text)"
              >
                {{ question.text }}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="chat-box" ref="messagesContainer">
        <div class="conv-box" v-for="(conv, index) in conversations" :key="index">
          <AgentMessageComponent
            v-for="(message, msgIndex) in conv.messages"
            :message="message"
            :key="msgIndex"
            :is-processing="isProcessing && conv.status === 'streaming' && msgIndex === conv.messages.length - 1"
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
import { handleChatError, handleValidationError } from '@/utils/errorHandler';
import { ScrollController } from '@/utils/scrollController';
import { AgentValidator } from '@/utils/agentValidator';
import { useAgentStore } from '@/stores/agent';
import { storeToRefs } from 'pinia';
import { MessageProcessor } from '@/utils/messageProcessor';
import { agentApi, threadApi } from '@/apis';

// ==================== PROPS & EMITS ====================
const props = defineProps({
  state: { type: Object, default: () => ({}) },
  agentId: { type: String, default: '' },
  singleMode: { type: Boolean, default: true }
});
const emit = defineEmits(['open-config', 'open-agent-modal']);

// ==================== STORE MANAGEMENT ====================
const agentStore = useAgentStore();
const {
  agents,
  selectedAgentId,
  defaultAgentId,
} = storeToRefs(agentStore);

// ==================== LOCAL CHAT & UI STATE ====================
const userInput = ref('');

// 从智能体元数据获取示例问题
const exampleQuestions = computed(() => {
  const examples = currentAgentMetadata.value?.examples || [];
  return examples.map((text, index) => ({
    id: index + 1,
    text: text
  }));
});

const chatState = reactive({
  currentThreadId: null,
  isLoadingThreads: false,
  isLoadingMessages: false,
  creatingNewChat: false,
  // 以threadId为键的线程状态
  threadStates: {}
});

// 组件级别的线程和消息状态
const threads = ref([]);
const threadMessages = ref({});

const uiState = reactive({
  ...props.state,
  isSidebarOpen: localStorage.getItem('chat_sidebar_open') !== 'false',
  isInitialRender: true,
  showRenameButton: false,
  containerWidth: 0,
});

// ==================== COMPUTED PROPERTIES ====================
const currentAgentId = computed(() => {
  if (props.singleMode) {
    return props.agentId || defaultAgentId.value;
  } else {
    return selectedAgentId.value;
  }
});

const currentAgentMetadata = computed(() => {
  if (agentStore?.metadata && CurrentAgentId.value in agentStore?.metadata[currentAgentId.value]) {
    return agentStore?.metadata[currentAgentId.value]
  }
  return {}
});
const currentAgentName = computed(() => currentAgentMetadata.value?.name || currentAgent.name || '智能体');

const currentAgent = computed(() => agents.value[currentAgentId.value] || null);
const chatsList = computed(() => threads.value || []);
const currentChatId = computed(() => chatState.currentThreadId);
const currentThread = computed(() => {
  if (!currentChatId.value) return null;
  return threads.value.find(thread => thread.id === currentChatId.value) || null;
});

const currentThreadMessages = computed(() => threadMessages.value[currentChatId.value] || []);

// 当前线程状态的computed属性
const currentThreadState = computed(() => {
  return getThreadState(currentChatId.value);
});

const onGoingConvMessages = computed(() => {
  const threadState = currentThreadState.value;
  if (!threadState || !threadState.onGoingConv) return [];

  const msgs = Object.values(threadState.onGoingConv.msgChunks).map(MessageProcessor.mergeMessageChunk);
  return msgs.length > 0
    ? MessageProcessor.convertToolResultToMessages(msgs).filter(msg => msg.type !== 'tool')
    : [];
});

const conversations = computed(() => {
  const historyConvs = MessageProcessor.convertServerHistoryToMessages(currentThreadMessages.value);
  if (onGoingConvMessages.value.length > 0) {
    const onGoingConv = {
      messages: onGoingConvMessages.value,
      status: 'streaming'
    };
    return [...historyConvs, onGoingConv];
  }
  return historyConvs;
});

const isLoadingThreads = computed(() => chatState.isLoadingThreads);
const isLoadingMessages = computed(() => chatState.isLoadingMessages);
const isStreaming = computed(() => {
  const threadState = currentThreadState.value;
  return threadState ? threadState.isStreaming : false;
});
const isProcessing = computed(() => isStreaming.value || chatState.creatingNewChat);
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
  setTimeout(() => { uiState.isInitialRender = false; }, 300);
});

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect();
  scrollController.cleanup();
  // 清理所有线程状态
  resetOnGoingConv();
});

// ==================== THREAD STATE MANAGEMENT ====================
// 获取指定线程的状态，如果不存在则创建
const getThreadState = (threadId) => {
  if (!threadId) return null;
  if (!chatState.threadStates[threadId]) {
    chatState.threadStates[threadId] = {
      isStreaming: false,
      streamAbortController: null,
      onGoingConv: { msgChunks: {} }
    };
  }
  return chatState.threadStates[threadId];
};

// 清理指定线程的状态
const cleanupThreadState = (threadId) => {
  if (!threadId) return;
  const threadState = chatState.threadStates[threadId];
  if (threadState) {
    if (threadState.streamAbortController) {
      threadState.streamAbortController.abort();
    }
    delete chatState.threadStates[threadId];
  }
};

// ==================== STREAM HANDLING LOGIC ====================
const resetOnGoingConv = (threadId = null) => {
  if (threadId) {
    // 清理指定线程的状态
    const threadState = getThreadState(threadId);
    if (threadState) {
      if (threadState.streamAbortController) {
        threadState.streamAbortController.abort();
        threadState.streamAbortController = null;
      }
      threadState.onGoingConv = { msgChunks: {} };
    }
  } else {
    // 清理当前线程或所有线程的状态
    const targetThreadId = currentChatId.value;
    if (targetThreadId) {
      const threadState = getThreadState(targetThreadId);
      if (threadState) {
        if (threadState.streamAbortController) {
          threadState.streamAbortController.abort();
          threadState.streamAbortController = null;
        }
        threadState.onGoingConv = { msgChunks: {} };
      }
    } else {
      // 如果没有当前线程，清理所有线程状态
      Object.keys(chatState.threadStates).forEach(tid => {
        cleanupThreadState(tid);
      });
    }
  }
};

const _processStreamChunk = (chunk, threadId) => {
  const { status, msg, request_id, message } = chunk;
  const threadState = getThreadState(threadId);

  if (!threadState) return;

  switch (status) {
    case 'init':
      threadState.onGoingConv.msgChunks[request_id] = [msg];
      break;
    case 'loading':
      if (msg.id) {
        if (!threadState.onGoingConv.msgChunks[msg.id]) {
          threadState.onGoingConv.msgChunks[msg.id] = [];
        }
        threadState.onGoingConv.msgChunks[msg.id].push(msg);
      }
      break;
    case 'error':
      handleChatError({ message }, 'stream');
      // Stop the loading indicator
      if (threadState) {
        threadState.isStreaming = false;

        // Create a new AI message chunk for the error
        const errorMsgChunk = {
          id: 'ai-error-' + Date.now(),
          type: 'ai',
          role: 'assistant',
          content: chunk.message || 'An error occurred',
          isError: true // Custom flag for styling
        };

        // Add this to the chunks of the ongoing conversation
        if (threadState.onGoingConv && threadState.onGoingConv.msgChunks) {
          threadState.onGoingConv.msgChunks[errorMsgChunk.id] = [errorMsgChunk];
        }

        // Abort the stream controller to stop processing further events
        if (threadState.streamAbortController) {
          threadState.streamAbortController.abort();
          threadState.streamAbortController = null;
        }
      }
      // We no longer call resetOnGoingConv to keep the context.
      break;
    case 'finished':
          fetchThreadMessages({ agentId: currentAgentId.value, threadId: threadId });
          resetOnGoingConv(threadId);
          break;
  }
};

// ==================== 线程管理方法 ====================
// 获取当前智能体的线程列表
const fetchThreads = async (agentId = null) => {
  const targetAgentId = agentId || currentAgentId.value;
  if (!targetAgentId) return;

  chatState.isLoadingThreads = true;
  try {
    const fetchedThreads = await threadApi.getThreads(targetAgentId);
    threads.value = fetchedThreads || [];
  } catch (error) {
    console.error('Failed to fetch threads:', error);
    handleChatError(error, 'fetch');
    throw error;
  } finally {
    chatState.isLoadingThreads = false;
  }
};

// 创建新线程
const createThread = async (agentId, title = '新的对话') => {
  if (!agentId) return null;

  chatState.isCreatingThread = true;
  try {
    const thread = await threadApi.createThread(agentId, title);
    if (thread) {
      threads.value.unshift(thread);
      threadMessages.value[thread.id] = [];
    }
    return thread;
  } catch (error) {
    console.error('Failed to create thread:', error);
    handleChatError(error, 'create');
    throw error;
  } finally {
    chatState.isCreatingThread = false;
  }
};

// 删除线程
const deleteThread = async (threadId) => {
  if (!threadId) return;

  chatState.isDeletingThread = true;
  try {
    await threadApi.deleteThread(threadId);
    threads.value = threads.value.filter(thread => thread.id !== threadId);
    delete threadMessages.value[threadId];

    if (chatState.currentThreadId === threadId) {
      chatState.currentThreadId = null;
    }
  } catch (error) {
    console.error('Failed to delete thread:', error);
    handleChatError(error, 'delete');
    throw error;
  } finally {
    chatState.isDeletingThread = false;
  }
};

// 更新线程标题
const updateThread = async (threadId, title) => {
  if (!threadId || !title) return;

  chatState.isRenamingThread = true;
  try {
    await threadApi.updateThread(threadId, title);
    const thread = threads.value.find(t => t.id === threadId);
    if (thread) {
      thread.title = title;
    }
  } catch (error) {
    console.error('Failed to update thread:', error);
    handleChatError(error, 'update');
    throw error;
  } finally {
    chatState.isRenamingThread = false;
  }
};

// 获取线程消息
const fetchThreadMessages = async ({ agentId, threadId }) => {
  if (!threadId || !agentId) return;

  try {
    const response = await agentApi.getAgentHistory(agentId, threadId);
    threadMessages.value[threadId] = response.history || [];
  } catch (error) {
    handleChatError(error, 'load');
    throw error;
  }
};

// 发送消息并处理流式响应
const sendMessage = async ({ agentId, threadId, text }) => {
  if (!agentId || !threadId || !text) {
    const error = new Error("Missing agent, thread, or message text");
    handleChatError(error, 'send');
    return Promise.reject(error);
  }

  // 如果是新对话，用消息内容作为标题
  if ((threadMessages.value[threadId] || []).length === 0) {
    updateThread(threadId, text);
  }

  const requestData = {
    query: text,
    config: {
      thread_id: threadId,
    },
  };

  try {
    return await agentApi.sendAgentMessage(agentId, requestData);
  } catch (error) {
    handleChatError(error, 'send');
    throw error;
  }
};

// 添加消息到线程
const addMessageToThread = (threadId, message) => {
  if (!threadId || !message) return;

  if (!threadMessages.value[threadId]) {
    threadMessages.value[threadId] = [];
  }

  threadMessages.value[threadId].push(message);
};

// 更新线程中的消息
const updateMessageInThread = (threadId, messageIndex, updatedMessage) => {
  if (!threadId || messageIndex < 0 || !threadMessages.value[threadId]) return;

  if (messageIndex < threadMessages.value[threadId].length) {
    threadMessages.value[threadId][messageIndex] = updatedMessage;
  }
};

// ==================== CHAT ACTIONS ====================
// 检查第一个对话是否为空
const isFirstChatEmpty = () => {
  if (threads.value.length === 0) return false;
  const firstThread = threads.value[0];
  const firstThreadMessages = threadMessages.value[firstThread.id] || [];
  return firstThreadMessages.length === 0;
};

// 如果第一个对话为空，直接切换到第一个对话
const switchToFirstChatIfEmpty = async () => {
  if (threads.value.length > 0 && isFirstChatEmpty()) {
    await selectChat(threads.value[0].id);
    return true;
  }
  return false;
};

const createNewChat = async () => {
  if (!AgentValidator.validateAgentId(currentAgentId.value, '创建对话') || isProcessing.value) return;

  // 如果第一个对话为空，直接切换到第一个对话而不是创建新对话
  if (await switchToFirstChatIfEmpty()) return;

  // 只有当当前对话是第一个对话且为空时，才阻止创建新对话
  const currentThreadIndex = threads.value.findIndex(thread => thread.id === currentChatId.value);
  if (currentChatId.value && conversations.value.length === 0 && currentThreadIndex === 0) return;

  chatState.creatingNewChat = true;
  try {
    const newThread = await createThread(currentAgentId.value, '新的对话');
    if (newThread) {
      chatState.currentThreadId = newThread.id;
    }
  } catch (error) {
    handleChatError(error, 'create');
  } finally {
    chatState.creatingNewChat = false;
  }
};

const selectChat = async (chatId) => {
  if (!AgentValidator.validateAgentIdWithError(currentAgentId.value, '选择对话', handleValidationError)) return;

  // 切换线程时，不再中断上一个线程的流式输出
  // resetOnGoingConv(chatState.currentThreadId);
  chatState.currentThreadId = chatId;
  chatState.isLoadingMessages = true;
  try {
    await fetchThreadMessages({ agentId: currentAgentId.value, threadId: chatId });
  } catch (error) {
    handleChatError(error, 'load');
  } finally {
    chatState.isLoadingMessages = false;
  }

  await nextTick();
  scrollController.scrollToBottomStaticForce();
};

const deleteChat = async (chatId) => {
  if (!AgentValidator.validateAgentIdWithError(currentAgentId.value, '删除对话', handleValidationError)) return;
  try {
    await deleteThread(chatId);
    if (chatState.currentThreadId === chatId) {
      chatState.currentThreadId = null;
      if (chatsList.value.length > 0) {
        await selectChat(chatsList.value[0].id);
      }
    }
  } catch (error) {
    handleChatError(error, 'delete');
  }
};

const renameChat = async (data) => {
  let { chatId, title } = data;
  if (!AgentValidator.validateRenameOperation(chatId, title, currentAgentId.value, handleValidationError)) return;
  if (title.length > 30) title = title.slice(0, 30);
  try {
    await updateThread(chatId, title);
  } catch (error) {
    handleChatError(error, 'rename');
  }
};

const handleSendMessage = async () => {
  const text = userInput.value.trim();
  if (!text || !currentAgent.value || isProcessing.value) return;

  // 如果没有当前线程，先创建一个新线程
  if (!currentChatId.value) {
    try {
      const newThread = await createThread(currentAgentId.value, text);
      if (newThread) {
        chatState.currentThreadId = newThread.id;
      } else {
        message.error('创建对话失败，请重试');
        return;
      }
    } catch (error) {
      handleChatError(error, 'create');
      return;
    }
  }

  userInput.value = '';
  await nextTick();
  scrollController.scrollToBottom(true);

  const threadId = currentChatId.value;
  const threadState = getThreadState(threadId);
  if (!threadState) return;

  threadState.isStreaming = true;
  resetOnGoingConv(threadId);
  threadState.streamAbortController = new AbortController();

  try {
    const response = await sendMessage({
      agentId: currentAgentId.value,
      threadId: currentChatId.value,
      text: text
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      if (!threadState.streamAbortController || threadState.streamAbortController.signal.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.trim() && threadState.streamAbortController && !threadState.streamAbortController.signal.aborted) {
          try {
            const chunk = JSON.parse(line.trim());
            _processStreamChunk(chunk, threadId);
          } catch (e) { console.warn('Failed to parse stream chunk JSON:', e); }
        }
      }
    }
    if (buffer.trim() && threadState.streamAbortController && !threadState.streamAbortController.signal.aborted) {
      try {
        const chunk = JSON.parse(buffer.trim());
        _processStreamChunk(chunk, threadId);
      } catch (e) { console.warn('Failed to parse final stream chunk JSON:', e); }
    }
  } catch (error) {
    if (error.name !== 'AbortError') {
      handleChatError(error, 'send');
    }
  } finally {
    threadState.isStreaming = false;
    threadState.streamAbortController = null;
    resetOnGoingConv(threadId);
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

// 处理示例问题点击
const handleExampleClick = (questionText) => {
  userInput.value = questionText;
  nextTick(() => {
    handleSendMessage();
  });
};

const shareChat = async () => {
  if (!AgentValidator.validateShareOperation(currentChatId.value, currentAgent.value, handleValidationError)) return;
  try {
    const result = await ChatExporter.exportToHTML({
      chatTitle: currentThread.value?.title || '新对话',
      agentName: currentAgent.value?.name || '智能助手',
      agentDescription: currentAgent.value?.description || '',
      messages: conversations.value,
      onGoingMessages: []
    });
    message.success(`对话已导出为HTML文件: ${result.filename}`);
  } catch (error) {
    handleChatError(error, 'export');
  }
};

const retryMessage = (msg) => { /* TODO */ };
const toggleSidebar = () => {
  uiState.isSidebarOpen = !uiState.isSidebarOpen;
  localStorage.setItem('chat_sidebar_open', uiState.isSidebarOpen);
};
const openAgentModal = () => emit('open-agent-modal');

// ==================== CONVERSATION INFO LOGGING ====================
const logConversationInfo = () => {
  console.log(currentThread.value);
  console.group('📜 对话历史消息');
  console.log('原始消息数组:', currentThreadMessages.value);
  console.log('消息总数:', currentThreadMessages.value.length);
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
const loadChatsList = async () => {
  const agentId = currentAgentId.value;
  if (!agentId) {
    console.warn('No agent selected, cannot load chats list');
    threads.value = [];
    chatState.currentThreadId = null;
    return;
  }

  try {
    await fetchThreads(agentId);
    if (currentAgentId.value !== agentId) return;

    // 如果当前线程不在线程列表中，清空当前线程
    if (chatState.currentThreadId && !threads.value.find(t => t.id === chatState.currentThreadId)) {
      chatState.currentThreadId = null;
    }

    // 如果有线程但没有选中任何线程，自动选择第一个
    if (threads.value.length > 0 && !chatState.currentThreadId) {
      await selectChat(threads.value[0].id);
    }
  } catch (error) {
    handleChatError(error, 'load');
  }
};

const initAll = async () => {
  try {
    if (!agentStore.isInitialized) {
      await agentStore.initialize();
    }
  } catch (error) {
    handleChatError(error, 'load');
  }
};

onMounted(async () => {
  await initAll();
  scrollController.enableAutoScroll();
});

watch(currentAgentId, async (newAgentId, oldAgentId) => {
  if (newAgentId !== oldAgentId) {
    // 清理当前线程状态
    chatState.currentThreadId = null;
    threadMessages.value = {};
    // 清理所有线程状态
    resetOnGoingConv();

    if (newAgentId) {
      await loadChatsList();
    } else {
      threads.value = [];
    }
  }
}, { immediate: true });

watch(conversations, () => {
  if (isProcessing.value) {
    scrollController.scrollToBottom();
  }
}, { deep: true, flush: 'post' });

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
  top: 15%;
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

  .agent-icons {
    height: 180px;
  }

  .example-questions {
    margin-top: 16px;
    text-align: center;

    .example-title {
      font-size: 0.85rem;
      color: var(--gray-600);
      margin-bottom: 12px;
    }

    .example-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: center;
    }

    .example-chip {
      padding: 6px 12px;
      background: var(--gray-25);
      // border: 1px solid var(--gray-100);
      border-radius: 16px;
      cursor: pointer;
      font-size: 0.8rem;
      color: var(--gray-700);
      transition: all 0.15s ease;
      white-space: nowrap;
      max-width: 200px;
      overflow: hidden;
      text-overflow: ellipsis;

      &:hover {
        // background: var(--main-25);
        border-color: var(--main-200);
        color: var(--main-700);
        box-shadow: 0 0px 4px rgba(0, 0, 0, 0.03);
      }

      &:active {
        transform: translateY(0);
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
      }
    }
  }

  .inputer-init {
    margin: 20px auto;
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
