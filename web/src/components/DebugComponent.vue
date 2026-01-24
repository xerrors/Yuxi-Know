<template>
  <a-modal
    v-model:open="showModal"
    title="调试面板（请在生产环境中谨慎使用）"
    width="90%"
    :footer="null"
    :maskClosable="true"
    :destroyOnClose="true"
    class="debug-modal"
  >
    <div :class="['log-viewer', { fullscreen: state.isFullscreen }]" ref="logViewer">
      <div class="control-panel">
        <div class="button-group">
          <a-button
            @click="fetchLogs"
            :loading="state.fetching"
            :icon="h(ReloadOutlined)"
            class="icon-only"
          >
          </a-button>
          <a-button @click="clearLogs" :icon="h(ClearOutlined)" class="icon-only"> </a-button>
          <a-button @click="printSystemConfig">
            <template #icon><SettingOutlined /></template>
            系统配置
          </a-button>
          <a-button @click="printUserInfo">
            <template #icon><UserOutlined /></template>
            用户信息
          </a-button>
          <a-button @click="printDatabaseInfo">
            <template #icon><DatabaseOutlined /></template>
            知识库信息
          </a-button>
          <a-button @click="printAgentConfig">
            <template #icon><RobotOutlined /></template>
            智能体配置
          </a-button>
          <a-button @click="toggleDebugMode" :type="infoStore.debugMode ? 'primary' : 'default'">
            <template #icon><BugOutlined /></template>
            Debug 模式: {{ infoStore.debugMode ? '开启' : '关闭' }}
          </a-button>
          <a-button @click="toggleFullscreen">
            <template #icon>
              <FullscreenOutlined v-if="!state.isFullscreen" />
              <FullscreenExitOutlined v-else />
            </template>
            {{ state.isFullscreen ? '退出全屏' : '全屏' }}
          </a-button>
          <a-tooltip :title="state.autoRefresh ? '点击停止自动刷新' : '点击开启自动刷新'">
            <a-button
              :type="state.autoRefresh ? 'primary' : 'default'"
              :class="{ 'auto-refresh-button': state.autoRefresh }"
              @click="toggleAutoRefresh(!state.autoRefresh)"
            >
              <template #icon>
                <SyncOutlined :spin="state.autoRefresh" />
              </template>
              自动刷新
              <span v-if="state.autoRefresh" class="refresh-interval">(5s)</span>
            </a-button>
          </a-tooltip>
          <a-button @click="openUserSwitcher">
            <template #icon><SwapOutlined /></template>
            切换用户
          </a-button>
        </div>
        <div class="filter-group">
          <a-input-search
            v-model:value="state.searchText"
            placeholder="搜索日志..."
            style="width: 200px; height: 32px"
            @search="onSearch"
          />
          <div class="log-level-selector">
            <div class="multi-select-cards">
              <div
                v-for="level in logLevels"
                :key="level.value"
                class="option-card"
                :class="{
                  selected: isLogLevelSelected(level.value),
                  unselected: !isLogLevelSelected(level.value)
                }"
                @click="toggleLogLevel(level.value)"
              >
                <div class="option-content">
                  <span class="option-text">{{ level.label }}</span>
                  <div class="option-indicator">
                    <CheckCircleOutlined v-if="isLogLevelSelected(level.value)" />
                    <PlusCircleOutlined v-else />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div ref="logContainer" class="log-container">
        <div v-if="processedLogs.length" class="log-lines">
          <div
            v-for="(log, index) in processedLogs"
            :key="index"
            :class="['log-line', `level-${log.level.toLowerCase()}`]"
          >
            <span class="timestamp">{{ formatTimestamp(log.timestamp) }}</span>
            <span class="level">{{ log.level }}</span>
            <span class="module">{{ log.module }}</span>
            <span class="message">{{ log.message }}</span>
          </div>
        </div>
        <div v-else class="empty-logs">暂无日志</div>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <!-- 用户切换 Modal -->
      <a-modal
        v-model:open="state.showUserSwitcher"
        title="切换用户"
        :confirmLoading="state.switchingUser"
        :footer="null"
        :bodyStyle="{ padding: '12px' }"
      >
        <a-list item-layout="horizontal" :data-source="state.users">
          <template #renderItem="{ item }">
            <a-list-item @click="switchToUser(item)" style="cursor: pointer">
              <a-list-item-meta :title="item.username" :description="item.role" />
            </a-list-item>
          </template>
          <template #empty>
            <a-empty description="暂无用户" />
          </template>
        </a-list>
      </a-modal>
    </div>
  </a-modal>
