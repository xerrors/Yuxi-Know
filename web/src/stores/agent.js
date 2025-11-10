import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { agentApi } from '@/apis/agent_api'
import { handleChatError } from '@/utils/errorHandler'
import { useUserStore } from '@/stores/user'

export const useAgentStore = defineStore('agent', () => {
  const userStore = useUserStore()
  // ==================== 状态定义 ====================
  // 智能体相关状态
  const agents = ref([])
  const selectedAgentId = ref(null)
  const defaultAgentId = ref(null)

  // 智能体配置相关状态
  const agentConfig = ref({})
  const originalAgentConfig = ref({})

  // 工具相关状态
  const availableTools = ref([])

  // 加载状态
  const isLoadingAgents = ref(false)
  const isLoadingConfig = ref(false)
  const isLoadingTools = ref(false)

  // 错误状态
  const error = ref(null)

  // 初始化状态
  const isInitialized = ref(false)

  // ==================== 计算属性 ====================
  const selectedAgent = computed(() =>
    selectedAgentId.value ? agents.value.find(a => a.id === selectedAgentId.value) : null
  )

  const defaultAgent = computed(() =>
    defaultAgentId.value ? agents.value.find(a => a.id === defaultAgentId.value) : agents.value[0]
  )

  const agentsList = computed(() => agents.value)

  const isDefaultAgent = computed(() => selectedAgentId.value === defaultAgentId.value)

  const configurableItems = computed(() => {
    const agent = selectedAgentId.value ? agents.value.find(a => a.id === selectedAgentId.value) : null
    if (!agent || !agent.configurable_items) return {}

    const agentConfigurableItems = agent.configurable_items
    const items = { ...agentConfigurableItems }
    Object.keys(items).forEach(key => {
      const item = items[key]
      if (item && item.x_oap_ui_config) {
        items[key] = { ...item, ...item.x_oap_ui_config }
        delete items[key].x_oap_ui_config
      }
    })
    return items
  })

  const hasConfigChanges = computed(() =>
    JSON.stringify(agentConfig.value) !== JSON.stringify(originalAgentConfig.value)
  )

  // ==================== 方法 ====================
  /**
   * 初始化 store
   */
  async function initialize() {
    if (isInitialized.value) return

    try {
      await fetchAgents()
      await fetchDefaultAgent()

      if (!selectedAgentId.value || !agents.value.find(a => a.id === selectedAgentId.value)) {
        if (defaultAgentId.value && agents.value.find(a => a.id === defaultAgentId.value)) {
          selectAgent(defaultAgentId.value)
        } else if (agents.value.length > 0) {
          const firstAgentId = agents.value[0].id
          selectAgent(firstAgentId)
        }
      } else {
        console.log('Condition FALSE: Persisted selected agent is valid. Keeping it.')
      }

      if (selectedAgentId.value) {
        if (userStore.isAdmin) {
          await loadAgentConfig()
        }
        await fetchTools()
      }

      isInitialized.value = true
    } catch (err) {
      console.error('Failed to initialize agent store:', err)
      handleChatError(err, 'initialize')
      error.value = err.message
    }
  }

  /**
   * 获取智能体列表
   */
  async function fetchAgents() {
    isLoadingAgents.value = true
    error.value = null

    try {
      const response = await agentApi.getAgents()
      agents.value = response.agents
    } catch (err) {
      console.error('Failed to fetch agents:', err)
      handleChatError(err, 'fetch')
      error.value = err.message
      throw err
    } finally {
      isLoadingAgents.value = false
    }
  }

  /**
   * 获取默认智能体
   */
  async function fetchDefaultAgent() {
    try {
      const response = await agentApi.getDefaultAgent()
      defaultAgentId.value = response.default_agent_id
    } catch (err) {
      console.error('Failed to fetch default agent:', err)
      handleChatError(err, 'fetch')
      error.value = err.message
    }
  }

  /**
   * 设置默认智能体
   */
  async function setDefaultAgent(agentId) {
    try {
      await agentApi.setDefaultAgent(agentId)
      defaultAgentId.value = agentId
    } catch (err) {
      console.error('Failed to set default agent:', err)
      handleChatError(err, 'save')
      error.value = err.message
      throw err
    }
  }

  /**
   * 选择智能体
   */
  function selectAgent(agentId) {
    if (agents.value.find(a => a.id === agentId)) {
      selectedAgentId.value = agentId
      // 清空之前的配置
      agentConfig.value = {}
      originalAgentConfig.value = {}
    }
  }

  /**
   * 加载智能体配置
   */
  async function loadAgentConfig(agentId = null) {
    if (!userStore.isAdmin) return

    const targetAgentId = agentId || selectedAgentId.value
    if (!targetAgentId) return

    isLoadingConfig.value = true
    error.value = null

    try {
      const response = await agentApi.getAgentConfig(targetAgentId)
      agentConfig.value = { ...response.config }
      originalAgentConfig.value = { ...response.config }
    } catch (err) {
      console.error('Failed to load agent config:', err)
      handleChatError(err, 'load')
      error.value = err.message
      throw err
    } finally {
      isLoadingConfig.value = false
    }
  }

  /**
   * 保存智能体配置
   */
  async function saveAgentConfig(agentId = null) {
    const targetAgentId = agentId || selectedAgentId.value
    if (!targetAgentId) return

    try {
      await agentApi.saveAgentConfig(targetAgentId, agentConfig.value)
      originalAgentConfig.value = { ...agentConfig.value }
    } catch (err) {
      console.error('Failed to save agent config:', err)
      handleChatError(err, 'save')
      error.value = err.message
      throw err
    }
  }

  /**
   * 重置智能体配置
   */
  function resetAgentConfig() {
    agentConfig.value = { ...originalAgentConfig.value }
  }

  /**
   * 更新配置项
   */
  function updateConfigItem(key, value) {
    agentConfig.value[key] = value
  }

  /**
   * 更新智能体配置（支持批量更新）
   */
  function updateAgentConfig(updates) {
    Object.assign(agentConfig.value, updates)
  }

  /**
   * 获取工具列表
   */
  async function fetchTools() {
    isLoadingTools.value = true
    error.value = null

    try {
      const response = await agentApi.getTools(selectedAgentId.value)
      availableTools.value = response.tools
    } catch (err) {
      console.error('Failed to fetch tools:', err)
      handleChatError(err, 'fetch')
      error.value = err.message
      throw err
    } finally {
      isLoadingTools.value = false
    }
  }

  /**
   * 清除错误状态
   */
  function clearError() {
    error.value = null
  }

  /**
   * 重置 store 状态
   */
  function reset() {
    agents.value = []
    selectedAgentId.value = null
    defaultAgentId.value = null
    agentConfig.value = {}
    originalAgentConfig.value = {}
    availableTools.value = []
    isLoadingAgents.value = false
    isLoadingConfig.value = false
    isLoadingTools.value = false
    error.value = null
    isInitialized.value = false
  }

  return {
    // 状态
    agents,
    selectedAgentId,
    defaultAgentId,
    agentConfig,
    originalAgentConfig,
    availableTools,
    isLoadingAgents,
    isLoadingConfig,
    isLoadingTools,
    error,
    isInitialized,

    // 计算属性
    selectedAgent,
    defaultAgent,
    agentsList,
    isDefaultAgent,
    configurableItems,
    hasConfigChanges,

    // 方法
    initialize,
    fetchAgents,
    fetchDefaultAgent,
    setDefaultAgent,
    selectAgent,
    loadAgentConfig,
    saveAgentConfig,
    resetAgentConfig,
    updateConfigItem,
    updateAgentConfig,
    fetchTools,
    clearError,
    reset
  }
}, {
  // 持久化配置
  persist: {
    key: 'agent-store',
    storage: localStorage,
    paths: ['selectedAgentId', 'defaultAgentId']
  }
})
