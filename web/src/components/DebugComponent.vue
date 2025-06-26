<template>
  <div :class="['log-viewer', { fullscreen: state.isFullscreen }]" ref="logViewer">
    <div class="control-panel">
      <div class="button-group">
        <a-button @click="fetchLogs" :loading="state.fetching">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
        <a-button @click="clearLogs">
          <template #icon><ClearOutlined /></template>
          清空
        </a-button>
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
      </div>
      <div class="filter-group">
        <a-input-search
          v-model:value="state.searchText"
          placeholder="搜索日志..."
          style="width: 200px; height: 32px;"
          @search="onSearch"
        />
        <div class="log-level-selector">
          <div class="multi-select-cards">
            <div
              v-for="level in logLevels"
              :key="level.value"
              class="option-card"
              :class="{
                'selected': isLogLevelSelected(level.value),
                'unselected': !isLogLevelSelected(level.value)
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
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated, onUnmounted, nextTick, reactive, computed } from 'vue';
import { useConfigStore } from '@/stores/config';
import { useUserStore } from '@/stores/user';
import { useDatabaseStore } from '@/stores/database';
import { useThrottleFn } from '@vueuse/core';
import { message } from 'ant-design-vue';
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
  RobotOutlined
} from '@ant-design/icons-vue';
import dayjs from 'dayjs';
import { logApi, systemConfigApi } from '@/apis/admin_api';
import { chatApi } from '@/apis/auth_api';

const configStore = useConfigStore()
const userStore = useUserStore();
const databaseStore = useDatabaseStore();
const config = configStore.config;

// 权限检查
const checkAdminPermission = () => {
  if (!userStore.isAdmin) {
    message.error('需要管理员权限才能查看日志');
    return false;
  }
  return true;
};

// 定义日志级别
const logLevels = [
  { value: 'INFO', label: 'INFO' },
  { value: 'ERROR', label: 'ERROR' },
  { value: 'DEBUG', label: 'DEBUG' },
  { value: 'WARNING', label: 'WARNING' }
];

const logViewer = ref(null);

// 状态管理
const state = reactive({
  fetching: false,
  autoRefresh: false,
  searchText: '',
  selectedLevels: logLevels.map(l => l.value),
  rawLogs: [],
  isFullscreen: false,
});

const logs = ref('');
const error = ref('');
const logContainer = ref(null);
let autoRefreshInterval = null;

// 解析日志行
const parseLogLine = (line) => {
  // 支持两种时间戳格式：带毫秒和不带毫秒
  const match = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d{3})?)\s*-\s*(\w+)\s*-\s*([^-]+?)\s*-\s*(.+)$/);
  if (match) {
    return {
      timestamp: match[1],
      level: match[2],
      module: match[3].trim(),
      message: match[4].trim(),
      raw: line
    };
  }
  return null;
};

// 格式化时间戳
const formatTimestamp = (timestamp) => {
  try {
    // 处理带毫秒的格式：将 "2025-03-10 08:26:37,269" 转换为 "2025-03-10 08:26:37.269"
    let normalizedTimestamp = timestamp.replace(',', '.');

    // 如果没有毫秒，添加 .000
    if (!/\.\d{3}$/.test(normalizedTimestamp)) {
      normalizedTimestamp += '.000';
    }

    const date = dayjs(normalizedTimestamp);
    return date.isValid() ? date.format('HH:mm:ss.SSS') : timestamp;
  } catch (err) {
    console.error('时间戳格式化错误:', err);
    return timestamp;
  }
};

// 处理日志显示
const processedLogs = computed(() => {
  return state.rawLogs
    .map(parseLogLine)
    .filter(log => log !== null)
    .filter(log => state.selectedLevels.includes(log.level))
    .filter(log => {
      if (!state.searchText) return true;
      return log.raw.toLowerCase().includes(state.searchText.toLowerCase());
    });
});

// 获取日志数据
const fetchLogs = async () => {
  if (!checkAdminPermission()) return;

  state.fetching = true;
  try {
    error.value = '';
    const logData = await logApi.getLogs();
    state.rawLogs = logData.log.split('\n').filter(line => line.trim());

    await nextTick();
    const scrollToBottom = useThrottleFn(() => {
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight;
      }
    }, 100);
    scrollToBottom();
  } catch (err) {
    error.value = `错误: ${err.message}`;
  } finally {
    state.fetching = false;
  }
};

// 清空日志
const clearLogs = () => {
  if (!checkAdminPermission()) return;
  state.rawLogs = [];
};

// 搜索功能
const onSearch = () => {
  // 搜索会通过computed自动触发
};

// 过滤日志
const filterLogs = () => {
  // 过滤会通过computed自动触发
};

// 日志级别选择相关方法
const isLogLevelSelected = (level) => {
  return state.selectedLevels.includes(level);
};

const toggleLogLevel = (level) => {
  const currentLevels = [...state.selectedLevels];
  const index = currentLevels.indexOf(level);

  if (index > -1) {
    currentLevels.splice(index, 1);
  } else {
    currentLevels.push(level);
  }

  state.selectedLevels = currentLevels;
};

// 自动刷新
const toggleAutoRefresh = (value) => {
  if (!checkAdminPermission()) return;

  if (value) {
    autoRefreshInterval = setInterval(fetchLogs, 5000);
    state.autoRefresh = true;
  } else {
    if (autoRefreshInterval) {
      clearInterval(autoRefreshInterval);
      autoRefreshInterval = null;
    }
    state.autoRefresh = false;
  }
};

