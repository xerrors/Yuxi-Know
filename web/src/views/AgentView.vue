<template>
  <div class="chat-container">
    <div class="chat">
      <div class="chat-header">
        <div class="header__left">
          <a-dropdown v-if="!useSingleMode">
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
          <div v-else class="current-agent nav-btn">
            <RobotOutlined />&nbsp;
            <span v-if="currentAgent">{{ currentAgent.name }}</span>
            <span v-else>加载中...</span>
          </div>
        </div>
        <div class="header__right">
          <div class="newchat nav-btn" @click="resetThread" :disabled="isProcessing">
            <PlusCircleOutlined /> <span class="text">新对话</span>
          </div>
        </div>
      </div>

      <div v-if="messages.length === 0" class="chat-examples">
        <h1>{{ currentAgent ? currentAgent.name : '请选择一个智能体开始对话' }}</h1>
        <p>{{ currentAgent ? currentAgent.description : '不同的智能体有不同的专长和能力' }}</p>
      </div>

      <div class="chat-box" ref="messagesContainer" :class="{ 'is-debug': options.debug_mode }">
        <MessageComponent
          v-for="(message, index) in messages"
          :message="message"
          :key="index"
          :is-processing="isProcessing"
          @retry="retryMessage(index)"
        >
          <div v-if="options.debug_mode" class="status-info">{{ message }}</div>

          <!-- 工具调用 -->
          <template #tool-calls>
            <div v-if="message.toolCalls && Object.keys(message.toolCalls).length > 0" class="tool-calls-container">
              <div v-for="(toolCall, index) in message.toolCalls || {}"
                   :key="index"
                   class="tool-call-container">
                <div v-if="toolCall" class="tool-call-display" :class="{ 'is-collapsed': !expandedToolCalls.has(toolCall.id) }">
                  <div class="tool-header" @click="toggleToolCall(toolCall.id)">
                    <span v-if="!toolCall.toolResultMsg">
                      <LoadingOutlined /> &nbsp;
                      <span>正在调用工具: </span>
                      <span class="tool-name">{{ toolCall.function.name }}</span>
                    </span>
                    <span v-else>
                      <ThunderboltOutlined /> 工具 <span class="tool-name">{{ toolCall.function.name }}</span> 执行完成
                    </span>

                    <!-- <span class="step-badge" v-if="message.step !== undefined">步骤 {{ message.step }}</span> -->
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
          </template>
        </MessageComponent>
      </div>

      <div class="bottom">
        <div class="message-input-wrapper">
          <MessageInputComponent
            v-model="userInput"
            :is-loading="isProcessing"
            :disabled="!currentAgent || isProcessing"
            :send-button-disabled="!userInput || !currentAgent || isProcessing"
            :placeholder="'输入问题...'"
            @send="sendMessage"
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
import { ref, reactive, onMounted, watch, nextTick, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  RobotOutlined, SendOutlined, LoadingOutlined,
  ThunderboltOutlined, ReloadOutlined, CheckCircleOutlined,
  PlusCircleOutlined
} from '@ant-design/icons-vue';
import MessageInputComponent from '@/components/MessageInputComponent.vue'
import MessageComponent from '@/components/MessageComponent.vue'

// ========= 加载路由参数并获取 agent id ====================
const route = useRoute();
const router = useRouter();
const useSingleMode = computed(() => !!route.params.agent_id);

// ==================== 状态管理 ====================

// UI状态
const state = reactive({});

// 应用选项
const options = reactive({
  use_web: true,
  debug_mode: false,
});

// DOM引用
const messagesContainer = ref(null);

// 数据状态
const agents = ref({});                // 智能体列表
const currentAgent = ref(null);        // 当前选中的智能体
const userInput = ref('');             // 用户输入
const messages = ref([]);              // 消息列表
const isProcessing = ref(false);       // 是否正在处理请求
const threadId = ref(null);            // 会话线程ID

// ==================== 工具调用相关 ====================

