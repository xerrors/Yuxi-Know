<template>
  <div class="chat-container">
    <div class="conversations" :class="{ 'is-open': state.isSidebarOpen }">
      <div class="actions">
        <span class="header-title">可用智能体</span>
        <div class="action close" @click="state.isSidebarOpen = false"><MenuOutlined /></div>
      </div>
      <div class="conversation-list">
        <div class="conversation"
          v-for="(agent, name) in agents"
          :key="name"
          :class="{ active: currentAgent?.name === name }"
          @click="selectAgent(name)">
          <div class="conversation__title"><RobotOutlined /> &nbsp;{{ agent.name }}</div>
          <div class="conversation__description">{{ agent.description }}</div>
        </div>
      </div>
    </div>
    <div class="chat">
      <div class="chat-header">
        <div class="header__left">
          <div
            v-if="!state.isSidebarOpen"
            class="nav-btn"
            @click="state.isSidebarOpen = true"
          >
            <MenuOutlined />
          </div>
          <a-dropdown>
            <div class="current-agent nav-btn">
              <RobotOutlined />&nbsp;
              <span v-if="currentAgent">{{ currentAgent.name }}</span>
              <span v-else>请选择智能体</span>
            </div>
            <template #overlay>
              <a-menu @click="({key}) => selectAgent(key)">
                <a-menu-item v-for="(agent, name) in agents" :key="name">
                  <RobotOutlined /> {{ agent.name }}
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
        <div class="header__right">
          <div class="nav-btn text" @click="state.isRightSidebarOpen = !state.isRightSidebarOpen">
            <SettingOutlined /> <span class="text">设置</span>
          </div>
        </div>
      </div>

      <div v-if="messages.length === 0" class="chat-examples">
        <h1>{{ currentAgent ? currentAgent.name : '请选择一个智能体开始对话' }}</h1>
        <p>{{ currentAgent ? currentAgent.description : '不同的智能体有不同的专长和能力' }}</p>
      </div>

      <div class="chat-box" ref="messagesContainer" :class="{ 'is-debug': options.debug_mode }">
        <div
          v-for="(message, index) in messages"
          :key="index"
          class="message-box"
          :class="message.role">
          <p v-if="message.role === 'user'" class="message-text">{{ message.content.trim() }}</p>
          <div v-else-if="message.role === 'assistant'" class="assistant-message" @click="handleAssistantClick(message)">
            <div v-if="options.debug_mode" class="status-info">{{ message }}</div>
            <div v-if="message.content" v-html="renderMarkdown(message.content)" class="message-md"></div>
            <div v-if="message.toolCalls && Object.keys(message.toolCalls).length > 0" class="tool-calls-container">
              <div v-for="(toolCall, index) in message.toolCalls || {}"
                   :key="index"
                   class="tool-call-container">
                <div v-if="toolCall" class="tool-call-display" :class="{ 'is-collapsed': !expandedToolCalls.has(toolCall.id) }">
                  <div class="tool-header" @click="toggleToolCall(toolCall.id)">
                    <span v-if="!toolCall.toolResultMsg">
                      <ThunderboltOutlined />
                      <span>正在调用工具: </span>
                      <span class="tool-name">{{ toolCall.function.name }}</span>
                    </span>
                    <span v-else>
                      <ThunderboltOutlined /> 工具 <span class="tool-name">{{ toolCall.function.name }}</span> 执行完成
                    </span>

                    <span class="step-badge" v-if="message.step !== undefined">步骤 {{ message.step }}</span>
                  </div>
                  <div class="tool-content" v-show="expandedToolCalls.has(toolCall.id)">
                    <div class="tool-params" v-if="toolCall.function && toolCall.function.arguments">
                      <div class="tool-params-header">
                        参数:
                      </div>
                      <div class="tool-params-content">
                        <pre>{{ toolCall.function.arguments }}</pre>
                      </div>
                    </div>
                    <div class="tool-params" v-if="toolCall.toolResultMsg && toolCall.toolResultMsg.content">
                      <div class="tool-params-header">
                        执行结果:
                      </div>
                      <div class="tool-params-content">{{ toolCall.toolResultMsg.content }}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else-if="isProcessing && (!message.content || message.content.length === 0)" class="loading-dots">
              <div></div>
              <div></div>
              <div></div>
            </div>
          </div>
          <div v-else-if="message.status === 'error'" class="err-msg" @click="retryMessage(index)">
            请求错误，请重试。{{ message.message }}
          </div>
        </div>
      </div>

      <div class="bottom">
        <div class="input-box">
          <div class="input-area">
            <a-textarea
              class="user-input"
              v-model:value="userInput"
              @keydown="handleKeyDown"
              placeholder="输入问题..."
              :disabled="!currentAgent || isProcessing"
              :auto-size="{ minRows: 2, maxRows: 6 }"
            />
          </div>
          <div class="input-options">
            <div class="options__right">
              <a-button size="large" @click="sendMessage" :disabled="!userInput || !currentAgent || isProcessing" type="link">
                <template #icon> <SendOutlined v-if="!isProcessing" /> <LoadingOutlined v-else/> </template>
              </a-button>
            </div>
          </div>
        </div>
        <p class="note">请注意辨别内容的可靠性</p>
      </div>
    </div>

    <!-- 右侧侧边栏 -->
    <div class="right-sidebar" :class="{ 'is-open': state.isRightSidebarOpen }">
      <div class="actions">
        <span class="header-title">设置选项</span>
        <div class="action close" @click="state.isRightSidebarOpen = false"><CloseOutlined /></div>
      </div>
      <div class="settings-container">
        <div class="settings-group">
          <div class="settings-title">基本设置</div>
          <div class="settings-item">
            <div class="settings-label">网络搜索</div>
            <a-switch v-model:checked="options.use_web" />
          </div>
        </div>

        <div class="settings-group">
          <div class="settings-title">高级设置</div>
          <div class="settings-item">
            <div class="settings-label">线程ID</div>
            <div class="thread-id-container">
              <div class="settings-value thread-id">{{ threadId || '未生成' }}</div>
              <a-button
                type="link"
                size="small"
                class="refresh-btn"
                @click="resetThread"
                :disabled="!threadId"
              >
                <ReloadOutlined />
              </a-button>
            </div>
          </div>
          <div class="settings-item">
            <div class="settings-label">显示调试信息</div>
            <a-switch v-model:checked="options.debug_mode" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch, nextTick } from 'vue';
