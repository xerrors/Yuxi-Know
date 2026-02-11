<template>
  <div class="chat-view">
    <!-- 顶部标签栏 -->
    <div class="chat-header-tabs" v-if="false">
      <div class="tab-item" :class="{ active: true }">
        {{ currentAgentName || '大模型名称' }}
      </div>
    </div>

    <!-- 主内容区域 -->
    <div class="chat-main-container">
      <!-- 左侧主内容区 -->
      <div class="chat-content">
        <!-- 欢迎区域（无对话时显示） -->
        <div v-if="!currentThreadId || conversations.length === 0" class="welcome-section">
          <div class="welcome-emoji">👋</div>
          <h1 class="welcome-greeting">{{ greeting }}</h1>
          <p class="welcome-intro">我是你的智能合规管控小助手,请问现在能帮您做什么?</p>
          
          <!-- 建议操作按钮（随机两条）
          <div class="suggested-actions">
            <div
              v-for="(question, index) in randomSuggestions"
              :key="index"
              class="action-button"
              @click="handleSuggestionClick(question)"
            >
              <span>{{ question }}</span>
              <span class="arrow-icon">→</span>
            </div>
          </div> -->
        </div>
        
        <!-- 对话消息列表（有对话时显示） -->
        <div v-else class="messages-container">
          <div
            v-for="(conversation, convIndex) in conversations"
            :key="convIndex"
            class="conversation-wrapper"
          >
            <AgentMessageComponent
              v-for="(msg, msgIndex) in conversation.messages"
              :key="`msg-${convIndex}-${msgIndex}-${msg.id || msg.type}-${msg.content?.length || 0}`"
              :message="msg"
              :is-processing="
                isProcessing &&
                conversation.status === 'streaming' &&
                msgIndex === conversation.messages.length - 1
              "
              :show-refs="false"
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

        <!-- 底部输入区域 - 放在左侧内容区底部 -->
        <div class="chat-input-wrapper">
          <div class="chat-input-area">
            <div class="input-icons" v-if="false">
              <a-tooltip title="切换智能体">
                <div class="input-icon" @click="openAgentModal">
                  <Bot :size="20" />
                </div>
              </a-tooltip>
              <a-tooltip title="添加附件">
                <label class="input-icon" style="cursor: pointer;">
                  <input
                    ref="fileInputRef"
                    type="file"
                    multiple
                    accept=".txt,.md,.docx,.html,.htm"
                    style="display: none"
                    @change="handleFileChange"
                  />
                  <FileText :size="20" />
                </label>
              </a-tooltip>
              <a-tooltip title="上传图片">
                <label class="input-icon" style="cursor: pointer;">
                  <input
                    ref="imageInputRef"
                    type="file"
                    accept="image/*"
                    style="display: none"
                    @change="handleImageChange"
                  />
                  <Image :size="20" />
                </label>
              </a-tooltip>
            </div>
            <input
              v-model="inputText"
              type="text"
              class="chat-input"
              placeholder="请输入您的问题..."
              @keyup.enter="handleSend"
              :disabled="isProcessing"
            />
            <a-tooltip :title="isProcessing ? '停止回答' : '发送'">
              <button 
                class="send-button" 
                @click="handleSendOrStop" 
                :disabled="(!inputText.trim() && !currentImage && currentAttachments.length === 0) && !isProcessing"
              >
                <Square v-if="isProcessing" :size="20" />
                <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
              </button>
            </a-tooltip>
          </div>
          <!-- 附件状态按钮和图片预览 - 放在输入框下方 -->
          <div class="input-actions-bottom">
            <!-- 附件状态按钮 -->
            <div
              v-if="threadAttachments.length > 0 || currentAttachments.length > 0"
              class="attachment-status-btn"
              :class="{ active: isAttachmentPanelOpen }"
              @click="toggleAttachmentPanel"
            >
              <FileText :size="16" />
              <span>附件 ({{ (threadAttachments?.length || 0) + (currentAttachments?.length || 0) }})</span>
            </div>
            <!-- 图片预览 -->
            <div v-if="currentImage" class="image-preview-wrapper">
              <ImagePreviewComponent
                :image-data="currentImage"
                @remove="currentImage = null"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧边栏 -->
      <div class="chat-sidebar">
        <div class="sidebar-header">
          <span class="clock-icon">🕐</span>
          <h3 class="sidebar-title">最近对话</h3>
        </div>
        <p class="sidebar-hint">
          最近的对话记录会显示在这里
        </p>
        <div class="conversation-list">
          <!-- 加载状态 -->
          <div v-if="isLoadingThreads" class="empty-conversations">
            <p>加载中...</p>
          </div>
          <!-- 对话列表 -->
          <template v-else-if="Object.keys(groupedChats).length > 0">
            <div v-for="(group, groupName) in groupedChats" :key="groupName" class="chat-group">
              <div class="chat-group-title">{{ groupName }}</div>
              <div
                v-for="chat in group.filter(c => c.title && c.title !== '新的对话' || currentThreadId === c.id)"
                :key="chat.id"
                class="conversation-item"
                :class="{ active: currentThreadId === chat.id }"
                @click="selectChat(chat)"
              >
                <div class="conversation-title">
                  {{ chat.title || '新的对话' }}
                </div>
              </div>
            </div>
          </template>
          <!-- 空状态 -->
          <div v-else class="empty-conversations">
            <p>暂无对话记录</p>
          </div>
        </div>

        <!-- 添加对话按钮（右下角） -->
        <button class="new-chat-floating-btn" @click="createNewChat" title="添加对话">
          <Plus :size="20" />
          <span>添加对话</span>
        </button>
      </div>
    </div>

    <!-- 智能体选择弹窗 -->
    <a-modal
      v-model:open="agentModalOpen"
      title="选择智能体"
      :width="800"
      :footer="null"
      :maskClosable="true"
      class="agent-modal"
    >
      <div class="agent-modal-content">
        <div class="agents-grid">
          <div
            v-for="agent in agents"
            :key="agent.id"
            class="agent-card"
            :class="{ selected: agent.id === selectedAgentId }"
            @click="selectAgentFromModal(agent.id)"
          >
            <div class="agent-card-header">
              <div class="agent-card-title">
                <Bot :size="20" class="agent-logo" />
                <span class="agent-card-name">{{ agent.name || 'Unknown' }}</span>
              </div>
              <template v-if="userStore.isAdmin">
                <StarFilled v-if="agent.id === defaultAgentId" class="default-icon" />
                <StarOutlined
                  v-else
                  @click.prevent="setAsDefaultAgent(agent.id)"
                  class="default-icon"
                />
              </template>
            </div>

            <div class="agent-card-description">
              {{ agent.description || '' }}
            </div>
          </div>
        </div>
      </div>
    </a-modal>

    <!-- 附件面板（右侧） -->
    <div v-if="isAttachmentPanelOpen" class="attachment-panel">
      <div class="panel-header">
        <div class="panel-title">附件</div>
        <div class="header-actions">
          <button class="close-btn" @click="isAttachmentPanelOpen = false">
            <X :size="18" />
          </button>
        </div>
      </div>
      
      <div class="panel-content">
        <div class="list-header" v-if="threadAttachments.length > 0">
          <div class="list-header-left">
            <span class="count">{{ threadAttachments.length }} 个附件</span>
            <a-tooltip title="支持 txt/md/docx/html 格式 ≤ 5 MB">
              <Info :size="14" class="info-icon" />
            </a-tooltip>
          </div>
          <button class="add-btn" @click="triggerAttachmentUpload" :disabled="isLoadingAttachments">
            <Plus :size="16" />
            <span>添加</span>
          </button>
        </div>
        
        <div v-if="!threadAttachments.length && !isLoadingAttachments" class="empty">
          <p>暂无附件</p>
          <a-button type="primary" @click="triggerAttachmentUpload">上传附件</a-button>
        </div>
        
        <div v-if="isLoadingAttachments" class="loading">
          <a-spin />
          <span>加载中...</span>
        </div>
        
        <div v-else-if="threadAttachments.length > 0" class="file-list">
          <div
            v-for="attachment in threadAttachments"
            :key="attachment.file_id"
            class="file-item"
          >
            <div class="file-info">
              <div class="file-icon-wrapper">
                <FileText :size="18" :style="{ color: '#1890ff' }" />
              </div>
              <div class="file-content-wrapper">
                <div class="file-name">{{ attachment.file_name }}</div>
                <div class="file-meta">
                  <span class="file-time" v-if="attachment.uploaded_at">
                    {{ formatAttachmentDate(attachment.uploaded_at) }}
                  </span>
                  <span class="file-size" v-if="attachment.file_size">
                    {{ formatFileSize(attachment.file_size) }}
                  </span>
                </div>
              </div>
              <div class="file-actions">
                <button class="download-btn" @click.stop="downloadAttachment(attachment)" title="下载附件">
                  <Download :size="18" />
                </button>
                <button class="delete-btn" @click.stop="deleteThreadAttachment(attachment.file_id)" title="删除附件">
                  <Trash2 :size="18" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 隐藏的文件输入 -->
      <input
        ref="attachmentPanelFileInputRef"
        type="file"
        multiple
        accept=".txt,.md,.docx,.html,.htm"
        style="display: none"
        @change="handleAttachmentPanelFileChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, reactive, nextTick } from 'vue'
