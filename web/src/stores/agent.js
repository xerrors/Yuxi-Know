import { defineStore } from 'pinia';
import { agentApi, threadApi } from '@/apis/agent';
import { MessageProcessor } from '@/utils/messageProcessor';
import { handleChatError } from '@/utils/errorHandler';

export const useAgentStore = defineStore('agent', {
  state: () => ({
    // 智能体相关状态
    agents: {}, // 以ID为键的智能体对象
    selectedAgentId: null, // 当前选中的智能体ID
    defaultAgentId: null, // 默认智能体ID

    // 智能体配置相关状态
    agentConfig: {}, // 当前智能体的配置
    originalAgentConfig: {}, // 原始配置，用于重置

    // 工具相关状态
    availableTools: [], // 所有可用工具列表

    // 线程相关状态
    threads: {}, // 以智能体ID为键的线程列表
    currentThreadId: null, // 当前选中的线程ID
    threadMessages: {}, // 以线程ID为键的消息列表

    // 对话状态
    onGoingConv: { msgChunks: {} }, // 正在进行的对话（流式）
    isStreaming: false, // 是否正在接收流式响应

    // 加载状态
    isLoadingAgents: false,
    isLoadingConfig: false,
    isLoadingTools: false,
    isLoadingThreads: false,
    isLoadingMessages: false,

    // 错误状态
    error: null,

    // 初始化状态
    isInitialized: false
  }),

  getters: {
    // --- 智能体相关 Getters ---
    selectedAgent: (state) => state.selectedAgentId ? state.agents[state.selectedAgentId] : null,
    defaultAgent: (state) => state.defaultAgentId ? state.agents[state.defaultAgentId] : state.agents[Object.keys(state.agents)[0]],
    agentsList: (state) => Object.values(state.agents),
    isDefaultAgent: (state) => state.selectedAgentId === state.defaultAgentId,
    configSchema: (state) => {
      const agent = state.selectedAgentId ? state.agents[state.selectedAgentId] : null;
      return agent?.config_schema || {};
    },
    configurableItems: (state) => {
      const schema = state.configSchema || {};
      if (!schema || !schema.configurable_items) return {};
      const items = { ...schema.configurable_items };
      Object.keys(items).forEach(key => {
        const item = items[key];
        if (item && item.x_oap_ui_config) {
          items[key] = { ...item, ...item.x_oap_ui_config };
          delete items[key].x_oap_ui_config;
        }
      });
      return items;
    },
    hasConfigChanges: (state) => JSON.stringify(state.agentConfig) !== JSON.stringify(state.originalAgentConfig),

    // --- 线程与消息相关 Getters ---
    currentAgentThreads: (state) => state.selectedAgentId ? (state.threads[state.selectedAgentId] || []) : [],
    currentThread: (state) => {
      if (!state.currentThreadId || !state.selectedAgentId) return null;
      const agentThreads = state.threads[state.selectedAgentId] || [];
      return agentThreads.find(thread => thread.id === state.currentThreadId);
    },
    currentThreadMessages: (state) => state.currentThreadId ? (state.threadMessages[state.currentThreadId] || []) : [],

    // --- 对话UI Getters ---
    onGoingConvMessages: (state) => {
      const msgs = Object.values(state.onGoingConv.msgChunks).map(MessageProcessor.mergeMessageChunk);
      return msgs.length > 0
        ? MessageProcessor.convertToolResultToMessages(msgs).filter(msg => msg.type !== 'tool')
        : [];
    },
    conversations: (state) => {
      const historyConvs = MessageProcessor.convertServerHistoryToMessages(state.currentThreadMessages);
      // Access onGoingConvMessages getter through state
      const onGoingMessages = state.onGoingConvMessages;

      if (onGoingMessages.length > 0) {
        // Create a new conversation object for the ongoing messages
        const onGoingConv = {
          messages: onGoingMessages,
          status: 'streaming'
        };
        return [...historyConvs, onGoingConv];
      }
      return historyConvs;
    },
  },

  actions: {
    // 初始化store
    async initialize() {
      if (this.isInitialized) return;

      try {
        await Promise.all([
          this.fetchAgents(),
          this.fetchDefaultAgent(),
          this.fetchTools()
        ]);
        this.isInitialized = true;
      } catch (error) {
        console.error('Failed to initialize agent store:', error);
        this.error = error.message;
      }
    },

    // 获取智能体列表
    async fetchAgents() {
      this.isLoadingAgents = true;
      this.error = null;

      try {
        const response = await agentApi.getAgents();
        // 将数组转换为以ID为键的对象
        this.agents = response.agents.reduce((acc, agent) => {
          acc[agent.id] = agent;
          return acc;
        }, {});
      } catch (error) {
        console.error('Failed to fetch agents:', error);
        this.error = error.message;
        throw error;
      } finally {
        this.isLoadingAgents = false;
      }
    },

    // 获取默认智能体
    async fetchDefaultAgent() {
      try {
        const response = await agentApi.getDefaultAgent();
        this.defaultAgentId = response.default_agent_id;

        // 如果没有选中的智能体，则选择默认智能体
        if (!this.selectedAgentId && this.defaultAgentId) {
          this.selectedAgentId = this.defaultAgentId;
        }
      } catch (error) {
        console.error('Failed to fetch default agent:', error);
        this.error = error.message;
      }
    },

    // 设置默认智能体
    async setDefaultAgent(agentId) {
      try {
        await agentConfigApi.setDefaultAgent(agentId);
        this.defaultAgentId = agentId;
      } catch (error) {
        console.error('Failed to set default agent:', error);
        this.error = error.message;
        throw error;
      }
    },

    // 选择智能体
    selectAgent(agentId) {
      if (this.agents[agentId]) {
        this.selectedAgentId = agentId;
        // 清空之前的配置
        this.agentConfig = {};
        this.originalAgentConfig = {};
      }
    },

    // 加载智能体配置
    async loadAgentConfig(agentId = null) {
      const targetAgentId = agentId || this.selectedAgentId;
      if (!targetAgentId) return;

      this.isLoadingConfig = true;
      this.error = null;

      try {
        const response = await agentApi.getAgentConfig(targetAgentId);
        this.agentConfig = { ...response.config };
        this.originalAgentConfig = { ...response.config };
      } catch (error) {
        console.error('Failed to load agent config:', error);
        this.error = error.message;
        throw error;
      } finally {
        this.isLoadingConfig = false;
      }
    },

    // 保存智能体配置
    async saveAgentConfig(agentId = null) {
      const targetAgentId = agentId || this.selectedAgentId;
      if (!targetAgentId) return;

      try {
        await agentApi.saveAgentConfig(targetAgentId, this.agentConfig);
        this.originalAgentConfig = { ...this.agentConfig };
      } catch (error) {
        console.error('Failed to save agent config:', error);
        this.error = error.message;
        throw error;
      }
    },

    // 重置智能体配置
    resetAgentConfig() {
      this.agentConfig = { ...this.originalAgentConfig };
    },

    // 更新配置项
    updateConfigItem(key, value) {
      this.agentConfig[key] = value;
    },

    // 更新智能体配置（支持批量更新）
    updateAgentConfig(updates) {
      Object.assign(this.agentConfig, updates);
    },

    // 获取工具列表
    async fetchTools() {
      this.isLoadingTools = true;
      this.error = null;

      try {
        const response = await agentApi.getTools();
        this.availableTools = response.tools;
      } catch (error) {
        console.error('Failed to fetch tools:', error);
        this.error = error.message;
        throw error;
      } finally {
        this.isLoadingTools = false;
      }
    },

    // 清除错误状态
    clearError() {
      this.error = null;
    },

    // ==================== 线程管理方法 ====================

    // 获取智能体的线程列表
    async fetchThreads(agentId = null) {
      const targetAgentId = agentId || this.selectedAgentId;
      if (!targetAgentId) return;

      this.isLoadingThreads = true;
      this.error = null;

      try {
        const threads = await threadApi.getThreads(targetAgentId);
        this.threads[targetAgentId] = threads || [];
      } catch (error) {
        console.error('Failed to fetch threads:', error);
        this.error = error.message;
        throw error;
      } finally {
        this.isLoadingThreads = false;
      }
    },

    // 创建新线程
    async createThread(agentId, title = '新的对话') {
      if (!agentId) return null;

      try {
        const thread = await threadApi.createThread(agentId, title);
        if (thread) {
          // 更新线程列表
          if (!this.threads[agentId]) {
            this.threads[agentId] = [];
          }
          this.threads[agentId].unshift(thread);

          // 设置为当前线程
          this.currentThreadId = thread.id;

          // 初始化消息列表
          this.threadMessages[thread.id] = [];
        }
        return thread;
      } catch (error) {
        console.error('Failed to create thread:', error);
        this.error = error.message;
        throw error;
      }
    },

    // 删除线程
    async deleteThread(threadId) {
      if (!threadId) return;

      try {
        await threadApi.deleteThread(threadId);

        // 从所有智能体的线程列表中移除
        Object.keys(this.threads).forEach(agentId => {
          this.threads[agentId] = this.threads[agentId].filter(thread => thread.id !== threadId);
        });

        // 清理消息
        delete this.threadMessages[threadId];

        // 如果删除的是当前线程，重置当前线程ID
        if (this.currentThreadId === threadId) {
          this.currentThreadId = null;
        }
      } catch (error) {
        console.error('Failed to delete thread:', error);
        this.error = error.message;
        throw error;
      }
    },

    // 更新线程标题
    async updateThread(threadId, title) {
      if (!threadId || !title) return;

      try {
        await threadApi.updateThread(threadId, title);

        // 更新本地线程列表中的标题
        Object.keys(this.threads).forEach(agentId => {
          const thread = this.threads[agentId].find(t => t.id === threadId);
          if (thread) {
            thread.title = title;
          }
        });
      } catch (error) {
        console.error('Failed to update thread:', error);
        this.error = error.message;
        throw error;
      }
    },

    // 选择线程
    selectThread(threadId) {
      this.currentThreadId = threadId;
      this.resetOnGoingConv();

      // 如果没有该线程的消息，初始化空数组
      if (threadId && !this.threadMessages[threadId]) {
        this.threadMessages[threadId] = [];
      }
    },

    // 获取线程消息
    async fetchThreadMessages(threadId) {
      if (!threadId) return;

      this.isLoadingMessages = true;
      this.error = null;
      this.resetOnGoingConv();

      try {
        const response = await agentApi.getAgentHistory(this.selectedAgentId, threadId);
        this.threadMessages[threadId] = response.history || [];
      } catch (error) {
        handleChatError(error, 'load');
        throw error;
      } finally {
        this.isLoadingMessages = false;
      }
    },

    // --- 流式对话 Actions ---

    resetOnGoingConv() {
      this.onGoingConv = { msgChunks: {} };
    },

    _processStreamChunk(chunk) {
      const { status, msg, request_id, message } = chunk;
      switch (status) {
        case 'init':
          this.onGoingConv.msgChunks[request_id] = [msg];
          break;
        case 'loading':
          if (msg.id) {
            if (!this.onGoingConv.msgChunks[msg.id]) {
              this.onGoingConv.msgChunks[msg.id] = [];
            }
            this.onGoingConv.msgChunks[msg.id].push(msg);
          }
          break;
        case 'error':
          handleChatError({ message }, 'stream');
          break;
        case 'finished':
          this.fetchThreadMessages(this.currentThreadId);
          break;
      }
    },

    // 发送消息并处理流式响应
    async sendMessage(text) {
      if (!this.selectedAgentId || !this.currentThreadId || !text) {
        handleChatError({ message: "Missing agent, thread, or message text" }, 'send');
        return;
      }

      this.isStreaming = true;
      this.resetOnGoingConv();

      // 如果是新对话，用消息内容作为标题
      if (this.currentThreadMessages.length === 0) {
        this.updateThread(this.currentThreadId, text);
      }

      const requestData = {
        query: text,
        config: {
          thread_id: this.currentThreadId,
        },
      };

      try {
        const response = await agentApi.sendAgentMessage(this.selectedAgentId, requestData);
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.trim()) {
              try {
                const chunk = JSON.parse(line.trim());
                this._processStreamChunk(chunk);
              } catch (e) {
                console.warn('Failed to parse stream chunk JSON:', e);
              }
            }
          }
        }
        // Process any remaining data in the buffer
        if (buffer.trim()) {
          try {
            const chunk = JSON.parse(buffer.trim());
            this._processStreamChunk(chunk);
          } catch (e) {
            console.warn('Failed to parse final stream chunk JSON:', e);
          }
        }

      } catch (error) {
        handleChatError(error, 'send');
      } finally {
        this.isStreaming = false;
      }
    },

    // 添加消息到线程
    addMessageToThread(threadId, message) {
      if (!threadId || !message) return;

      if (!this.threadMessages[threadId]) {
        this.threadMessages[threadId] = [];
      }

      this.threadMessages[threadId].push(message);
    },

    // 更新线程中的消息
    updateMessageInThread(threadId, messageIndex, updatedMessage) {
      if (!threadId || messageIndex < 0 || !this.threadMessages[threadId]) return;

      if (messageIndex < this.threadMessages[threadId].length) {
        this.threadMessages[threadId][messageIndex] = updatedMessage;
      }
    },

    // 重置store状态
    reset() {
      this.agents = {};
      this.selectedAgentId = null;
      this.defaultAgentId = null;
      this.agentConfig = {};
      this.originalAgentConfig = {};
      this.availableTools = [];
      this.threads = {};
      this.currentThreadId = null;
      this.threadMessages = {};
      this.isLoadingAgents = false;
      this.isLoadingConfig = false;
      this.isLoadingTools = false;
      this.isLoadingThreads = false;
      this.isLoadingMessages = false;
      this.error = null;
      this.isInitialized = false;
    }
  },

  // 持久化配置
  persist: {
    key: 'agent-store',
    storage: localStorage,
    paths: ['selectedAgentId', 'defaultAgentId'] // 只持久化关键状态
  }
});