import {
  MenuOutlined, RobotOutlined, SendOutlined, LoadingOutlined, SettingOutlined,
  CloseOutlined, ThunderboltOutlined, ReloadOutlined, CheckCircleOutlined,
  DownOutlined, RightOutlined,
} from '@ant-design/icons-vue';
import { Marked } from 'marked';
import { markedHighlight } from 'marked-highlight';
import { onClickOutside } from '@vueuse/core';
import 'highlight.js/styles/github.css';
import hljs from 'highlight.js';

// ==================== 初始化配置 ====================

// Markdown渲染配置
const marked = new Marked(
  { gfm: true, breaks: true, tables: true },
  markedHighlight({
    langPrefix: 'hljs language-',
    highlight(code) { return hljs.highlightAuto(code).value; }
  })
);

// ==================== 状态管理 ====================

// UI状态
const state = reactive({
  isSidebarOpen: true,
  isRightSidebarOpen: false,
  showOptions: false,
});

// 应用选项
const options = reactive({
  use_web: true,
  thread_id: null,
  debug_mode: false,
});

// DOM引用
const messagesContainer = ref(null);
const optionsPanel = ref(null);

// 数据状态
const agents = ref({});                // 智能体列表
const currentAgent = ref(null);        // 当前选中的智能体
const userInput = ref('');             // 用户输入
const messages = ref([]);              // 消息列表
const isProcessing = ref(false);       // 是否正在处理请求
const threadId = ref(null);            // 会话线程ID

// ==================== 步骤与状态跟踪 ====================

// 工具调用相关
const toolCalls = ref([]);             // 工具调用列表
const currentToolCallId = ref(null);   // 当前工具调用ID
const currentRunId = ref(null);        // 当前运行ID
const messageStepMap = ref({});        // 消息步骤映射
const expandedToolCalls = ref(new Set()); // 展开的工具调用集合

// ==================== 基础工具函数 ====================

// 渲染Markdown
const renderMarkdown = (text) => {
  if (!text) return '';
  return marked.parse(text);
};

// 滚动到底部
const scrollToBottom = async () => {
  await nextTick();
  if (!messagesContainer.value) return;

  const container = messagesContainer.value;
  const scrollOptions = { top: container.scrollHeight, behavior: 'smooth' };

  // 多次尝试滚动以确保成功
  container.scrollTo(scrollOptions);
  setTimeout(() => container.scrollTo(scrollOptions), 50);
  setTimeout(() => container.scrollTo(scrollOptions), 150);
  setTimeout(() => container.scrollTo({ top: container.scrollHeight, behavior: 'auto' }), 300);
};

// ==================== 状态管理函数 ====================

// 添加新的状态管理变量
const messageMap = ref(new Map()); // 存储消息ID与消息对象的映射
const toolCallMap = ref(new Map()); // 存储工具调用ID与对应消息ID的映射

