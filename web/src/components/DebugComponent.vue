<template>
  <div class="log-viewer">
    <div class="button-group">
      <a-button @click="fetchLogs" :loading="state.fetching">刷新</a-button>
      <a-button @click="printConfig">打印配置</a-button>
      <a-switch v-model:checked="state.autoRefresh" @change="toggleAutoRefresh">
        自动刷新
      </a-switch>
    </div>
    <div ref="logContainer" class="log-container">
      <pre v-if="logs">{{ logs }}</pre>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated, onUnmounted, nextTick, reactive } from 'vue';
import { useConfigStore } from '@/stores/config';
import { useThrottleFn } from '@vueuse/core';

const configStore = useConfigStore()
const config = configStore.config;

// 定义一个 ref 来存储日志数据和错误信息
const logs = ref('');
const error = ref('');
const state = reactive({
  fetching: false,
  autoRefresh: false,
})

// 定义一个 ref 来获取日志容器的 DOM 元素
const logContainer = ref(null);

// 定义一个方法来获取日志数据
const fetchLogs = async () => {
  state.fetching = true;
  try {
    error.value = '';
    const response = await fetch('/api/log');
    if (!response.ok) {
      throw new Error('Failed to fetch logs');
    }

    const data = await response.json();
    logs.value = data.log;

    // 使用节流函数优化滚动操作
    await nextTick();
    const scrollToBottom = useThrottleFn(() => {
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight;
      }
    }, 100);
    scrollToBottom();
  } catch (err) {
    // 处理请求错误
    error.value = `Error: ${err.message}`;
  } finally {
    state.fetching = false;
  }
};

// 组件第一次挂载时自动获取日志并滚动到底部
onMounted(() => {
  fetchLogs();
});

// 组件重新激活时（从 keep-alive 缓存恢复）自动获取日志
onActivated(() => {
  if (state.autoRefresh) {
    toggleAutoRefresh(true);
  } else {
    fetchLogs();
  }
});

// 添加自动刷新功能
const toggleAutoRefresh = (value) => {
  if (value) {
    let autoRefreshInterval = setInterval(fetchLogs, 5000);
    state.autoRefresh = true;
  } else {
    clearInterval(autoRefreshInterval);
    state.autoRefresh = false;
  }
};

onUnmounted(() => {
  clearInterval(autoRefreshInterval);
});

// 添加新方法来打印配置信息
const printConfig = () => {
  console.log('Current config:', config);
};

</script>

<style scoped>
.log-viewer {
  background: white;
}

.button-group {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.error {
  color: var(--error-color);
}

.log-container {
  height: calc(100vh - 150px); /* 设置最大高度 */
  overflow-y: auto; /* 启用垂直滚动 */
  background-color: #f6f7f7;
  padding-bottom: 0;
  border-radius: 5px;
  margin-top: 10px;
  white-space: pre-wrap; /* 使日志内容自动换行 */
  word-wrap: break-word;
  font-size: small;

  background: #0C0C0C;
  color: #D1D1D1;

  pre {
    margin: 0;
    padding: 10px;
    height: 100%;
  }

  transition: background-color 0.3s ease;
}

@media (prefers-color-scheme: dark) {
  .log-container {
    background: #1E1E1E;
    color: #D4D4D4;
  }
}
</style>