import { useAgentStore } from '@/stores/agent'
import { useChatUIStore } from '@/stores/chatUI'
import { useUserStore } from '@/stores/user'
import { storeToRefs } from 'pinia'
import { threadApi, agentApi, multimodalApi } from '@/apis'
import { MessageProcessor } from '@/utils/messageProcessor'
import dayjs, { parseToShanghai } from '@/utils/time'
import AgentMessageComponent from '@/components/AgentMessageComponent.vue'
import ImagePreviewComponent from '@/components/ImagePreviewComponent.vue'
import { Hand, FileText, Image, X, Plus, Download, Trash2, Info, Square, Bot } from 'lucide-vue-next'
import { StarFilled, StarOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { handleChatError } from '@/utils/errorHandler'
import { formatFileSize } from '@/utils/file_utils'
import { useAgentStreamHandler } from '@/composables/useAgentStreamHandler'

const agentStore = useAgentStore()
const chatUIStore = useChatUIStore()
const userStore = useUserStore()

// 从 agentStore 中获取响应式状态
const {
  agents,
  selectedAgentId,
  defaultAgentId
} = storeToRefs(agentStore)

// 智能体选择弹窗状态
const agentModalOpen = computed({
  get: () => chatUIStore.agentModalOpen,
  set: (value) => {
    chatUIStore.agentModalOpen = value
  }
})

// 当前智能体名称
const currentAgentName = computed(() => {
  if (!selectedAgentId.value || !agents.value || !agents.value.length) return '大模型名称'
  const agent = agents.value.find((a) => a.id === selectedAgentId.value)
  return agent ? agent.name : '大模型名称'
})

const inputText = ref('')

// 对话线程列表
const threads = ref([])
const isLoadingThreads = ref(false)
const currentThreadId = ref(null)

// 对话消息列表（历史消息）
const threadMessages = ref({})

// 流式消息状态管理
const createOnGoingConvState = () => ({
  msgChunks: {},
  currentRequestKey: null,
  currentAssistantKey: null,
  toolCallBuffers: {}
})

// 线程状态管理
const threadStates = reactive({})

// 获取线程状态
const getThreadState = (threadId) => {
  if (!threadId) return null
  if (!threadStates[threadId]) {
    threadStates[threadId] = {
      onGoingConv: createOnGoingConvState(),
      isStreaming: false,
      streamAbortController: null,
      agentState: null
    }
  }
  return threadStates[threadId]
}

// 重置进行中的对话
const resetOnGoingConv = (threadId) => {
  const threadState = getThreadState(threadId)
  if (threadState) {
    threadState.onGoingConv = createOnGoingConvState()
  }
}

// 当前线程的历史消息
const currentThreadMessages = computed(() => {
  return threadMessages.value[currentThreadId.value] || []
})

// 进行中的流式消息
const onGoingConvMessages = computed(() => {
  const threadState = getThreadState(currentThreadId.value)
  if (!threadState || !threadState.onGoingConv) return []

  const msgs = Object.values(threadState.onGoingConv.msgChunks).map(
    MessageProcessor.mergeMessageChunk
  )
  return msgs.length > 0
    ? MessageProcessor.convertToolResultToMessages(msgs).filter((msg) => msg.type !== 'tool')
    : []
})

// 历史对话
const historyConversations = computed(() => {
  return MessageProcessor.convertServerHistoryToMessages(currentThreadMessages.value)
})

// 合并历史消息和流式消息
const conversations = computed(() => {
  const historyConvs = historyConversations.value

  // 如果有进行中的消息且线程状态显示正在流式处理，添加进行中的对话
  if (onGoingConvMessages.value.length > 0) {
    const onGoingConv = {
      messages: onGoingConvMessages.value,
      status: 'streaming'
    }
    return [...historyConvs, onGoingConv]
  }
  return historyConvs
})

// 文件上传相关
const fileInputRef = ref(null)
const imageInputRef = ref(null)
const currentImage = ref(null)
const currentAttachments = ref([]) // 待发送的附件列表（本地文件）
// isProcessing 改为 computed，见下方

// 附件面板相关
const isAttachmentPanelOpen = ref(false)
const threadAttachments = ref([]) // 线程中的附件列表（已上传）
const isLoadingAttachments = ref(false)
const attachmentPanelFileInputRef = ref(null)

// 根据时间获取问候语
const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 12) {
    return '上午好'
  } else if (hour < 18) {
    return '下午好'
  } else {
    return '晚上好'
  }
})