// 全屏切换
const toggleFullscreen = async () => {
  if (!checkAdminPermission()) return;

  try {
    if (!state.isFullscreen) {
      if (logViewer.value.requestFullscreen) {
        await logViewer.value.requestFullscreen();
      } else if (logViewer.value.webkitRequestFullscreen) {
        await logViewer.value.webkitRequestFullscreen();
      } else if (logViewer.value.msRequestFullscreen) {
        await logViewer.value.msRequestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        await document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        await document.webkitExitFullscreen();
      } else if (document.msExitFullscreen) {
        await document.msExitFullscreen();
      }
    }
  } catch (err) {
    console.error('全屏切换失败:', err);
  }
};

// 监听全屏变化
const handleFullscreenChange = () => {
  state.isFullscreen = Boolean(
    document.fullscreenElement ||
    document.webkitFullscreenElement ||
    document.msFullscreenElement
  );
};

onMounted(() => {
  if (checkAdminPermission()) {
    fetchLogs();
  }
  document.addEventListener('fullscreenchange', handleFullscreenChange);
  document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
  document.addEventListener('msfullscreenchange', handleFullscreenChange);
});

onActivated(() => {
  if (!checkAdminPermission()) return;

  if (state.autoRefresh) {
    toggleAutoRefresh(true);
  } else {
    fetchLogs();
  }
});

onUnmounted(() => {
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval);
    autoRefreshInterval = null;
  }
  document.removeEventListener('fullscreenchange', handleFullscreenChange);
  document.removeEventListener('webkitfullscreenchange', handleFullscreenChange);
  document.removeEventListener('msfullscreenchange', handleFullscreenChange);
});

// 打印系统配置
const printSystemConfig = () => {
  if (!checkAdminPermission()) return;
  console.log('=== 系统配置 ===');
  console.log(config);
};

// 打印用户信息
const printUserInfo = () => {
  if (!checkAdminPermission()) return;
  console.log('=== 用户信息 ===');
  const userInfo = {
    token: userStore.token ? '*** (已隐藏)' : null,
    userId: userStore.userId,
    username: userStore.username,
    userRole: userStore.userRole,
    isLoggedIn: userStore.isLoggedIn,
    isAdmin: userStore.isAdmin,
    isSuperAdmin: userStore.isSuperAdmin
  };
  console.log(JSON.stringify(userInfo, null, 2));
};

// 打印知识库信息
const printDatabaseInfo = async () => {
  if (!checkAdminPermission()) return;

  try {
    console.log('=== 知识库信息 ===');

    // 直接调用API获取最新的数据库信息
    await databaseStore.refreshDatabase();

  } catch (error) {
    console.error('获取知识库信息失败:', error);
    message.error('获取知识库信息失败: ' + error.message);
  }
};

// 打印智能体配置
const printAgentConfig = async () => {
  if (!checkAdminPermission()) return;

  try {
    console.log('=== 智能体配置 ===');

    // 获取智能体列表
    const agentsData = await chatApi.getAgents();
    console.log('智能体列表:', JSON.stringify(agentsData.agents, null, 2));

    // 获取默认智能体
    const defaultAgent = await chatApi.getDefaultAgent();
    console.log('默认智能体:', JSON.stringify(defaultAgent, null, 2));

    // 获取每个智能体的配置
    for (const agent of agentsData.agents) {
      try {
        const agentConfig = await systemConfigApi.getAgentConfig(agent.name);
        console.log(`智能体 "${agent.name}" 配置:`, JSON.stringify(agentConfig, null, 2));
      } catch (err) {
        console.log(`智能体 "${agent.name}" 配置获取失败:`, err.message);
      }
    }

  } catch (error) {
    console.error('获取智能体配置失败:', error);
    message.error('获取智能体配置失败: ' + error.message);
  }
};
</script>

<style scoped>
.log-viewer {
  background: white;
}

.log-viewer.fullscreen {
  padding: 16px;
}

.control-panel {
  margin-bottom: 16px;
  padding: 16px;
  background: var(--gray-50);
  border-radius: 8px;
  border: 1px solid var(--gray-200);
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

    &:hover {
      border-color: var(--main-color);
      color: var(--main-color);
    }

    &.ant-btn-primary {
      background-color: var(--main-color);
      border-color: var(--main-color);

      &:hover {
        background-color: var(--main-600);
        border-color: var(--main-600);
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
    color:white;
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
  color: var(--error-color);
}

.log-container {
  height: calc(80vh - 200px);
  overflow-y: auto;
  background: #0C0C0C;
  color: #D1D1D1;
  border-radius: 5px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
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
  color: #6A9955;
  min-width: 80px;
}

.level {
  min-width: 40px;
  font-weight: bold;
}

.module {
  color: #569CD6;
  min-width: 30px;
}

.message {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-all;
}

.level-info {
  .level { color: #4EC9B0; }
}

.level-error {
  .level { color: #F14C4C; }
}

.level-debug {
  .level { color: #9CDCFE; }
}

.level-warning {
  .level { color: #DCD900; }
}

.empty-logs {
  padding: 16px;
  text-align: center;
  color: #666;
}

@media (prefers-color-scheme: dark) {
  .log-container {
    background: #1E1E1E;
  }
}

:fullscreen .log-container {
  height: calc(100vh - 160PX);
}

:-webkit-full-screen .log-container {
  height: calc(100vh - 160PX);
}

:-ms-fullscreen .log-container {
  height: calc(100vh - 160PX);
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
