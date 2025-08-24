import { defineStore } from 'pinia';
import { agentApi, threadApi } from '@/apis/agent';

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
    // 获取当前选中的智能体
    selectedAgent() {
      return this.selectedAgentId ? this.agents[this.selectedAgentId] : null;
    },

    // 获取默认智能体，默认取第一个
    defaultAgent() {
      return this.defaultAgentId ? this.agents[this.defaultAgentId] : this.agents[Object.keys(this.agents)[0]];
    },

    // 获取智能体列表（数组形式）
    agentsList() {
      return Object.values(this.agents);
    },

    // 判断当前智能体是否为默认智能体
    isDefaultAgent() {
      return this.selectedAgentId === this.defaultAgentId;
    },

    // 获取当前智能体的配置schema
    configSchema() {
      const agent = this.selectedAgentId ? this.agents[this.selectedAgentId] : null;
      return agent?.config_schema || {};
    },

    // 获取可配置项（处理x_oap_ui_config）
    configurableItems() {
      const schema = this.configSchema || {};
      if (!schema || !schema.configurable_items) return {};

      const items = { ...schema.configurable_items };

      // 处理x_oap_ui_config，将其提升到上一层
      Object.keys(items).forEach(key => {
        const item = items[key];
        if (item && item.x_oap_ui_config) {
          items[key] = {
            ...item,
            ...item.x_oap_ui_config
          };
          delete items[key].x_oap_ui_config;
        }
      });

      return items;
    },

    // 检查配置是否有变更
    hasConfigChanges() {
      return JSON.stringify(this.agentConfig) !== JSON.stringify(this.originalAgentConfig);
    },

    // 获取当前智能体的线程列表
    currentAgentThreads() {
      return this.selectedAgentId ? (this.threads[this.selectedAgentId] || []) : [];
    },

    // 获取当前线程
    currentThread() {
      if (!this.currentThreadId || !this.selectedAgentId) return null;
      const agentThreads = this.threads[this.selectedAgentId] || [];
      return agentThreads.find(thread => thread.id === this.currentThreadId);
    },

    // 获取当前线程的消息
    currentThreadMessages() {
      return this.currentThreadId ? (this.threadMessages[this.currentThreadId] || []) : [];
    }
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

      try {
        const response = await agentApi.getAgentHistory(this.selectedAgentId, threadId);
        this.threadMessages[threadId] = response.history || [];
      } catch (error) {
        console.error('Failed to fetch thread messages:', error);
        this.error = error.message;
        throw error;
      } finally {
        this.isLoadingMessages = false;
      }
    },

    // 发送消息
    async sendMessage(agentId, requestData) {
      if (!agentId) return null;

      try {
        const response = await agentApi.sendAgentMessage(agentId, requestData);
        return response;
      } catch (error) {
        console.error('Failed to send message:', error);
        this.error = error.message;
        throw error;
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