// 欢迎区域随机建议问题
const suggestionPool = [
'电网建业、电力保供、市场化改革相关保障策略和机制','电网法律合规核心业务中制度建设与管理中相关管理规范及标准'
]

const randomSuggestions = ref([])

const pickRandomSuggestions = () => {
  const pool = [...suggestionPool]
  // 简单洗牌
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j], pool[i]]
  }
  randomSuggestions.value = pool.slice(0, 2)
}

// 初始化随机建议
pickRandomSuggestions()

// 分组对话列表（今天、七天内、三十天内）
const groupedChats = computed(() => {
  const groups = {
    今天: [],
    七天内: [],
    三十天内: []
  }

  // 确保使用北京时间进行比较
  const now = dayjs().tz('Asia/Shanghai')
  const today = now.startOf('day')
  const sevenDaysAgo = now.subtract(7, 'day').startOf('day')
  const thirtyDaysAgo = now.subtract(30, 'day').startOf('day')

  // Sort chats by creation date, newest first
  const sortedChats = [...threads.value].sort((a, b) => {
    const dateA = parseToShanghai(b.created_at)
    const dateB = parseToShanghai(a.created_at)
    if (!dateA || !dateB) return 0
    return dateA.diff(dateB)
  })

  sortedChats.forEach((chat) => {
    // 将后端时间当作UTC时间处理，然后转换为北京时间
    const chatDate = parseToShanghai(chat.created_at)
    if (!chatDate) {
      return
    }
    if (chatDate.isAfter(today) || chatDate.isSame(today, 'day')) {
      groups['今天'].push(chat)
    } else if (chatDate.isAfter(sevenDaysAgo)) {
      groups['七天内'].push(chat)
    } else if (chatDate.isAfter(thirtyDaysAgo)) {
      groups['三十天内'].push(chat)
    } else {
      const monthKey = chatDate.format('YYYY-MM')
      if (!groups[monthKey]) {
        groups[monthKey] = []
      }
      groups[monthKey].push(chat)
    }
  })

  // Remove empty groups
  for (const key in groups) {
    if (groups[key].length === 0) {
      delete groups[key]
    }
  }

  return groups
})

// 获取对话线程列表
const fetchThreads = async (agentId = null) => {
  const targetAgentId = agentId || selectedAgentId.value
  if (!targetAgentId) return

  isLoadingThreads.value = true
  try {
    const fetchedThreads = await threadApi.getThreads(targetAgentId)
    threads.value = fetchedThreads || []
  } catch (error) {
    console.error('Failed to fetch threads:', error)
  } finally {
    isLoadingThreads.value = false
  }
}

// 获取线程消息
const fetchThreadMessages = async (agentId, threadId, delay = 0) => {
  if (!threadId || !agentId) return

  if (delay > 0) {
    await new Promise((resolve) => setTimeout(resolve, delay))
  }

  try {
    const response = await agentApi.getAgentHistory(agentId, threadId)
    const serverHistory = response.history || []
    // 保存到threadMessages中
    threadMessages.value[threadId] = serverHistory
    
    // 如果附件面板打开，刷新附件列表
    if (isAttachmentPanelOpen.value) {
      await fetchThreadAttachments(threadId)
    }
  } catch (error) {
    console.error('Failed to fetch thread messages:', error)
    threadMessages.value[threadId] = []
  }
}