</template>

<script setup>
import {
  ref,
  reactive,
  computed,
  defineModel,
  onMounted,
  onActivated,
  onUnmounted,
  nextTick,
  toRaw,
  h,
  watch
} from 'vue'

const showModal = defineModel('show')

// 监听 showModal 变化，当打开时获取日志
watch(showModal, (isOpen) => {
  if (isOpen) {
    // 延迟一下确保 DOM 渲染完成
    setTimeout(fetchLogs, 100)
  }
})

import { useConfigStore } from '@/stores/config'
import { useUserStore } from '@/stores/user'
import { useDatabaseStore } from '@/stores/database'
import { useAgentStore } from '@/stores/agent'
import { useInfoStore } from '@/stores/info'
import { useThrottleFn } from '@vueuse/core'
import {
  message,
  Modal,
  List as AList,
  ListItem as AListItem,
  ListItemMeta as AListItemMeta,
  Empty as AEmpty
} from 'ant-design-vue'
import {
  FullscreenOutlined,
  FullscreenExitOutlined,
  ReloadOutlined,
  ClearOutlined,
  SettingOutlined,
  SyncOutlined,
  CheckCircleOutlined,
  PlusCircleOutlined,
  UserOutlined,
  DatabaseOutlined,
  RobotOutlined,
  BugOutlined,
  SwapOutlined
} from '@ant-design/icons-vue'
import dayjs from '@/utils/time'
import { configApi } from '@/apis/system_api'
import { checkSuperAdminPermission } from '@/stores/user'

const configStore = useConfigStore()
const userStore = useUserStore()
const databaseStore = useDatabaseStore()
const agentStore = useAgentStore()
const infoStore = useInfoStore()
const config = configStore.config

// 定义日志级别
const logLevels = [
  { value: 'INFO', label: 'INFO' },
  { value: 'ERROR', label: 'ERROR' },
  { value: 'DEBUG', label: 'DEBUG' },
  { value: 'WARNING', label: 'WARNING' }
]

const logViewer = ref(null)

// 状态管理
const state = reactive({
  fetching: false,
  autoRefresh: false,
  searchText: '',
  selectedLevels: logLevels.map((l) => l.value),
  rawLogs: [],
  isFullscreen: false,
  showUserSwitcher: false,
  users: [],
  switchingUser: false
})

const error = ref('')
const logContainer = ref(null)
let autoRefreshInterval = null

// 解析日志行
const parseLogLine = (line) => {
  // 支持两种时间戳格式：带毫秒和不带毫秒
  const match = line.match(
    /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d{3})?)\s*-\s*(\w+)\s*-\s*([^-]+?)\s*-\s*(.+)$/
  )
  if (match) {
    return {
      timestamp: match[1],
      level: match[2],
      module: match[3].trim(),
      message: match[4].trim(),
      raw: line
    }
  }
  return null
}

// 格式化时间戳
const formatTimestamp = (timestamp) => {
  try {
    // 处理带毫秒的格式：将 "2025-03-10 08:26:37,269" 转换为 "2025-03-10 08:26:37.269"
    let normalizedTimestamp = timestamp.replace(',', '.')

    // 如果没有毫秒，添加 .000
    if (!/\.\d{3}$/.test(normalizedTimestamp)) {
      normalizedTimestamp += '.000'
    }

    const date = dayjs(normalizedTimestamp)
    return date.isValid() ? date.format('HH:mm:ss.SSS') : timestamp
  } catch (err) {
    console.error('时间戳格式化错误:', err)
    return timestamp
  }
}

// 处理日志显示
const processedLogs = computed(() => {
  return state.rawLogs
    .map(parseLogLine)
    .filter((log) => log !== null)
    .filter((log) => {
      if (!state.searchText) return true
      return log.raw.toLowerCase().includes(state.searchText.toLowerCase())
    })
})

