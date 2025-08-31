import { defineStore } from 'pinia';
import { agentApi, threadApi } from '@/apis/agent_api';
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

    // 线程相关状态已迁移到组件级别

    // 加载状态
    isLoadingAgents: false,
    isLoadingConfig: false,
    isLoadingTools: false,

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
    configurableItems: (state) => {
      const agent = state.selectedAgentId ? state.agents[state.selectedAgentId] : null;
      if (!agent || !agent.configurable_items) return {};

      const agentConfigurableItems = agent.configurable_items;
      const items = { ...agentConfigurableItems };
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

    // --- 线程与消息相关 Getters (MOVED TO COMPONENT) ---
  },

  actions: {
    // 初始化store
    async initialize() {
      if (this.isInitialized) return;

      try {
        await this.fetchAgents();
        await this.fetchDefaultAgent();

        if (!this.selectedAgentId || !this.agents[this.selectedAgentId]) {
          if (this.defaultAgentId && this.agents[this.defaultAgentId]) {
            this.selectAgent(this.defaultAgentId);
          } else if (Object.keys(this.agents).length > 0) {
            const firstAgentId = Object.keys(this.agents)[0];
            this.selectAgent(firstAgentId);
          }
        } else {
          console.log('Condition FALSE: Persisted selected agent is valid. Keeping it.');
        }

        if (this.selectedAgentId) {
          await this.loadAgentConfig();
          await this.fetchTools();
        }

        this.isInitialized = true;
      } catch (error) {
        console.error('Failed to initialize agent store:', error);
        handleChatError(error, 'initialize');
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
        handleChatError(error, 'fetch');
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
      } catch (error) {
        console.error('Failed to fetch default agent:', error);
        handleChatError(error, 'fetch');
        this.error = error.message;
      }
    },

    // 设置默认智能体
    async setDefaultAgent(agentId) {
      try {
        await agentApi.setDefaultAgent(agentId);
        this.defaultAgentId = agentId;
      } catch (error) {
        console.error('Failed to set default agent:', error);
        handleChatError(error, 'save');
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
        handleChatError(error, 'load');
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
        handleChatError(error, 'save');
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
        const response = await agentApi.getTools(this.selectedAgentId);
        this.availableTools = response.tools;
      } catch (error) {
        console.error('Failed to fetch tools:', error);
        handleChatError(error, 'fetch');
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

    // ==================== 线程管理方法已迁移到组件级别 ====================

    // 重置store状态
    reset() {
      this.agents = {};
      this.selectedAgentId = null;
      this.defaultAgentId = null;
      this.agentConfig = {};
      this.originalAgentConfig = {};
      this.availableTools = [];
      this.isLoadingAgents = false;
      this.isLoadingConfig = false;
      this.isLoadingTools = false;
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