// 选择对话
const selectChat = async (chat) => {
  if (!selectedAgentId.value) return
  
  // 中断之前线程的流式输出（如果存在）
  const previousThreadId = currentThreadId.value
  if (previousThreadId && previousThreadId !== chat.id) {
    const previousThreadState = getThreadState(previousThreadId)
    if (previousThreadState?.isStreaming && previousThreadState.streamAbortController) {
      previousThreadState.streamAbortController.abort()
      previousThreadState.isStreaming = false
      previousThreadState.streamAbortController = null
    }
  }
  
  currentThreadId.value = chat.id
  chatUIStore.isLoadingMessages = true
  try {
    await fetchThreadMessages(selectedAgentId.value, chat.id)
  } catch (error) {
    handleChatError(error, 'load')
  } finally {
    chatUIStore.isLoadingMessages = false
  }
  
  await nextTick()
  scrollToBottom()
}

// 监听线程变化，刷新附件列表
watch(currentThreadId, async (newThreadId) => {
  if (newThreadId && isAttachmentPanelOpen.value) {
    await fetchThreadAttachments(newThreadId)
  } else if (!newThreadId) {
    threadAttachments.value = []
  }
})

// 监听智能体变化，重新加载对话列表
watch(selectedAgentId, async (newAgentId) => {
  if (newAgentId) {
    await fetchThreads(newAgentId)
    // 清空当前对话
    currentThreadId.value = null
    conversations.value = []
    threadAttachments.value = []
  } else {
    threads.value = []
    currentThreadId.value = null
    conversations.value = []
    threadAttachments.value = []
  }
})

// 处理建议按钮点击
const handleSuggestionClick = (text) => {
  inputText.value = text
  // 这里可以触发发送
  console.log('建议内容:', text)
}

// 打开智能体选择弹窗
const openAgentModal = () => {
  chatUIStore.agentModalOpen = true
}

// 从弹窗中选择智能体
const selectAgentFromModal = async (agentId) => {
  try {
    await agentStore.selectAgent(agentId)
    chatUIStore.agentModalOpen = false
    // 选择智能体后，重新加载对话列表
    await fetchThreads(agentId)
    // 清空当前对话
    currentThreadId.value = null
    conversations.value = []
  } catch (error) {
    console.error('选择智能体失败:', error)
    message.error('选择智能体失败')
  }
}

// 设置默认智能体
const setAsDefaultAgent = async (agentId) => {
  if (!agentId || !userStore.isAdmin) return

  try {
    await agentStore.setDefaultAgent(agentId)
    message.success('已设置为默认智能体')
  } catch (error) {
    console.error('设置默认智能体失败:', error)
    message.error(error.message || '设置默认智能体失败')
  }
}

// 确保有活动的线程
const ensureActiveThread = async (preferredTitle = '新的对话') => {
  if (currentThreadId.value) {
    return currentThreadId.value
  }

  if (!selectedAgentId.value) {
    message.warning('请先选择智能体')
    return null
  }

  try {
    const thread = await threadApi.createThread(selectedAgentId.value, preferredTitle)
    if (thread) {
      currentThreadId.value = thread.id
      threads.value.unshift(thread)
      threadMessages.value[thread.id] = []
      return thread.id
    }
    return null
  } catch (error) {
    console.error('创建线程失败:', error)
    message.error('创建对话失败')
    return null
  }
}

// 显式创建一个全新的对话（点击“新建对话”按钮时使用）
const createNewChat = async () => {
  if (!selectedAgentId.value) {
    message.warning('请先选择智能体')
    return
  }

  try {
    const thread = await threadApi.createThread(selectedAgentId.value, '新的对话')
    if (thread) {
      // 确保新对话有created_at字段（如果后端没有返回，使用当前时间）
      if (!thread.created_at) {
        thread.created_at = new Date().toISOString()
      }
      // 将新对话放到列表最前面
      threads.value.unshift(thread)
      currentThreadId.value = thread.id
      // 清空当前对话内容与附件
      conversations.value = []
      currentImage.value = null
      currentAttachments.value = []
      threadAttachments.value = []
    }
  } catch (error) {
    console.error('创建新对话失败:', error)
    message.error('创建新对话失败')
  }
}

// 处理文件选择（上传到线程并保存到列表）
const handleFileChange = async (event) => {
  const files = event.target.files
  if (!files || files.length === 0) return

  if (!selectedAgentId.value) {
    message.error('请先选择智能体')
    event.target.value = ''
    return
  }

  // 验证文件大小和类型
  const maxSize = 5 * 1024 * 1024 // 5MB
  const allowedTypes = ['.txt', '.md', '.docx', '.html', '.htm']
  
  // 确保有线程
  let threadId = currentThreadId.value
  if (!threadId) {
    const preferredTitle = files[0]?.name || '新的对话'
    threadId = await ensureActiveThread(preferredTitle)
    if (!threadId) {
      message.error('创建对话失败，无法上传附件')
      event.target.value = ''
      return
    }
  }

  // 上传文件
  for (const file of Array.from(files)) {
    // 检查文件大小
    if (file.size > maxSize) {
      message.error(`${file.name} 文件过大，请选择小于5MB的文件`)
      continue
    }
    
    // 检查文件类型
    const fileExt = '.' + file.name.split('.').pop().toLowerCase()
    if (!allowedTypes.includes(fileExt)) {
      message.error(`${file.name} 文件类型不支持，仅支持 txt/md/docx/html 格式`)
      continue
    }
    
    try {
      // 上传附件到线程
      const response = await threadApi.uploadThreadAttachment(threadId, file)
      message.success(`${file.name} 上传成功`)
      
      // 保存附件信息（从响应中获取file_id等信息）
      const attachmentInfo = {
        file_id: response?.file_id || response?.id || Date.now().toString(),
        file_name: file.name,
        file_size: file.size,
        uploaded_at: new Date().toISOString(),
        file: file // 保留原始文件对象，用于发送消息时使用
      }
      
      // 如果附件面板打开，刷新列表；否则直接添加
      if (isAttachmentPanelOpen.value) {
        await fetchThreadAttachments(threadId)
      } else {
        threadAttachments.value.push(attachmentInfo)
      }
    } catch (error) {
      console.error('上传附件失败:', error)
      handleChatError(error, '上传附件')
    }
  }

  // 清空文件输入
  event.target.value = ''
}

