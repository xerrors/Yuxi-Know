<template>
  <div class="chat-container">
    <div class="chat">
      <div class="chat-header">
        <div class="header__left">
          <slot name="header-left" class="nav-btn"></slot>
          <div class="newchat nav-btn" @click="resetThread" :disabled="isProcessing">
            <PlusCircleOutlined /> <span class="text">新对话</span>
          </div>
        </div>
        <div class="header__center">
          <slot name="header-center"></slot>
        </div>
        <div class="header__right">
          <div class="current-agent nav-btn" @click="sayHi">
            <RobotOutlined />&nbsp;
            <span v-if="currentAgent">{{ currentAgent.name }}</span>
            <span v-else>加载中...</span>
          </div>
          <slot name="header-right"></slot>
        </div>
      </div>

      <div v-if="messages.length === 0" class="chat-examples">
        <h1>{{ currentAgent ? currentAgent.name : '请选择一个智能体开始对话' }}</h1>
        <p>{{ currentAgent ? currentAgent.description : '不同的智能体有不同的专长和能力' }}</p>
      </div>

      <div class="chat-box" ref="messagesContainer" :class="{ 'is-debug': state.debug_mode }">
        <MessageComponent
          v-for="(message, index) in messages"
          :message="message"
          :key="index"
          :is-processing="isProcessing"
          :debug-mode="state.debug_mode"
          :show-refs="showMsgRefs(message)"
          @retry="retryMessage(message)"
        >
          <div v-if="state.debug_mode" class="status-info">{{ message }}</div>

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
                        执行结果
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
import {
  RobotOutlined, SendOutlined, LoadingOutlined,
  ThunderboltOutlined, ReloadOutlined, CheckCircleOutlined,
  PlusCircleOutlined
} from '@ant-design/icons-vue';
import { message } from 'ant-design-vue';
import MessageInputComponent from '@/components/MessageInputComponent.vue'
import MessageComponent from '@/components/MessageComponent.vue'

// 新增props属性，允许父组件传入agentId
const props = defineProps({
  agentId: {
    type: String,
    default: null
  },
  config: {
    type: Object,
    default: () => ({})
  },
  state: {
    type: Object,
    default: () => ({})
  }
});

// ==================== 状态管理 ====================

// UI状态
const state = ref(props.state);
const waitingServerResponse = ref(false);
const showMsgRefs = (msg) => {
  if (msg.isLast) {
    return ['copy', 'regenerate']
  }
  return false
}

// DOM引用
const messagesContainer = ref(null);

// 数据状态
const agents = ref({});                // 智能体列表
const currentAgent = ref(null);        // 当前选中的智能体
const userInput = ref('');             // 用户输入
const messages = ref([]);              // 消息列表
const isProcessing = ref(false);       // 是否正在处理请求

// ==================== 工具调用相关 ====================

// 工具调用相关
const toolCalls = ref([]);             // 工具调用列表
const currentToolCallId = ref(null);   // 当前工具调用ID
const currentRunId = ref(null);        // 当前运行ID
const messageStepMap = ref({});        // 消息步骤映射
const expandedToolCalls = ref(new Set()); // 展开的工具调用集合

// ==================== 基础工具函数 ====================