// 获取日志数据
const fetchLogs = async () => {
  if (!checkSuperAdminPermission()) return

  state.fetching = true
  try {
    error.value = ''
    // 将选中的日志级别转换为逗号分隔的字符串传递给后端
    const levelsParam = state.selectedLevels.join(',')
    const logData = await configApi.getLogs(levelsParam)
    state.rawLogs = logData.log.split('\n').filter((line) => line.trim())

    await nextTick()
    const scrollToBottom = useThrottleFn(() => {
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight
      }
    }, 100)
    scrollToBottom()
  } catch (err) {
    error.value = `错误: ${err.message}`
  } finally {
    state.fetching = false
  }
}

// 清空日志
const clearLogs = () => {
  if (!checkSuperAdminPermission()) return
  state.rawLogs = []
}

// 搜索功能
const onSearch = () => {
  // 搜索会通过computed自动触发
}

// 日志级别选择相关方法
const isLogLevelSelected = (level) => {
  return state.selectedLevels.includes(level)
}

const toggleLogLevel = (level) => {
  const currentLevels = [...state.selectedLevels]
  const index = currentLevels.indexOf(level)

  if (index > -1) {
    // 如果取消选中后没有选中的级别，默认全选
    if (currentLevels.length === 1) {
      return
    }
    currentLevels.splice(index, 1)
  } else {
    currentLevels.push(level)
  }

  state.selectedLevels = currentLevels
  // 切换日志级别后重新获取数据
  fetchLogs()
}

// 自动刷新
const toggleAutoRefresh = (value) => {
  if (!checkSuperAdminPermission()) return

  if (value) {
    autoRefreshInterval = setInterval(fetchLogs, 5000)
    state.autoRefresh = true
  } else {
    if (autoRefreshInterval) {
      clearInterval(autoRefreshInterval)
      autoRefreshInterval = null
    }
    state.autoRefresh = false
  }
}

// 全屏切换
const toggleFullscreen = async () => {
  if (!checkSuperAdminPermission()) return

  try {
    if (!state.isFullscreen) {
      if (logViewer.value.requestFullscreen) {
        await logViewer.value.requestFullscreen()
      } else if (logViewer.value.webkitRequestFullscreen) {
        await logViewer.value.webkitRequestFullscreen()
      } else if (logViewer.value.msRequestFullscreen) {
        await logViewer.value.msRequestFullscreen()
      }
    } else {
      if (document.exitFullscreen) {
        await document.exitFullscreen()
      } else if (document.webkitExitFullscreen) {
        await document.webkitExitFullscreen()
      } else if (document.msExitFullscreen) {
        await document.msExitFullscreen()
      }
    }
  } catch (err) {
    console.error('全屏切换失败:', err)
  }
}

// 监听全屏变化
const handleFullscreenChange = () => {
  state.isFullscreen = Boolean(
    document.fullscreenElement || document.webkitFullscreenElement || document.msFullscreenElement
  )
}

onMounted(() => {
  document.addEventListener('fullscreenchange', handleFullscreenChange)
  document.addEventListener('webkitfullscreenchange', handleFullscreenChange)
  document.addEventListener('msfullscreenchange', handleFullscreenChange)
})

onActivated(() => {
  if (state.autoRefresh) {
    toggleAutoRefresh(true)
  } else if (showModal.value) {
    fetchLogs()
  }
})

onUnmounted(() => {
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval)
    autoRefreshInterval = null
  }
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  document.removeEventListener('webkitfullscreenchange', handleFullscreenChange)
  document.removeEventListener('msfullscreenchange', handleFullscreenChange)
})

// 打印系统配置
const printSystemConfig = () => {
  if (!checkSuperAdminPermission()) return
  console.log('=== 系统配置 ===')
  console.log(config)
}

// 打印用户信息
const printUserInfo = () => {
  if (!checkSuperAdminPermission()) return
  console.log('=== 用户信息 ===')
  const userInfo = {
    token: userStore.token ? '*** (已隐藏)' : null,
    userId: userStore.userId,
    username: userStore.username,
    userIdLogin: userStore.userIdLogin,
    phoneNumber: userStore.phoneNumber,
    avatar: userStore.avatar,
    userRole: userStore.userRole,
    isLoggedIn: userStore.isLoggedIn,
    isAdmin: userStore.isAdmin,
    isSuperAdmin: userStore.isSuperAdmin
  }
  console.log(JSON.stringify(userInfo, null, 2))
}