// 处理图片上传
const handleImageChange = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return

  if (!selectedAgentId.value) {
    message.warning('请先选择智能体')
    return
  }

  // 验证文件大小（10MB）
  if (file.size > 10 * 1024 * 1024) {
    message.error('图片文件过大，请选择小于10MB的图片')
    return
  }

  // 验证文件类型
  if (!file.type.startsWith('image/')) {
    message.error('请选择有效的图片文件')
    return
  }

  try {
    message.loading({ content: '正在处理图片...', key: 'image-upload' })

    const result = await multimodalApi.uploadImage(file)

    if (result.success) {
      message.success({
        content: '图片处理成功',
        key: 'image-upload',
        duration: 2
      })

      // 保存图片数据，发送消息时使用
      currentImage.value = {
        success: true,
        imageContent: result.image_content,
        thumbnailContent: result.thumbnail_content,
        width: result.width,
        height: result.height,
        format: result.format,
        mimeType: result.mime_type || file.type,
        sizeBytes: result.size_bytes,
        originalName: file.name
      }
    } else {
      message.error({
        content: `图片处理失败: ${result.error}`,
        key: 'image-upload'
      })
    }
  } catch (error) {
    console.error('图片上传失败:', error)
    message.error({
      content: `图片上传失败: ${error.message || '未知错误'}`,
      key: 'image-upload'
    })
  }

  // 清空文件输入
  event.target.value = ''
}

// 发送消息
const sendMessage = async ({ agentId, threadId, text, imageData, attachments, signal }) => {
  // 如果是新对话，用消息内容作为标题
  if ((conversations.value || []).length === 0) {
    try {
      await threadApi.updateThread(threadId, text)
    } catch (error) {
      console.error('更新线程标题失败:', error)
    }
  }

  // 先上传附件到线程
  if (attachments && attachments.length > 0) {
    try {
      for (const attachment of attachments) {
        await threadApi.uploadThreadAttachment(threadId, attachment.file)
      }
    } catch (error) {
      console.error('上传附件失败:', error)
      handleChatError(error, 'upload')
      throw error
    }
  }

  const requestData = {
    query: text,
    config: {
      thread_id: threadId
    }
  }

  // 如果有图片，添加到请求中
  if (imageData && imageData.imageContent) {
    requestData.image_content = imageData.imageContent
  }

  try {
    return await agentApi.sendAgentMessage(agentId, requestData, signal ? { signal } : undefined)
  } catch (error) {
    console.error('发送消息失败:', error)
    handleChatError(error, 'send')
    throw error
  }
}

// 发送或中断
const handleSendOrStop = async () => {
  const threadId = currentThreadId.value
  const threadState = getThreadState(threadId)
  
  // 如果正在流式处理，中断它
  if (isProcessing.value && threadState && threadState.streamAbortController) {
    threadState.streamAbortController.abort()
    
    // 中断后刷新消息历史，确保显示最新的状态
    try {
      await fetchThreadMessages(selectedAgentId.value, threadId, 500)
      message.info('已中断对话生成')
    } catch (error) {
      console.error('刷新消息历史失败:', error)
      message.info('已中断对话生成')
    }
    return
  }
  
  // 否则执行发送
  await handleSend()
}

// 处理发送
const handleSend = async () => {
  const text = inputText.value.trim()
  if ((!text && !currentImage.value && currentAttachments.value.length === 0) || !selectedAgentId.value) {
    return
  }

  let threadId = currentThreadId.value
  if (!threadId) {
    threadId = await ensureActiveThread(text || '新的对话')
    if (!threadId) {
      message.error('创建对话失败，请重试')
      return
    }
  }

  inputText.value = ''
  const imageData = currentImage.value
  const attachments = [...currentAttachments.value]
  currentImage.value = null
  currentAttachments.value = []

  // 滚动到底部
  scrollToBottom()

  const threadStateForSend = getThreadState(threadId)
  if (!threadStateForSend) return

  threadStateForSend.isStreaming = true
  resetOnGoingConv(threadId)
  threadStateForSend.streamAbortController = new AbortController()

  try {
    const response = await sendMessage({
      agentId: selectedAgentId.value,
      threadId: threadId,
      text: text,
      imageData: imageData,
      attachments: attachments,
      signal: threadStateForSend.streamAbortController?.signal
    })

    // 处理流式响应
    if (response && response.body) {
      await handleAgentResponse(response, threadId)
    } else {
      // 非流式响应，直接刷新消息
      await fetchThreadMessages(selectedAgentId.value, threadId)
    }
  } catch (error) {
    if (error.name !== 'AbortError') {
      // 如果发送失败，恢复附件列表
      if (attachments.length > 0) {
        currentAttachments.value = attachments
      }
      if (imageData) {
        currentImage.value = imageData
      }
      handleChatError(error, 'send')
    }
    threadStateForSend.isStreaming = false
  } finally {
    threadStateForSend.streamAbortController = null
    // 异步加载历史记录，保持当前消息显示直到历史记录加载完成
    fetchThreadMessages(selectedAgentId.value, threadId, 500).finally(() => {
      // 历史记录加载完成后，安全地清空当前进行中的对话
      resetOnGoingConv(threadId)
      scrollToBottom()
    })
  }
}

// 计算是否正在处理
const isProcessing = computed(() => {
  const threadState = getThreadState(currentThreadId.value)
  return threadState ? threadState.isStreaming : false
})

// 移除待发送的附件
const removeAttachment = (attachmentId) => {
  currentAttachments.value = currentAttachments.value.filter(att => att.id !== attachmentId)
}