// 重置状态
const resetStatusSteps = () => {
  toolCalls.value = [];
  currentToolCallId.value = null;
  currentRunId.value = null;
  messageStepMap.value = {};
  messageMap.value.clear();
  toolCallMap.value.clear();
};

// 重置线程
const resetThread = () => {
  threadId.value = null;
  messages.value = [];
  resetStatusSteps();
  saveState();
};

// ==================== 消息历史处理 ====================

// 过滤和准备消息历史记录
const prepareMessageHistory = (msgs) => {
  // 按步骤和运行ID建立索引
  const toolCallsByRunAndStep = {};
  const toolResultsByRunAndStep = {};

  // 收集所有工具调用
  msgs.filter(msg => msg.role === 'tool_call').forEach(msg => {
    const runId = msg.tool?.run_id || 'unknown';
    const step = msg.tool?.step !== undefined ? msg.tool.step : -1;
    const key = `${runId}:${step}`;
    toolCallsByRunAndStep[key] = msg;
  });

  // 收集所有工具结果
  msgs.filter(msg => msg.role === 'tool').forEach(msg => {
    const runId = msg.tool?.run_id || 'unknown';
    // 尝试使用工具调用步骤（如果可用）或当前步骤
    const step = msg.tool?.tool_call_step !== undefined ? msg.tool.tool_call_step :
                (msg.tool?.step !== undefined ? msg.tool.step - 1 : -1);
    const key = `${runId}:${step}`;
    toolResultsByRunAndStep[key] = msg;
  });

  // 构建有效的工具调用ID集合
  const validToolCallKeys = new Set();

  // 查找所有具有对应结果的工具调用
  for (const key in toolCallsByRunAndStep) {
    if (toolResultsByRunAndStep[`${key.split(':')[0]}:${parseInt(key.split(':')[1]) + 1}`] ||
        toolResultsByRunAndStep[key.replace(/:\d+$/, ':result')]) {
      validToolCallKeys.add(key);
    }
  }

  // 过滤消息
  return msgs.filter(msg => {
    // 保留用户和助手消息
    if (msg.role === 'user' || msg.role === 'assistant') return true;

    // 处理工具调用和结果
    if (msg.role === 'tool_call') {
      const runId = msg.tool?.run_id || 'unknown';
      const step = msg.tool?.step !== undefined ? msg.tool.step : -1;
      const key = `${runId}:${step}`;
      return validToolCallKeys.has(key);
    }

    if (msg.role === 'tool') {
      const runId = msg.tool?.run_id || 'unknown';
      const callStep = msg.tool?.tool_call_step !== undefined ? msg.tool.tool_call_step :
                    (msg.tool?.step !== undefined ? msg.tool.step - 1 : -1);
      const key = `${runId}:${callStep}`;
      return validToolCallKeys.has(key);
    }

    return false;
  });
};

// ==================== 用户交互处理 ====================

// 选择智能体
const selectAgent = (agentName) => {
  currentAgent.value = agents.value[agentName];
  messages.value = [];
  threadId.value = null;
  resetStatusSteps();
  saveState();
};

// 处理键盘事件
const handleKeyDown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    // 只有在满足条件时才发送
    if (userInput.value.trim() && currentAgent.value && !isProcessing.value) {
      const tempUserInput = userInput.value;
      userInput.value = ''; // 立即清空输入框
      // 使用异步调用确保清空先发生
      setTimeout(() => {
        sendMessageWithText(tempUserInput);
      }, 0);
    }
  }
};

// 发送消息
const sendMessage = () => {
  if (!userInput.value || !currentAgent.value || isProcessing.value) return;
  const tempUserInput = userInput.value;
  userInput.value = ''; // 立即清空输入框
  // 确保UI更新后再发送消息
  nextTick(() => {
    sendMessageWithText(tempUserInput);
  });
};

// 重试消息
const retryMessage = (index) => {
  // 获取用户消息
  const userMessage = messages.value[index - 1]?.content;
  if (!userMessage) return;

  // 删除错误消息和对应的用户消息
  messages.value = messages.value.slice(0, index - 1);

  // 重新发送消息
  sendMessageWithText(userMessage);
};

// ==================== 核心消息处理 ====================