// 工具调用相关
const toolCalls = ref([]);             // 工具调用列表
const currentToolCallId = ref(null);   // 当前工具调用ID
const currentRunId = ref(null);        // 当前运行ID
const messageStepMap = ref({});        // 消息步骤映射
const expandedToolCalls = ref(new Set()); // 展开的工具调用集合

// ==================== 基础工具函数 ====================


// 滚动到底部 TODO: 需要优化
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
  if (useSingleMode.value) return; // 单页面模式下不允许切换智能体
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
        use_web: options.use_web
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
    lastAssistantMsg.status = 'finished';
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
    msgInstance.status = 'loading';
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

// // 点击外部关闭选项面板
// onClickOutside(optionsPanel, () => {
//   state.showOptions = false;
// });

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

// 监听消息变化自动滚动
watch(messages, () => {
  scrollToBottom();
}, { deep: true });

// 组件挂载时加载状态
onMounted(async () => {
  try {
    console.log("组件挂载");
    // 获取智能体列表
    await fetchAgents();

    // 检查加载状态
    console.log("单页面模式:", useSingleMode.value);
    console.log("路由参数:", route.params.agent_id);
    console.log("智能体列表:", Object.keys(agents.value));

    // 初始加载 - 确保使用 Vue Router 的解析后路由
    // 使用 setTimeout 确保路由完全解析
    setTimeout(async () => {
      await loadAgentData();
      console.log("初始化后消息数量:", messages.value.length);
    }, 10);
  } catch (error) {
    console.error("组件挂载出错:", error);
  }
});

// 添加路由参数变化监听
watch(() => route.params.agent_id, async (newAgentId, oldAgentId) => {
  try {
    console.log("路由参数变化", oldAgentId, "->", newAgentId);

    // 如果路由参数变化了（包括从有参数变为无参数的情况）
    if (oldAgentId !== newAgentId) {
      // 重置会话
      messages.value = [];
      threadId.value = null;
      resetStatusSteps();

      // 加载新的智能体数据
      await loadAgentData();
    }
  } catch (error) {
    console.error('路由参数变化处理出错:', error);
  }
}, { immediate: true });

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

// 从localStorage加载状态
const loadState = () => {
  try {
    // 确定存储前缀
    const storagePrefix = useSingleMode.value ?
      (route.params.agent_id ? `agent-single-${route.params.agent_id}` : null) :
      'agent-multi';

    if (!storagePrefix) {
      console.error('无法确定存储前缀，agent_id缺失');
      return;
    }

    console.log("loadState with prefix:", storagePrefix);

    // 在单页面模式下，直接从路由参数加载智能体
    if (useSingleMode.value) {
      // 智能体已在 loadAgentData 中设置，这里不再需要重复设置
    } else {
      // 多智能体模式下，从本地存储加载当前选择的智能体
      const savedAgent = localStorage.getItem(`${storagePrefix}-current-agent`);
      if (savedAgent && agents.value && agents.value[savedAgent]) {
        currentAgent.value = agents.value[savedAgent];
      }
    }

    // 加载设置选项
    const savedOptions = localStorage.getItem(`${storagePrefix}-options`);
    if (savedOptions) {
      try {
        Object.assign(options, JSON.parse(savedOptions));
      } catch (e) {
        console.error('解析选项数据出错:', e);
      }
    }

    // 加载消息历史
    const savedMessages = localStorage.getItem(`${storagePrefix}-messages`);
    if (savedMessages) {
      try {
        const parsedMessages = JSON.parse(savedMessages);
        console.log(`加载消息历史 (${storagePrefix}):`, parsedMessages ? parsedMessages.length : 0);
        if (Array.isArray(parsedMessages)) {
          messages.value = parsedMessages;
        }

        // 检查消息历史是否成功加载
        console.log(`消息历史加载后数量:`, messages.value.length);
      } catch (e) {
        console.error('解析消息历史出错:', e);
      }
    }

    // 加载线程ID
    const savedThreadId = localStorage.getItem(`${storagePrefix}-thread-id`);
    if (savedThreadId) {
      threadId.value = savedThreadId;
      console.log(`加载线程ID (${storagePrefix}):`, threadId.value);
    }
  } catch (error) {
    console.error('从localStorage加载状态出错:', error);
  }
};