// 获取线程附件列表
const fetchThreadAttachments = async (threadId) => {
  if (!threadId) {
    threadAttachments.value = []
    return
  }
  
  isLoadingAttachments.value = true
  try {
    const attachments = await threadApi.getThreadAttachments(threadId)
    // 确保返回的是数组
    if (Array.isArray(attachments)) {
      threadAttachments.value = attachments
    } else if (attachments && Array.isArray(attachments.data)) {
      threadAttachments.value = attachments.data
    } else {
      threadAttachments.value = []
    }
  } catch (error) {
    console.error('获取附件列表失败:', error)
    threadAttachments.value = []
  } finally {
    isLoadingAttachments.value = false
  }
}

// 删除线程附件
const deleteThreadAttachment = async (fileId) => {
  if (!currentThreadId.value || !fileId) return
  
  try {
    await threadApi.deleteThreadAttachment(currentThreadId.value, fileId)
    message.success('删除成功')
    // 从列表中移除
    threadAttachments.value = threadAttachments.value.filter(att => att.file_id !== fileId)
    // 同时从待发送列表中移除
    currentAttachments.value = currentAttachments.value.filter(att => att.id !== fileId)
  } catch (error) {
    console.error('删除附件失败:', error)
    handleChatError(error, '删除附件')
  }
}

// 下载附件
const downloadAttachment = async (attachment) => {
  try {
    // 如果有文件对象，直接下载
    if (attachment.file) {
      const url = URL.createObjectURL(attachment.file)
      const link = document.createElement('a')
      link.href = url
      link.download = attachment.file_name || attachment.name
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } else {
      // 否则尝试从服务器下载
      message.warning('该附件无法下载')
    }
  } catch (error) {
    console.error('下载附件失败:', error)
    message.error('下载附件失败')
  }
}

// 触发附件上传（从附件面板）
const triggerAttachmentUpload = () => {
  if (attachmentPanelFileInputRef.value) {
    attachmentPanelFileInputRef.value.click()
  }
}

// 处理附件面板文件上传
const handleAttachmentPanelFileChange = async (event) => {
  const files = event.target.files
  if (!files || files.length === 0) return

  if (!selectedAgentId.value) {
    message.error('请先选择智能体')
    event.target.value = ''
    return
  }

  // 确保有线程
  let threadId = currentThreadId.value
  if (!threadId) {
    const preferredTitle = files[0]?.name || '新的对话'
    threadId = await ensureActiveThread(preferredTitle)
    if (!threadId) {
      message.error('创建对话失败，无法上传附件')
      event.target.value = ''
      return
    }
  }

  // 验证和上传文件
  const maxSize = 5 * 1024 * 1024 // 5MB
  const allowedTypes = ['.txt', '.md', '.docx', '.html', '.htm']
  
  for (const file of Array.from(files)) {
    if (file.size > maxSize) {
      message.error(`${file.name} 文件过大，请选择小于5MB的文件`)
      continue
    }
    
    const fileExt = '.' + file.name.split('.').pop().toLowerCase()
    if (!allowedTypes.includes(fileExt)) {
      message.error(`${file.name} 文件类型不支持，仅支持 txt/md/docx/html 格式`)
      continue
    }
    
    try {
      const response = await threadApi.uploadThreadAttachment(threadId, file)
      message.success(`${file.name} 上传成功`)
      
      const attachmentInfo = {
        file_id: response?.file_id || response?.id || Date.now().toString(),
        file_name: file.name,
        file_size: file.size,
        uploaded_at: new Date().toISOString(),
        file: file
      }
      
      // 直接本地添加到线程附件列表，避免依赖接口返回结构
      threadAttachments.value.push(attachmentInfo)
    } catch (error) {
      console.error('上传附件失败:', error)
      handleChatError(error, '上传附件')
    }
  }

  event.target.value = ''
}

// 切换附件面板
const toggleAttachmentPanel = () => {
  isAttachmentPanelOpen.value = !isAttachmentPanelOpen.value
  // 仅在首次打开且本地没有数据时，从接口拉取，避免把已有附件清空
  if (isAttachmentPanelOpen.value && currentThreadId.value && threadAttachments.value.length === 0) {
    fetchThreadAttachments(currentThreadId.value)
  }
}

// 格式化附件日期
const formatAttachmentDate = (dateString) => {
  if (!dateString) return ''
  try {
    const date = new Date(dateString)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch (error) {
    return dateString
  }
}

// 流式处理handler
const { handleAgentResponse } = useAgentStreamHandler({
  getThreadState,
  processApprovalInStream: () => false, // 对话页暂不支持审批
  currentAgentId: selectedAgentId,
  supportsTodo: computed(() => false),
  supportsFiles: computed(() => false)
})

// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    const messagesContainer = document.querySelector('.messages-container')
    if (messagesContainer) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight
    }
  })
}

// 处理流式响应
const handleStreamResponse = async (response, threadId) => {
  const threadState = getThreadState(threadId)
  if (!threadState) return

  threadState.isStreaming = true
  resetOnGoingConv(threadId)
  threadState.streamAbortController = new AbortController()

  try {
    await handleAgentResponse(response, threadId)
  } catch (error) {
    if (error.name !== 'AbortError') {
      console.error('Stream error:', error)
      handleChatError(error, 'send')
    }
    threadState.isStreaming = false
  } finally {
    threadState.streamAbortController = null
    // 异步加载历史记录，保持当前消息显示直到历史记录加载完成
    fetchThreadMessages(selectedAgentId.value, threadId, 500).finally(() => {
      // 历史记录加载完成后，安全地清空当前进行中的对话
      resetOnGoingConv(threadId)
      scrollToBottom()
    })
  }
}