// 打印知识库信息
const printDatabaseInfo = async () => {
  if (!checkSuperAdminPermission()) return

  try {
    console.log('=== 知识库信息 ===')
    console.log('基本信息:', {
      databaseId: databaseStore.databaseId,
      databaseName: databaseStore.database.name,
      databaseDesc: databaseStore.database.description,
      fileCount: Object.keys(databaseStore.database.files || {}).length
    })

    console.log('状态信息:', {
      databaseLoading: databaseStore.state.databaseLoading,
      refrashing: databaseStore.state.refrashing,
      searchLoading: databaseStore.state.searchLoading,
      lock: databaseStore.state.lock,
      autoRefresh: databaseStore.state.autoRefresh,
      queryParamsLoading: databaseStore.state.queryParamsLoading
    })

    console.log('查询参数:', {
      queryParams: databaseStore.queryParams,
      meta: databaseStore.meta,
      selectedFileCount: databaseStore.selectedRowKeys.length
    })
  } catch (error) {
    console.error('获取知识库信息失败:', error)
    message.error('获取知识库信息失败: ' + error.message)
  }
}

// 切换Debug模式
const toggleDebugMode = () => {
  if (!checkSuperAdminPermission()) return
  infoStore.toggleDebugMode()
}

// 打印智能体配置
const printAgentConfig = async () => {
  if (!checkSuperAdminPermission()) return

  try {
    console.log('=== 智能体配置信息 ===')

    // Store状态信息
    console.log('Store 状态:', {
      isInitialized: agentStore.isInitialized,
      selectedAgentId: agentStore.selectedAgentId,
      defaultAgentId: agentStore.defaultAgentId,
      agentCount: agentStore.agentsList.length,
      loadingStates: {
        isLoadingAgents: agentStore.isLoadingAgents,
        isLoadingConfig: agentStore.isLoadingConfig,
        isLoadingTools: agentStore.isLoadingTools
      },
      error: agentStore.error,
      hasConfigChanges: agentStore.hasConfigChanges
    })

    // 智能体列表信息
    console.log('智能体列表:', {
      count: agentStore.agentsList.length,
      agents: toRaw(agentStore.agentsList)
    })

    // 当前选中智能体信息
    if (agentStore.selectedAgent) {
      console.log('当前选中智能体:', {
        agent: toRaw(agentStore.selectedAgent),
        isDefault: agentStore.isDefaultAgent,
        configurableItemsCount: Object.keys(agentStore.configurableItems).length
      })

      // 当前智能体配置（仅管理员可见）
      if (userStore.isAdmin) {
        console.log('当前智能体配置:', {
          current: toRaw(agentStore.agentConfig),
          original: toRaw(agentStore.originalAgentConfig),
          hasChanges: agentStore.hasConfigChanges
        })
      } else {
        console.log('智能体配置: 需要管理员权限查看详细配置')
      }
    }

    // 工具信息
    const toolsList = agentStore.availableTools ? Object.values(agentStore.availableTools) : []
    console.log('可用工具:', {
      count: toolsList.length,
      tools: toolsList
    })

    // 配置项信息（管理员可见）
    if (userStore.isAdmin && agentStore.selectedAgent) {
      console.log('可配置项:', toRaw(agentStore.configurableItems))
    }
  } catch (error) {
    console.error('获取智能体配置失败:', error)
    message.error('获取智能体配置失败: ' + error.message)
  }
}

// 获取用户列表
const fetchUsers = async () => {
  try {
    const response = await fetch('/api/auth/users', {
      headers: userStore.getAuthHeaders()
    })
    if (!response.ok) {
      throw new Error('获取用户列表失败')
    }
    state.users = await response.json()
  } catch (err) {
    message.error(`获取用户列表失败: ${err.message}`)
  }
}

// 打开用户选择器
const openUserSwitcher = () => {
  if (!checkSuperAdminPermission()) return
  state.showUserSwitcher = true
  fetchUsers()
}

// 切换用户
const switchToUser = async (user) => {
  if (!checkSuperAdminPermission()) return

  // 危险操作确认
  Modal.confirm({
    title: '⚠️ 危险操作确认',
    content: `确定要切换为用户 "${user.username}" 吗？此操作将被记录。`,
    okText: '确认切换',
    cancelText: '取消',
    okType: 'danger',
    onOk: async () => {
      state.switchingUser = true
      try {
        const response = await fetch(`/api/auth/impersonate/${user.id}`, {
          method: 'POST',
          headers: userStore.getAuthHeaders()
        })
        if (!response.ok) {
          const error = await response.json()
          throw new Error(error.detail || '切换用户失败')
        }
        const data = await response.json()
        // 设置新 token
        localStorage.setItem('user_token', data.access_token)
        message.success(`已切换用户: ${user.username}`)
        state.showUserSwitcher = false
        // 刷新页面以重新初始化应用
        window.location.reload()
      } catch (err) {
        message.error(`切换失败: ${err.message}`)
      } finally {
        state.switchingUser = false
      }
    }
  })
}
</script>