// 滚动到底部 TODO: 需要优化当用户向上滚动的时候，停止滚动，当用户点击回到底部或者滚动到最底部的时候，再滚动到底部
const scrollToBottom = async () => {
  await nextTick();
  if (!messagesContainer.value) return;

  // 找到真正需要滚动的容器元素
  const containerBox = messagesContainer.value;
  const container = document.querySelector('.chat');
  if (!container) return;

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
const retryMessage = (message) => {
  // 获取用户消息的request_id
  const requestId = message.request_id;
  const sendMessage = messages.value.find(msg => msg.id === requestId);
  const sendMessageIndex = messages.value.indexOf(sendMessage);

  // 删除包含 request_id 之后的所有消息
  messages.value = messages.value.slice(0, sendMessageIndex);

  // 重新发送消息
  sendMessageWithText(sendMessage.content);
};

// ==================== 核心消息处理 ====================

// 使用文本发送消息
const sendMessageWithText = async (text) => {
  if (!text || !currentAgent.value || isProcessing.value) return;

  // 重置状态
  resetStatusSteps();

  const userMessage = text.trim();
  const requestId = currentAgent.value.name + '-' + new Date().getTime();

  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: userMessage,
    id: requestId
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

    waitingServerResponse.value = true;
    // 设置请求参数
    const requestData = {
      query: userMessage,
      history: history.slice(0, -1), // 去掉最后一条刚添加的用户消息
      config: {
        ...props.config
      },
      meta: {
        request_id: requestId
      }
    };

    // 发送请求
    const response = await fetch(`/api/chat/agent/${currentAgent.value.name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestData)
    });

    // console.log("requestData", requestData);
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
    waitingServerResponse.value = false;
    isProcessing.value = false;
    await scrollToBottom();
  }
};

// 处理流式响应
const handleStreamResponse = async (response) => {
  try {
    await scrollToBottom();

    // 检查是否支持现代流API
    if ('TransformStream' in window && 'ReadableStream' in window) {
      const jsonStream = new TransformStream({
        start(controller) {
          this.buffer = '';
          this.decoder = new TextDecoder();
        },
        transform(chunk, controller) {
          this.buffer += this.decoder.decode(chunk, { stream: true });

          let position;
          while ((position = this.buffer.indexOf('\n')) !== -1) {
            const line = this.buffer.substring(0, position).trim();
            this.buffer = this.buffer.substring(position + 1);

            if (line) {
              try {
                controller.enqueue(JSON.parse(line));
              } catch (e) {
                // 不完整的JSON，保留在缓冲区中
              }
            }
          }
        },
        flush(controller) {
          if (this.buffer.trim()) {
            try {
              controller.enqueue(JSON.parse(this.buffer.trim()));
            } catch (e) {
              console.warn('最终缓冲区内容无法解析:', this.buffer);
            }
          }
        }
      });

      // 通过管道处理响应流
      const transformedStream = response.body.pipeThrough(jsonStream);
      const reader = transformedStream.getReader();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // 这里的value已经是解析后的JSON对象
        if (value) {
          if (value.debug_mode) {
            console.log("debug_mode", value);
          }

          // 处理不同状态的消息
          if (value.status === 'init') {
            await handleInit(value);
          } else if (value.status === 'finished') {
            await handleFinished(value);
          } else if (value.status === 'error') {
            await handleError(value);
          } else {
            await handleMessageById(value);
          }

          await scrollToBottom();
        }
      }
    } else {
      // 降级方案：使用传统方式处理流数据
      const reader = response.body.getReader();
      let buffer = '';
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // 保留最后一行可能不完整的内容

        for (const line of lines) {
          if (line.trim()) {
            try {
              const data = JSON.parse(line.trim());

              if (data.debug_mode) {
                console.log("debug_mode", data);
              }

              if (data.status === 'init') {
                await handleInit(data);
              } else if (data.status === 'finished') {
                await handleFinished(data);
              } else {
                await handleMessageById(data);
              }
            } catch (e) {
              console.debug('解析JSON出错:', e.message);
            }
          }
        }

        await scrollToBottom();
      }

      // 处理缓冲区中可能剩余的内容
      if (buffer.trim()) {
        try {
          const data = JSON.parse(buffer.trim());
          if (data.status === 'init') {
            await handleInit(data);
          } else if (data.status === 'finished') {
            await handleFinished(data);
          } else {
            await handleMessageById(data);
          }
        } catch (e) {
          console.warn('最终缓冲区内容无法解析:', buffer);
        }
      }
    }
  } catch (error) {
    console.error('流式处理出错:', error);
    const lastMsg = messages.value[messages.value.length - 1];
    if (lastMsg.role === 'assistant') {
      lastMsg.status = 'error';
      lastMsg.message = error.message;
    } else {
      messages.value.push({
        role: 'assistant',
        message: `发生错误: ${error.message}`,
        status: 'error'
      });
      await scrollToBottom();
    }
    isProcessing.value = false;
  }
};

const handleInit = async (data) => {
  waitingServerResponse.value = false;
  console.log("handleInit", data);
  const initMsg = {
    role: 'assistant',
    content: '',
    status: 'init',
    toolCalls: {},
    toolCallIds: {},
    request_id: data.request_id
  }
  messages.value.push(initMsg);
  await scrollToBottom();
}

// 处理完成状态
const handleFinished = async (data) => {
  // 更新最后一条助手消息的状态
  const lastAssistantMsg = messages.value[messages.value.length - 1];
  if (lastAssistantMsg) {
    // 如果既没有内容也没有工具调用，添加一个完成提示
    if ((!lastAssistantMsg.content || lastAssistantMsg.content.trim().length === 0) &&
        (!lastAssistantMsg.toolCalls || Object.keys(lastAssistantMsg.toolCalls).length === 0)) {
      lastAssistantMsg.content = '已完成';
    }
    // 更新状态为已完成
    lastAssistantMsg.status = 'finished';
    lastAssistantMsg.isLast = true;
    lastAssistantMsg.meta = data.meta;
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
      const loadingAssistantIndex = messages.value.findIndex(m => m.role === 'assistant' && m.status === 'init');
      if (loadingAssistantIndex !== -1) {
        // 更新现有助手消息
        messages.value[loadingAssistantIndex].id = msgId;
        messageMap.value.set(msgId, loadingAssistantIndex);
        console.log("更新现有助手消息", messages.value[loadingAssistantIndex]);
        await updateExistingMessage(data, loadingAssistantIndex);
      } else {
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
  const requestId = data.metadata?.request_id || data.request_id;

  let currentMsg = null;
  // 查看最后一个消息是不是 assistant 并且 status 是 init，并且 request_id 是当前的 request_id，而且没有 id
  const lastMsg = messages.value[messages.value.length - 1];
  const lastMsgIsInit = lastMsg.role === 'assistant'
      && lastMsg.status === 'init'
      && lastMsg.request_id === requestId
      && !lastMsg.id;

  if (lastMsgIsInit) {
    currentMsg = lastMsg;
  } else {
    // 创建新消息
    currentMsg = {
      role: 'assistant',
      status: 'init',
      toolCalls: {},
      toolCallIds: {},
      request_id: requestId
    };
    messages.value.push(currentMsg);
  }

  currentMsg.id = msgId;
  currentMsg.content = msgContent;
  currentMsg.run_id = runId;
  currentMsg.step = step;

  // 处理工具调用
  const toolCalls = data.msg.additional_kwargs?.tool_calls;
  if (toolCalls && toolCalls.length > 0) {
    // console.log("toolCalls in createAssistantMessage", toolCalls);
    for (const toolCall of toolCalls) {
      const toolCallId = toolCall.id;
      const toolIndex = toolCall.index || 0;
      currentMsg.toolCallIds[toolCallId] = toolIndex;
      currentMsg.toolCalls[toolIndex] = toolCall;
      toolCallMap.value.set(toolCallId, msgId);
    }
  }

  // 添加新消息
  const newIndex = messages.value.length - 1;
  messageMap.value.set(msgId, newIndex);

  await scrollToBottom();
};

// 更新现有消息
const updateExistingMessage = async (data, existingMsgIndex) => {
  const msgInstance = messages.value[existingMsgIndex];
  // console.log("updateExistingMessage", msgInstance);

  // 如果消息状态是loading，更新为processing
  if (msgInstance.status === 'init') {
    msgInstance.status = data.status || 'loading';
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

  // 如果状态是error，则更新为error
  if (data.status === 'error') {
    msgInstance.status = 'error';
    msgInstance.message = data.message;
  }

  // 确保变更生效
  await nextTick();
  await scrollToBottom();
};

const handleError = async (data) => {
  console.error('处理错误状态:', data);
  const lastMsg = messages.value[messages.value.length - 1];
  if (lastMsg) {
    lastMsg.status = 'error';
    lastMsg.message = data.message;
  }
  isProcessing.value = false;
};

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
    // console.log("组件挂载");
    // 获取智能体列表
    await fetchAgents();

    // 检查加载状态
    // console.log("路由参数:", props.agentId);
    // console.log("智能体列表:", Object.keys(agents.value));

    // 初始加载 - 确保使用 Vue Router 的解析后路由
    // 使用 setTimeout 确保路由完全解析
    setTimeout(async () => {
      await loadAgentData();
      // console.log("初始化后消息数量:", messages.value.length);
    }, 10);
  } catch (error) {
    console.error("组件挂载出错:", error);
  }
});

// // 处理元数据
// const handleMetadata = (data) => {
//   // 检查并更新运行ID
//   if (data.metadata?.run_id && !currentRunId.value) {
//     currentRunId.value = data.metadata.run_id;
//   }

//   // 跟踪步骤信息
//   if (data.metadata?.langgraph_step !== undefined) {
//     const step = data.metadata.langgraph_step;
//     messageStepMap.value[step] = {
//       type: data.msg?.type || 'unknown',
//       timestamp: new Date().toISOString()
//     };
//   }
// };

// 在 script setup 部分添加 toggleToolCall 方法
const toggleToolCall = (toolCallId) => {
  if (expandedToolCalls.value.has(toolCallId)) {
    expandedToolCalls.value.delete(toolCallId);
  } else {
    expandedToolCalls.value.add(toolCallId);
  }
};

// 加载智能体数据的方法
const loadAgentData = async () => {
  try {
    // 确保智能体列表已加载
    if (Object.keys(agents.value).length === 0) {
      await fetchAgents();
    }

    // 设置当前智能体
    if (props.agentId && agents.value && agents.value[props.agentId]) {
      // 如果传入了指定的agentId，就加载对应的智能体
      currentAgent.value = agents.value[props.agentId];
      // console.log("设置当前智能体", currentAgent.value.name);
    } else if (!props.agentId) {
      // 多智能体模式下，尝试从本地存储恢复上次选择的智能体
      const storagePrefix = 'agent-multi';
      const savedAgent = localStorage.getItem(`${storagePrefix}-current-agent`);
      if (savedAgent && agents.value && agents.value[savedAgent]) {
        currentAgent.value = agents.value[savedAgent];
        // console.log("从存储中恢复智能体", currentAgent.value.name);
      }
    }

    // 加载保存的状态
    loadState();

    // 处理消息历史
    if (messages.value && messages.value.length > 0) {
      // console.log("处理消息历史:", messages.value.length);
      messages.value = prepareMessageHistory(messages.value);
    }
  } catch (error) {
    console.error('加载智能体数据出错:', error);
  }
};

// 从localStorage加载状态
const loadState = () => {
  try {
    // 确定存储前缀
    const storagePrefix = props.agentId ?
      `agent-${props.agentId}` :
      'agent-multi';

    if (!storagePrefix) {
      console.error('无法确定存储前缀，agent_id缺失');
      return;
    }

    // console.log("loadState with prefix:", storagePrefix);

    // 加载消息历史
    const savedMessages = localStorage.getItem(`${storagePrefix}-messages`);
    if (savedMessages) {
      try {
        const parsedMessages = JSON.parse(savedMessages);
        // console.log(`加载消息历史 (${storagePrefix}):`, parsedMessages ? parsedMessages.length : 0);
        if (Array.isArray(parsedMessages)) {
          messages.value = parsedMessages;
        }

        // 检查消息历史是否成功加载
        // console.log(`消息历史加载后数量:`, messages.value.length);
      } catch (e) {
        console.error('解析消息历史出错:', e);
      }
    }

    // 加载线程ID
    const savedThreadId = localStorage.getItem(`${storagePrefix}-thread-id`);
    if (savedThreadId) {
      currentRunId.value = savedThreadId;
      // console.log(`加载线程ID (${storagePrefix}):`, currentRunId.value);
    }
  } catch (error) {
    console.error('从localStorage加载状态出错:', error);
  }
};

// 监听agentId变化
watch(() => props.agentId, async (newAgentId, oldAgentId) => {
  try {
    // console.log("智能体ID变化", oldAgentId, "->", newAgentId);

    // 如果变化了，重置会话并加载新数据
    if (newAgentId !== oldAgentId) {
      // 重置会话
      messages.value = [];
      currentRunId.value = null;
      resetStatusSteps();

      // 加载新的智能体数据
      await loadAgentData();
    }
  } catch (error) {
    console.error('智能体ID变化处理出错:', error);
  }
}, { immediate: true });

// 保存状态到localStorage
const saveState = () => {
  try {
    // 防止初始化阶段保存干扰
    if (!currentAgent.value) {
      console.warn("当前没有选中智能体，跳过保存");
      return;
    }

    // 确定存储前缀
    const prefix = props.agentId ? `agent-${props.agentId}` : 'agent-multi';
    // console.log("saveState with prefix:", prefix);

    // 如果是多智能体模式，保存当前选择的智能体
    if (!props.agentId && currentAgent.value) {
      localStorage.setItem(`${prefix}-current-agent`, currentAgent.value.name);
    }

    // 保存消息历史
    if (messages.value && messages.value.length > 0) {
      // console.log(`保存消息历史 (${prefix}):`, messages.value.length);
      localStorage.setItem(`${prefix}-messages`, JSON.stringify(messages.value));
    } else {
      localStorage.removeItem(`${prefix}-messages`);
    }

    // 保存线程ID
    if (currentRunId.value) {
      localStorage.setItem(`${prefix}-thread-id`, currentRunId.value);
      // console.log(`保存线程ID (${prefix}):`, currentRunId.value);
    } else {
      localStorage.removeItem(`${prefix}-thread-id`);
    }
  } catch (error) {
    console.error('保存状态到localStorage出错:', error);
  }
};

const sayHi = () => {
  message.success(`Hi, I am ${currentAgent.value.name}, ${currentAgent.value.description}`);
}

// 监听状态变化并保存
watch([currentAgent, messages, currentRunId], () => {
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