// 监听线程变化，刷新附件列表
watch(currentThreadId, async (newThreadId) => {
  if (newThreadId && isAttachmentPanelOpen.value) {
    await fetchThreadAttachments(newThreadId)
  } else if (!newThreadId) {
    threadAttachments.value = []
  }
})

// 监听智能体变化
watch(selectedAgentId, async (newAgentId) => {
  if (newAgentId) {
    await fetchThreads(newAgentId)
  } else {
    threads.value = []
    currentThreadId.value = null
    threadMessages.value = {}
    threadAttachments.value = []
  }
})

// 初始化
onMounted(async () => {
  // 确保智能体列表已加载
  if (!agentStore.isInitialized) {
    await agentStore.initialize()
  }
  
  // 如果有选中的智能体，加载对话列表
  if (selectedAgentId.value) {
    await fetchThreads(selectedAgentId.value)
  }
})
</script>

<style lang="less" scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #ffffff;
}

// 顶部标签栏
.chat-header-tabs {
  display: flex;
  gap: 8px;
  padding: 16px 24px;
  border-bottom: 1px solid #f0f0f0;
  background: #ffffff;

  .tab-item {
    padding: 8px 20px;
    border-radius: 8px;
    background: #1890ff;
    color: #ffffff;
    font-size: 14px;
    font-weight: 500;
  }
}

// 主内容容器
.chat-main-container {
  display: flex;
  flex: 1;
  overflow: hidden;
}

// 左侧主内容区
.chat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.welcome-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  text-align: center;
  max-width: 600px;
  margin: 0 auto;
}

.welcome-emoji {
  font-size: 80px;
  margin-bottom: 24px;
  animation: wave 2s ease-in-out infinite;
}

@keyframes wave {
  0%, 100% {
    transform: rotate(0deg);
  }
  25% {
    transform: rotate(20deg);
  }
  75% {
    transform: rotate(-20deg);
  }
}

.welcome-greeting {
  font-size: 32px;
  font-weight: 600;
  color: #262626;
  margin: 0 0 16px 0;
}

.welcome-intro {
  font-size: 16px;
  color: #595959;
  margin: 0 0 32px 0;
  line-height: 1.6;
}

.suggested-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 32px;
}

.action-button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: #f5f5f5;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 14px;
  color: #262626;

  &:hover {
    background: #e8e8e8;
    transform: translateX(4px);
  }

  .arrow-icon {
    color: #8c8c8c;
    font-size: 18px;
  }
}

// 右侧边栏
.chat-sidebar {
  width: 320px;
  border-left: 1px solid #f0f0f0;
  background: #fafafa;
  display: flex;
  flex-direction: column;
  padding: 24px;
  overflow: hidden;
  flex-shrink: 0;
  position: relative;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;

  .clock-icon {
    font-size: 18px;
  }

  .sidebar-title {
    font-size: 16px;
    font-weight: 600;
    color: #262626;
    margin: 0;
  }
}

.sidebar-hint {
  font-size: 12px;
  color: #8c8c8c;
  line-height: 1.5;
  margin: 0 0 24px 0;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
}

.empty-conversations {
  text-align: center;
  padding: 40px 20px;
  color: #bfbfbf;
  font-size: 14px;
}

.chat-group {
  margin-bottom: 24px;

  .chat-group-title {
    font-size: 12px;
    color: #8c8c8c;
    margin-bottom: 8px;
    font-weight: 500;
  }
}

.conversation-item {
  padding: 12px 16px;
  margin-bottom: 4px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  background: #ffffff;
  border: 1px solid transparent;

  &:hover {
    background: #f5f5f5;
  }

  &.active {
    background: #e6f7ff;
    border-color: #1890ff;
  }

  .conversation-title {
    font-size: 14px;
    color: #262626;
    display: flex;
    align-items: center;
    gap: 6px;

    .new-dialog-plus {
      color: #8c8c8c;
      flex-shrink: 0;
      opacity: 0.6;
    }
  }
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  width: 100%;
  max-width: 1000px;
  margin: 0 auto;
  min-height: 0;
}

.conversation-wrapper {
  margin-bottom: 24px;
  display: flex;
  flex-direction: column;
}

// 底部输入区域包装器
.chat-input-wrapper {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 16px 24px;
  border-top: 1px solid #f0f0f0;
  background: #ffffff;
  flex-shrink: 0;
}

// 底部输入区域
.chat-input-area {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
}

.input-icons {
  display: flex;
  gap: 12px;
}

.input-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: #8c8c8c;
  cursor: pointer;
  transition: color 0.2s;

  &:hover {
    color: #1890ff;
  }
}

.chat-input {
  flex: 1;
  padding: 12px 16px;
  border: 1px solid #d9d9d9;
  border-radius: 24px;
  font-size: 14px;
  outline: none;
  transition: all 0.2s;

  &:focus {
    border-color: #1890ff;
    box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.1);
  }

  &::placeholder {
    color: #bfbfbf;
  }
}

.send-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #1890ff;
  color: #ffffff;
  border: none;
  cursor: pointer;
  transition: all 0.2s;

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &:not(:disabled):hover {
    background: #40a9ff;
  }

  &:hover:not(:disabled) {
    background: #40a9ff;
    transform: scale(1.05);
  }

  &:disabled {
    background: #d9d9d9;
    cursor: not-allowed;
  }
}