// 使用文本发送消息
const sendMessageWithText = async (text) => {
  if (!text || !currentAgent.value || isProcessing.value) return;

  // 重置状态
  resetStatusSteps();

  const userMessage = text.trim();

  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: userMessage
  });

  // // 添加加载中的消息
  // messages.value.push({
  //   role: 'assistant',
  //   content: '',
  //   status: 'loading',
  //   toolCalls: {},
  //   toolCallIds: {}
  // });

  isProcessing.value = true;
  await scrollToBottom();

  try {
    // 准备历史消息
    const history = messages.value
      .filter(msg => msg.role !== 'assistant' || msg.status !== 'loading')
      .filter(msg => msg.role !== 'tool_call' && msg.role !== 'tool')
      .map(msg => ({
        role: msg.role === 'user' || msg.role === 'assistant' ? msg.role : 'assistant',
        content: msg.content
      }));

    // 设置请求参数
    const requestData = {
      query: userMessage,
      meta: {
        use_web: options.use_web,
        history_round: options.history_round
      },
      history: history.slice(0, -1), // 去掉最后一条刚添加的用户消息
      thread_id: threadId.value
    };

    // 发送请求
    const response = await fetch(`/api/chat/agent/${currentAgent.value.name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestData)
    });

    if (!response.ok) {
      throw new Error('请求失败');
    }

    // 处理流式响应
    await handleStreamResponse(response);

  } catch (error) {
    console.error('发送消息错误:', error);
    // 更新错误状态
    const loadingMsgIndex = messages.value.length - 1;
    if (loadingMsgIndex >= 0) {
      messages.value[loadingMsgIndex] = {
        role: 'assistant',
        content: `发生错误: ${error.message}`,
        status: 'error'
      };
    }
  } finally {
    isProcessing.value = false;
    await scrollToBottom();
  }
};

// 处理流式响应
const handleStreamResponse = async (response) => {
  const reader = response.body.getReader();
  // 创建一个初始的助手消息
  const assistantMsg = {
    role: 'assistant',
    content: '',
    status: 'loading',
    toolCalls: {},
    toolCallIds: {}
  };

  // 添加到消息列表
  messages.value.push(assistantMsg);
  await scrollToBottom();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const text = new TextDecoder().decode(value);
    const lines = text.split('\n').filter(line => line.trim());

    for (const line of lines) {
      try {
        const data = JSON.parse(line);

        // 处理元数据
        handleMetadata(data);

        // 基于消息ID处理消息
        if (data.msg?.id) {
          await handleMessageById(data);
        }

        // 处理完成状态
        if (data.status === 'finished') {
          await handleFinished(data);
        }
      } catch (error) {
        console.error('解析响应错误:', error);
      }
    }
  }
};

// 处理完成状态
const handleFinished = async () => {
  // 更新最后一条助手消息的状态
  const lastAssistantMsg = messages.value.find(m => m.role === 'assistant' && m.status === 'loading' || m.status === 'processing');
  if (lastAssistantMsg) {
    // 如果既没有内容也没有工具调用，添加一个完成提示
    if ((!lastAssistantMsg.content || lastAssistantMsg.content.trim().length === 0) &&
        (!lastAssistantMsg.toolCalls || Object.keys(lastAssistantMsg.toolCalls).length === 0)) {
      lastAssistantMsg.content = '已完成';
    }
    // 更新状态为已完成
    lastAssistantMsg.status = 'complete';
  }

  // 标记处理完成
  isProcessing.value = false;
  await scrollToBottom();
};

// 基于ID处理消息
const handleMessageById = async (data) => {
  const msgId = data.msg.id;
  const msgType = data.msg.type;
  // console.log("data", data);

  // 查找现有消息
  const existingMsgIndex = messageMap.value.get(msgId);
  // console.log("existingMsgIndex", existingMsgIndex);

  if (existingMsgIndex === undefined) {
    // 创建新消息或附加到现有助手消息
    if (msgType === 'tool') {
      await appendToolMessageToExistingAssistant(data);
    } else {
      // 查找是否有正在加载的助手消息
      const loadingAssistantIndex = messages.value.findIndex(m => m.role === 'assistant' && m.status === 'loading');
      if (loadingAssistantIndex !== -1) {
        // 更新现有助手消息
        messages.value[loadingAssistantIndex].id = msgId;
        messageMap.value.set(msgId, loadingAssistantIndex);
        await updateExistingMessage(data, loadingAssistantIndex);
      } else {
        // 创建新消息
        await createAssistantMessage(data);
      }
    }
  } else {
    // 更新现有消息
    await updateExistingMessage(data, existingMsgIndex);
  }
};

// 创建新的助手消息
const createAssistantMessage = async (data) => {
  // console.log("createAssistantMessage", data);
  const msgId = data.msg.id;
  const msgContent = data.response || '';
  const runId = data.metadata?.run_id;
  const step = data.metadata?.langgraph_step;

  // 创建新消息
  const newMsg = {
    id: msgId,
    role: 'assistant',
    content: msgContent,
    run_id: runId,
    step: step,
    status: 'processing',
    toolCalls: {},
    toolCallIds: {}
  };

  // 处理工具调用
  const toolCalls = data.msg.additional_kwargs?.tool_calls;
  if (toolCalls && toolCalls.length > 0) {
    // console.log("toolCalls in createAssistantMessage", toolCalls);
    for (const toolCall of toolCalls) {
      const toolCallId = toolCall.id;
      const toolIndex = toolCall.index || 0;
      newMsg.toolCallIds[toolCallId] = toolIndex;
      newMsg.toolCalls[toolIndex] = toolCall;
      toolCallMap.value.set(toolCallId, msgId);
    }
  }

  // 添加新消息
  messages.value.push(newMsg);
  const newIndex = messages.value.length - 1;
  messageMap.value.set(msgId, newIndex);

  await scrollToBottom();
};

// 更新现有消息
const updateExistingMessage = async (data, existingMsgIndex) => {
  const msgInstance = messages.value[existingMsgIndex];
  // console.log("updateExistingMessage", msgInstance);

  // 如果消息状态是loading，更新为processing
  if (msgInstance.status === 'loading') {
    msgInstance.status = 'processing';
    msgInstance.run_id = data.metadata?.run_id;
    msgInstance.step = data.metadata?.langgraph_step;
  }

  // 添加新的响应内容
  if (data.response) {
    msgInstance.content = msgInstance.content || '';
    msgInstance.content += data.response;
  }

  const toolCalls = data.msg.additional_kwargs?.tool_calls;
  if (toolCalls && toolCalls.length > 0) {
    // console.log("toolCalls in updateExistingMessage", toolCalls);
    for (const toolCall of toolCalls) {
      const toolIndex = toolCall.index || 0;

      // 创建临时对象
      const newToolCalls = { ...msgInstance.toolCalls };
      const newToolCallIds = { ...msgInstance.toolCallIds };
      if (!newToolCalls[toolIndex]) {
        newToolCalls[toolIndex] = toolCall;
        newToolCallIds[toolCall.id] = toolIndex;
      } else {
        newToolCalls[toolIndex]['function']['arguments'] += toolCall.function.arguments;
      }
      // 整体替换，触发响应式更新
      msgInstance.toolCalls = newToolCalls;
      msgInstance.toolCallIds = newToolCallIds;

      toolCallMap.value.set(toolCall.id, msgInstance.id);
    }
  }

  // 确保变更生效
  await nextTick();
  await scrollToBottom();
};

const handleAssistantClick = (message) => {
  console.log(message);
}

const appendToolMessageToExistingAssistant = async (data) => {
  // console.log("appendToolMessageToExistingAssistant", data);
  currentToolCallId.value = data.msg.tool_call_id;
  const assignedMsgId = toolCallMap.value.get(currentToolCallId.value);
  if (assignedMsgId === undefined) {
    console.error('未找到关联的消息实例', currentToolCallId.value);
    return;
  }

  // 获取消息索引
  const msgIndex = messageMap.value.get(assignedMsgId);
  if (msgIndex === undefined) {
    console.error('未找到关联的消息索引', assignedMsgId);
    return;
  }

  const msgInstance = messages.value[msgIndex];
  const toolCallIndex = msgInstance.toolCallIds[currentToolCallId.value];
  if (toolCallIndex === undefined) {
    console.error('未找到工具调用索引', currentToolCallId.value);
    return;
  }

  msgInstance.toolCalls[toolCallIndex].toolResultMsg = data.msg;
  msgInstance.toolCalls[toolCallIndex].toolResultMetadata = data.metadata;
  await scrollToBottom();
}

// ==================== 生命周期钩子 ====================

// 点击外部关闭选项面板
onClickOutside(optionsPanel, () => {
  state.showOptions = false;
});

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
    } else {
      console.error('获取智能体失败');
    }
  } catch (error) {
    console.error('获取智能体错误:', error);
  }
};

// 从localStorage加载状态
const loadState = () => {
  // 加载当前选择的智能体
  const savedAgent = localStorage.getItem('agent-current-agent');
  if (savedAgent && agents.value[savedAgent]) {
    currentAgent.value = agents.value[savedAgent];
  }

  // 加载设置选项
  const savedOptions = localStorage.getItem('agent-options');
  if (savedOptions) {
    Object.assign(options, JSON.parse(savedOptions));
  }

  // 加载消息历史
  const savedMessages = localStorage.getItem('agent-messages');
  if (savedMessages) {
    messages.value = JSON.parse(savedMessages);
  }

  // 加载线程ID
  const savedThreadId = localStorage.getItem('agent-thread-id');
  if (savedThreadId) {
    threadId.value = savedThreadId;
  }
};

// 保存状态到localStorage
const saveState = () => {
  // 保存当前选择的智能体
  if (currentAgent.value) {
    localStorage.setItem('agent-current-agent', currentAgent.value.name);
  }

  // 保存设置选项
  localStorage.setItem('agent-options', JSON.stringify(options));

  // 保存消息历史
  localStorage.setItem('agent-messages', JSON.stringify(messages.value));

  // 保存线程ID
  if (threadId.value) {
    localStorage.setItem('agent-thread-id', threadId.value);
  }
};

// 监听状态变化并保存
watch([currentAgent, options, messages, threadId], () => {
  saveState();
}, { deep: true });

// 组件挂载时加载状态
onMounted(async () => {
  // 获取智能体列表
  await fetchAgents();

  // 加载保存的状态
  loadState();

  // 处理消息历史
  if (messages.value.length > 0) {
    messages.value = prepareMessageHistory(messages.value);
  }

  // 从localStorage加载侧边栏状态
  const savedSidebarState = localStorage.getItem('agent-sidebar-open');
  if (savedSidebarState !== null) {
    state.isSidebarOpen = JSON.parse(savedSidebarState);
  }

  const savedRightSidebarState = localStorage.getItem('agent-right-sidebar-open');
  if (savedRightSidebarState !== null) {
    state.isRightSidebarOpen = JSON.parse(savedRightSidebarState);
  }
});

// 监听消息变化自动滚动
watch(messages, () => {
  scrollToBottom();
}, { deep: true });

// 处理元数据
const handleMetadata = (data) => {
  // 更新线程ID
  if (data.metadata?.thread_id && !threadId.value) {
    threadId.value = data.metadata.thread_id;
  }

  // 检查并更新运行ID
  if (data.metadata?.run_id && !currentRunId.value) {
    currentRunId.value = data.metadata.run_id;
  }

  // 跟踪步骤信息
  if (data.metadata?.langgraph_step !== undefined) {
    const step = data.metadata.langgraph_step;
    messageStepMap.value[step] = {
      type: data.msg?.type || 'unknown',
      timestamp: new Date().toISOString()
    };
  }
};

// 在 script setup 部分添加 toggleToolCall 方法
const toggleToolCall = (toolCallId) => {
  if (expandedToolCalls.value.has(toolCallId)) {
    expandedToolCalls.value.delete(toolCallId);
  } else {
    expandedToolCalls.value.add(toolCallId);
  }
};
</script>

<style lang="less" scoped>
@import '@/assets/main.css';

.chat-container {
  display: flex;
  width: 100%;
  height: 100%;
  position: relative;
}

.conversations {
  width: 230px;
  max-width: 230px;
  border-right: 1px solid var(--main-light-3);
  background-color: var(--bg-sider);
  transition: all 0.3s ease;
  white-space: nowrap; /* 防止文本换行 */
  overflow: hidden; /* 确保内容不溢出 */

  &.is-open {
    width: 230px;
  }

  &:not(.is-open) {
    width: 0;
    padding: 0;
    overflow: hidden;
  }

  & .actions {
    height: var(--header-height);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    z-index: 9;
    border-bottom: 1px solid var(--main-light-3);

    .header-title {
      font-weight: bold;
      user-select: none;
      white-space: nowrap;
      overflow: hidden;
    }

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
    flex-direction: column;
    padding: 16px;
    cursor: pointer;
    width: 100%;
    user-select: none;
    transition: background-color 0.2s ease-in-out;
    border-bottom: 1px solid var(--main-light-3);
    overflow: hidden;

    &__title {
      color: var(--gray-700);
      white-space: nowrap; /* 禁止换行 */
      overflow: hidden;    /* 超出部分隐藏 */
      text-overflow: ellipsis; /* 显示省略号 */
      font-weight: bold;
      margin-bottom: 4px;
    }

    &__description {
      color: var(--gray-600);
      font-size: 12px;
      white-space: normal;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    &.active {
      border-right: 3px solid var(--main-500);
      background-color: var(--main-light-4);

      & .conversation__title {
        color: var(--main-800);
      }
    }

    &:not(.active):hover {
      background-color: var(--main-light-3);
    }
  }
}

/* 右侧侧边栏样式 */
.right-sidebar {
  width: 350px;
  max-width: 350px;
  border-left: 1px solid var(--main-light-3);
  // background-color: var(--bg-sider);
  transition: all 0.3s ease;
  white-space: nowrap;
  overflow: hidden;

  &.is-open {
    width: 350px;
  }

  &:not(.is-open) {
    width: 0;
    padding: 0;
    overflow: hidden;
  }

  & .actions {
    height: var(--header-height);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    z-index: 9;
    border-bottom: 1px solid var(--main-light-3);

    .header-title {
      font-weight: bold;
      user-select: none;
      white-space: nowrap;
      overflow: hidden;
    }

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

  .settings-container {
    padding: 16px;
    overflow-y: auto;
  }

  .settings-group {
    margin-bottom: 20px;
  }

  .settings-title {
    font-weight: bold;
    margin-bottom: 12px;
    color: var(--gray-800);
    padding-bottom: 6px;
    border-bottom: 1px solid var(--main-light-3);
  }

  .settings-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
  }

  .settings-label {
    color: var(--gray-700);
  }

  .settings-value {
    color: var(--gray-600);
    font-size: 0.9em;
  }

  .thread-id-container {
    display: flex;
    align-items: center;
  }

  .settings-value.thread-id {
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .refresh-btn {
    padding: 0 8px;
    margin-left: 5px;
  }
}

.chat {
  position: relative;
  flex: 1;
  max-height: 100vh;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
  background: white;
  position: relative;
  box-sizing: border-box;
  overflow-y: scroll;

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
    padding: 1rem;
    border-bottom: 1px solid var(--main-light-3);

    .header__left, .header__right {
      display: flex;
      align-items: center;
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
    font-size: 1rem;
    width: auto;
    padding: 0.5rem 1rem;
    transition: background-color 0.3s;

    .text {
      margin-left: 10px;
    }

    &:hover {
      background-color: var(--main-light-3);
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
    font-size: 1.2rem;
    color: var(--gray-900);
  }

  p {
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

  .message-box {
    display: inline-block;
    border-radius: 1.5rem;
    margin: 0.8rem 0;
    padding: 0.625rem 1.25rem;
    user-select: text;
    word-break: break-word;
    font-size: 15px;
    box-sizing: border-box;
    color: black;

    .reasoning-box {
      margin-top: 10px;
      margin-bottom: 15px;
      border-radius: 8px;
      border: 1px solid var(--main-light-3);
      overflow: hidden;

      .reasoning-header {
        padding: 8px 12px;
        background-color: var(--main-50);
        font-size: 13px;
        color: var(--main-700);
        border-bottom: 1px solid var(--main-light-3);
        display: flex;
        align-items: center;
        gap: 6px;
      }

      .reasoning-content {
        padding: 10px 12px;
        font-size: 13px;
        color: var(--gray-700);
        white-space: pre-wrap;
        max-height: 200px;
        overflow-y: auto;
        background-color: white;
      }
    }

    .tool-call-box {
      margin: 10px 0 15px 0;
      border-radius: 8px;
      border: 1px solid var(--main-light-3);
      overflow: hidden;

      .tool-header {
        padding: 8px 12px;
        background-color: var(--gray-100);
        font-size: 13px;
        color: var(--gray-800);
        border-bottom: 1px solid var(--gray-200);
        display: flex;
        align-items: center;
        gap: 6px;
      }

      .tool-params {
        padding: 8px 12px;
        background-color: var(--gray-50);

        .tool-params-content,
        .tool-result-content,
        .tool-params-content pre {
          margin: 0;
          font-size: 12px;
          overflow-x: auto;
          white-space: pre-wrap;
          word-break: break-all;
        }
      }
    }
  }

  .message-box.user {
    line-height: 24px;
    max-width: 95%;
    background: var(--main-light-4);
    align-self: flex-end;
  }

  .message-box.assistant {
    color: initial;
    width: 100%;
    text-align: left;
    word-wrap: break-word;
    margin: 0 0 16px 0;
    padding-bottom: 0;
    padding-top: 10px;
    padding-left: 0;
    padding-right: 0;
    text-align: justify;
    background-color: white;
    border-radius: 12px;
    position: relative;
  }

  .tool-calls-container {
    width: 100%;
    margin-top: 10px;

    .tool-call-container {
      margin-bottom: 10px;

      &:last-child {
        margin-bottom: 0;
      }
    }
  }

  .tool-call-display {
    background-color: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 4px rgba(60, 60, 60, 0.05);
    animation: fadeInUp 0.3s ease-out;

    .tool-header {
      padding: 10px 12px;
      background-color: var(--gray-100);
      font-size: 14px;
      font-weight: 500;
      color: var(--gray-800);
      border-bottom: 1px solid var(--gray-200);
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      user-select: none;
      position: relative;

      .anticon {
        color: var(--main-600);
      }

      .step-badge {
        margin-left: auto;
        background-color: var(--gray-200);
        color: var(--gray-700);
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
      }
    }

    .tool-content {
      transition: all 0.3s ease;
      .tool-params {
        padding: 10px 12px;
        background-color: var(--gray-50);

        .tool-params-header {
          background-color: var(--gray-100);
          font-size: 13px;
          color: var(--gray-800);
        }

        .tool-params-content {
          margin: 0;
          font-size: 13px;
          background-color: var(--gray-100);
          border-radius: 4px;
          padding: 8px;
          overflow-x: auto;
        }
      }
    }

    &.is-collapsed {
      .tool-header {
        border-bottom: none;
      }
    }
  }

  p.message-text {
    max-width: 100%;
    word-wrap: break-word;
    margin-bottom: 0;
  }

  .err-msg {
    color: #ff4d4f;
    padding: 8px 12px;
    background-color: #fff2f0;
    border: 1px solid #ffccc7;
    border-radius: 8px;
    margin-top: 10px;
    cursor: pointer;

    &:hover {
      background-color: #fff0ed;
    }
  }
}

.chat-box.is-debug {
  .message-box .assistant-message {
    outline: 1px solid red;
    outline-offset: 10px;
    outline-style: dashed;

    .status-info {
      display: block;
      background-color: var(--gray-50);
      color: var(--gray-700);
      padding: 10px;
      border-radius: 8px;
      margin-bottom: 10px;
    }
  }
}

.bottom {
  position: sticky;
  bottom: 0;
  width: 100%;
  margin: 0 auto;
  padding: 4px 2rem 0 2rem;
  background: white;

  .input-box {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: auto;
    max-width: 800px;
    margin: 0 auto;
    padding: 0.25rem 0.5rem;
    border: 2px solid var(--gray-200);
    border-radius: 1rem;
    background: var(--gray-50);
    transition: background, border 0.3s, box-shadow 0.3s;

    &:focus-within {
      border: 2px solid var(--main-500);
      background: white;
    }

    .input-options {
      display: flex;
      padding: 4px 8px;
      justify-content: flex-end;
    }

    .input-area {
      display: flex;
      align-items: flex-end;
      gap: 8px;
    }

    .user-input {
      flex: 1;
      height: 40px;
      padding: 0.5rem 0.5rem;
      background-color: transparent;
      border: none;
      margin: 0;
      color: var(--gray-900);
      font-size: 16px;
      outline: none;
      resize: none;

      &:focus {
        outline: none;
        box-shadow: none;
      }

      &:active {
        outline: none;
      }
    }
  }

  button.ant-btn-icon-only {
    height: 32px;
    width: 32px;
    cursor: pointer;
    background-color: var(--main-color);
    border-radius: 50%;
    border: none;
    transition: color 0.3s;
    box-shadow: none;
    color: white;
    padding: 0;

    &:hover {
      background-color: var(--main-800);
    }

    &:disabled {
      background-color: var(--gray-400);
      cursor: not-allowed;
    }
  }

  .note {
    width: 100%;
    font-size: small;
    text-align: center;
    padding: 0rem;
    color: #ccc;
    margin: 4px 0;
    user-select: none;
  }
}

.conversation-list::-webkit-scrollbar,
.settings-container::-webkit-scrollbar {
  position: absolute;
  width: 4px;
  height: 4px;
}

.conversation-list::-webkit-scrollbar-track,
.settings-container::-webkit-scrollbar-track {
  background: transparent;
  border-radius: 4px;
}

.conversation-list::-webkit-scrollbar-thumb,
.settings-container::-webkit-scrollbar-thumb {
  background: var(--gray-400);
  border-radius: 4px;
}

.conversation-list::-webkit-scrollbar-thumb:hover,
.settings-container::-webkit-scrollbar-thumb:hover {
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
}

.loading-dots div {
  width: 8px;
  height: 8px;
  margin: 0 4px;
  background-color: var(--gray-700);
  border-radius: 50%;
  opacity: 0.3;
  animation: pulse 0.5s infinite ease-in-out both;
}

.loading-dots div:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots div:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes pulse {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.3;
  }
  40% {
    transform: scale(1);
    opacity: 1;
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

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

@media (max-width: 520px) {
  .conversations,
  .right-sidebar {
    position: absolute;
    z-index: 101;
    width: 300px;
    height: 100%;
    box-shadow: 0 0 10px 1px rgba(0, 0, 0, 0.05);
  }

  .conversations {
    border-radius: 0 16px 16px 0;
    left: 0;

    &:not(.is-open) {
      width: 0;
      padding: 0;
      overflow: hidden;
    }
  }

  .right-sidebar {
    border-radius: 16px 0 0 16px;
    right: 0;

    &:not(.is-open) {
      width: 0;
      padding: 0;
      overflow: hidden;
    }
  }

  .chat {
    height: calc(100vh - 60px);
  }

  .chat-box {
    padding: 1rem 1rem;
  }

  .bottom {
    padding: 0.5rem 0.5rem;

    .input-box {
      border-radius: 8px;
      padding: 0.5rem;
    }

    .note {
      display: none;
    }
  }
}
</style>