// 保存状态到localStorage
const saveState = () => {
  try {
    // 防止初始化阶段保存干扰
    if (!currentAgent.value) {
      console.log("当前没有选中智能体，跳过保存");
      return;
    }

    // 确定存储前缀 - 确保agent_id总是可用
    let prefix = 'agent-multi';
    if (useSingleMode.value) {
      if (route.params.agent_id) {
        prefix = `agent-single-${route.params.agent_id}`;
      } else {
        console.error("保存状态时缺少agent_id");
        return; // 不保存
      }
    }

    console.log("saveState with prefix:", prefix);

    // 多智能体模式下，保存当前选择的智能体
    if (!useSingleMode.value && currentAgent.value) {
      localStorage.setItem(`${prefix}-current-agent`, currentAgent.value.name);
    }

    // 保存设置选项
    localStorage.setItem(`${prefix}-options`, JSON.stringify(options));

    // 保存消息历史
    if (messages.value && messages.value.length > 0) {
      console.log(`保存消息历史 (${prefix}):`, messages.value.length);
      localStorage.setItem(`${prefix}-messages`, JSON.stringify(messages.value));
    } else {
      localStorage.removeItem(`${prefix}-messages`);
    }

    // 保存线程ID
    if (threadId.value) {
      localStorage.setItem(`${prefix}-thread-id`, threadId.value);
      console.log(`保存线程ID (${prefix}):`, threadId.value);
    } else {
      localStorage.removeItem(`${prefix}-thread-id`);
    }
  } catch (error) {
    console.error('保存状态到localStorage出错:', error);
  }
};

// 加载智能体数据的方法
const loadAgentData = async () => {
  try {
    // 确保智能体列表已加载
    if (Object.keys(agents.value).length === 0) {
      await fetchAgents();
    }

    // 在单页面模式下，设置当前智能体
    if (useSingleMode.value && route.params.agent_id) {
      const agentId = route.params.agent_id;
      if (agents.value && agents.value[agentId]) {
        currentAgent.value = agents.value[agentId];
        console.log("设置当前智能体", currentAgent.value.name);
      } else {
        console.error("未找到指定的智能体:", agentId);
      }
    }

    // 加载保存的状态 - 在设置好currentAgent后再加载状态
    loadState();

    // 处理消息历史
    if (messages.value && messages.value.length > 0) {
      console.log("处理消息历史:", messages.value.length);
      messages.value = prepareMessageHistory(messages.value);
    }
  } catch (error) {
    console.error('加载智能体数据出错:', error);
  }
};

// 监听状态变化并保存
watch([currentAgent, options, messages, threadId], () => {
  try {
    saveState();
  } catch (error) {
    console.error('保存状态时出错:', error);
  }
}, { deep: true });
</script>

<style lang="less" scoped>
@import '@/assets/main.css';

.chat-container {
  display: flex;
  width: 100%;
  height: 100%;
  position: relative;
  min-height: 100vh;
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
    font-size: 15px;
    width: auto;
    padding: 0.5rem 1rem;
    transition: background-color 0.3s;

    .text {
      margin-left: 10px;
    }

    &:hover {
      background-color: var(--main-light-3);
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
  .chat {
    height: calc(100vh - 60px);
  }

  .chat-box {
    padding: 1rem 1rem;
  }

  .bottom {
    padding: 0.5rem 0.5rem;
  }

  .chat-header {
    padding: 0.5rem 1rem !important;

    .nav-btn {
      font-size: 14px !important;
      padding: 0.4rem 0.8rem !important;
    }
  }
}
</style>