// 智能体选择弹窗样式
.agent-modal {
  :deep(.ant-modal-body) {
    padding: 24px;
    background: #fafafa;
  }

  :deep(.ant-modal-header) {
    padding: 20px 24px;
    border-bottom: 1px solid #f0f0f0;
  }

  :deep(.ant-modal-title) {
    font-size: 18px;
    font-weight: 600;
    color: #262626;
  }

  .agent-modal-content {
    .agents-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
      max-height: 600px;
      overflow-y: auto;
      padding: 4px 0;
    }

    .agent-card {
      border: 1.5px solid #e8e8e8;
      border-radius: 12px;
      padding: 20px;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      background: #ffffff;
      position: relative;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);

      &::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #1890ff, #40a9ff);
        transform: scaleX(0);
        transition: transform 0.3s ease;
      }

      &:hover {
        border-color: #1890ff;
        box-shadow: 0 8px 24px rgba(24, 144, 255, 0.25);
        transform: translateY(-4px);
        border-width: 2px;

        &::before {
          transform: scaleX(1);
        }
      }

      .agent-card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 14px;
        gap: 12px;

        .agent-card-title {
          flex: 1;
          min-width: 0;
          display: flex;
          align-items: center;
          gap: 10px;

          .agent-logo {
            color: #1890ff;
            flex-shrink: 0;
          }

          .agent-card-name {
            font-size: 16px;
            font-weight: 600;
            color: #262626;
            line-height: 1.5;
            margin: 0;
            word-break: break-word;
          }
        }

        .default-icon {
          color: #faad14;
          font-size: 18px;
          flex-shrink: 0;
          cursor: pointer;
          transition: all 0.2s;
          padding: 4px;

          &:hover {
            color: #d48806;
          }
        }
      }

      .agent-card-description {
        font-size: 14px;
        color: #595959;
        line-height: 1.6;
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
        margin: 0;
      }

      &.selected {
        border-color: #1890ff;
        border-width: 2px;
        background: linear-gradient(135deg, #e6f7ff 0%, #f0f9ff 100%);
        box-shadow: 0 6px 20px rgba(24, 144, 255, 0.3);

        &::before {
          transform: scaleX(1);
        }

        .agent-card-header .agent-card-title .agent-card-name {
          color: #1890ff;
        }

        .agent-card-description {
          color: #262626;
        }
      }
    }
  }
}

// 响应式适配智能体弹窗
@media (max-width: 768px) {
  .agent-modal {
    :deep(.ant-modal) {
      width: 95% !important;
      max-width: 95% !important;
    }

    .agent-modal-content {
      .agents-grid {
        grid-template-columns: 1fr;
        gap: 12px;
      }

      .agent-card {
        padding: 16px;
      }
    }
  }
}

@media (min-width: 769px) and (max-width: 1200px) {
  .agent-modal {
    .agent-modal-content {
      .agents-grid {
        grid-template-columns: repeat(2, 1fr);
        gap: 14px;
      }
    }
  }
}

.input-actions-bottom {
  margin-top: 12px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.attachment-status-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #f5f5f5;
  border-radius: 6px;
  font-size: 13px;
  color: #595959;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;

  &:hover {
    background: #e8e8e8;
    color: #1890ff;
  }

  &.active {
    background: #e6f7ff;
    color: #1890ff;
    border-color: #1890ff;
  }
}

.image-preview-wrapper {
  display: flex;
  justify-content: flex-start;
}

// 附件面板样式
.attachment-panel {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 400px;
  background: #ffffff;
  border-left: 1px solid #f0f0f0;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  z-index: 1000;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  height: 56px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.panel-title {
  font-weight: 600;
  font-size: 16px;
  color: #262626;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.close-btn {
  border: none;
  background: transparent;
  cursor: pointer;
  color: #8c8c8c;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover {
    background: #f5f5f5;
    color: #262626;
  }
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 0 4px;

  .list-header-left {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .count {
    font-size: 13px;
    color: #8c8c8c;
  }

  .info-icon {
    color: #bfbfbf;
    cursor: help;
    transition: color 0.2s;

    &:hover {
      color: #1890ff;
    }
  }

  .add-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    height: 28px;
    border: 1px solid #d9d9d9;
    border-radius: 6px;
    background: #ffffff;
    color: #595959;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;

    &:hover:not(:disabled) {
      background: #f5f5f5;
      color: #1890ff;
      border-color: #1890ff;
    }

    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  }
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
  color: #8c8c8c;

  p {
    margin-bottom: 16px;
    font-size: 14px;
  }
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 12px;
  color: #8c8c8c;
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-item {
  padding: 12px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  transition: all 0.15s ease;

  &:hover {
    background: #f5f5f5;
    border-color: #d9d9d9;
  }
}

.file-info {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.file-icon-wrapper {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.file-content-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.file-name {
  font-size: 14px;
  color: #262626;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #8c8c8c;
}

.file-time {
  white-space: nowrap;
}

.file-size {
  color: #bfbfbf;
}

.file-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.download-btn,
.delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: #8c8c8c;
  cursor: pointer;
  transition: all 0.15s ease;
  padding: 0;

  &:hover {
    background: #f5f5f5;
  }
}

.download-btn:hover {
  color: #1890ff;
}

.delete-btn:hover {
  color: #ff4d4f;
}

// 生成状态样式
.generating-status {
  padding: 16px 0;
  display: flex;
  justify-content: center;
  align-items: center;
}

.generating-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: #f5f5f5;
  border-radius: 8px;
}

.loading-dots {
  display: flex;
  gap: 4px;
  align-items: center;
}

.loading-dots div {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #1890ff;
  animation: loading-dot 1.4s infinite ease-in-out;
}

.loading-dots div:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots div:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes loading-dot {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.new-chat-floating-btn {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 32px;
  width: 80%;
  background: #1890ff;
  color: #ffffff;
  border: none;
  border-radius: 24px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(24, 144, 255, 0.3);
  z-index: 10;
  text-align: center;
  opacity: 0.8;

  span {
    text-align: center;
  }

  &:hover {
    background: #40a9ff;
    box-shadow: 0 6px 16px rgba(24, 144, 255, 0.4);
    transform: translateX(-50%) translateY(-2px);
  }

  &:active {
    transform: translateX(-50%) translateY(0);
  }
}

.generating-text {
  font-size: 14px;
  color: #8c8c8c;
}
</style>