<style scoped>
.log-viewer.fullscreen {
  padding: 16px;
}

.control-panel {
  margin-bottom: 16px;
}

.button-group {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;

  .ant-btn {
    min-width: 80px;
    height: 32px;
    padding: 4px 12px;
    font-size: 13px;
    border-color: var(--gray-300);
    color: var(--gray-700);

    &.icon-only {
      min-width: 32px;
      padding: 0;
    }

    &:hover {
      border-color: var(--main-color);
      color: var(--main-color);
    }

    &.ant-btn-primary {
      background-color: var(--main-color);
      border-color: var(--main-color);
      color: var(--gray-0);

      &:hover,
      &:focus {
        background-color: var(--main-color);
        border-color: var(--main-color);
        color: var(--gray-0);
      }
    }

    .anticon {
      font-size: 14px;
    }
  }

  .refresh-interval {
    font-size: 12px;
    opacity: 0.8;
    margin-left: 2px;
  }

  .auto-refresh-button {
    color: var(--gray-0);
  }
}

.filter-group {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  flex-wrap: wrap;
  height: 32px;

  @media (max-width: 768px) {
    flex-direction: column;
    gap: 12px;
  }
}

.error {
  color: var(--color-error-500);
}

.log-container {
  height: calc(80vh - 200px);
  overflow-y: auto;
  background: var(--gray-0);
  color: var(--gray-1000);
  border-radius: 5px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}

.log-lines {
  padding: 8px;
}

.log-line {
  padding: 2px 4px;
  display: flex;
  gap: 8px;
  line-height: 1.4;
}

.log-line:hover {
  background: rgba(255, 255, 255, 0.05);
}

.timestamp {
  color: var(--color-success-500);
  min-width: 80px;
}

.level {
  min-width: 40px;
  font-weight: bold;
}

.module {
  color: var(--color-info-500);
  min-width: 30px;
}

.message {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-all;
}

.level-info {
  .level {
    color: var(--color-success-500);
  }
}

.level-error {
  .level {
    color: var(--color-error-500);
  }
}

.level-debug {
  .level {
    color: var(--color-info-500);
  }
}

.level-warning {
  .level {
    color: var(--color-warning-500);
  }
}

.empty-logs {
  padding: 16px;
  text-align: center;
  color: var(--gray-500);
}

@media (prefers-color-scheme: dark) {
  .log-container {
    background: var(--gray-900);
  }
}

:fullscreen .log-container {
  height: calc(100vh - 160px);
}

:-webkit-full-screen .log-container {
  height: calc(100vh - 160px);
}

:-ms-fullscreen .log-container {
  height: calc(100vh - 160px);
}

.multi-select-cards {
  display: flex;
  flex-direction: row;
  gap: 10px;

  .option-card {
    border: 1px solid var(--gray-300);
    border-radius: 6px;
    padding: 0px 10px;
    cursor: pointer;
    transition: all 0.2s ease;
    background: var(--gray-0);
    user-select: none;
    height: 32px;
    display: flex;
    align-items: center;

    &:hover {
      border-color: var(--main-color);
      background: var(--main-5);
    }

    &.selected {
      border-color: var(--main-color);
      background: var(--main-10);

      .option-indicator {
        color: var(--main-color);
      }

      .option-text {
        color: var(--main-color);
        font-weight: 500;
      }
    }

    &.unselected {
      .option-indicator {
        color: var(--gray-400);
      }

      .option-text {
        color: var(--gray-700);
      }
    }

    .option-content {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 6px;
      width: 100%;
    }

    .option-text {
      flex: 1;
      font-size: 12px;
      text-align: center;
    }

    .option-indicator {
      flex-shrink: 0;
      font-size: 14px;
      transition: color 0.2s ease;
    }
  }
}

/* 响应式适配 */
@media (max-width: 768px) {
  .log-level-selector {
    min-width: 280px;
  }

  .multi-select-cards .options-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
