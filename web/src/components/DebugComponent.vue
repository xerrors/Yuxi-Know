<template>
    <div class="log-viewer">
      <a-button @click="fetchLogs">刷新</a-button>
      <div ref="logContainer" class="log-container">
        <pre v-if="logs">{{ logs }}</pre>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </div>
  </template>

  <script setup>
  import { ref, onMounted, onActivated, nextTick } from 'vue';

  // 定义一个 ref 来存储日志数据和错误信息
  const logs = ref('');
  const error = ref('');

  // 定义一个 ref 来获取日志容器的 DOM 元素
  const logContainer = ref(null);

  // 定义一个方法来获取日志数据
  const fetchLogs = async () => {
    try {
      // 清空之前的错误信息
      error.value = '';

      // 发送请求获取日志数据
      const response = await fetch('/api/log'); // 替换为你的 API 路径

      if (!response.ok) {
        throw new Error('Failed to fetch logs');
      }

      // 解析 JSON 数据
      const data = await response.json();

      // 将日志信息赋值给 logs 变量
      logs.value = data.log;

      // 等待 DOM 更新完成后自动滚动到最底部
      await nextTick();
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight;
      }
    } catch (err) {
      // 处理请求错误
      error.value = `Error: ${err.message}`;
    }
  };

  // 组件第一次挂载时自动获取日志并滚动到底部
  onMounted(() => {
    fetchLogs();
    setInterval(fetchLogs, 5000); // 每 5 秒自动刷新一次日志
  });

  // 组件重新激活时（从 keep-alive 缓存恢复）自动获取日志
  onActivated(() => {
    fetchLogs();
  });

  </script>

  <style scoped>
  .log-viewer {}

  .error {
    color: red;
  }

  .log-container {
    max-height: 80vh; /* 设置最大高度 */
    overflow-y: auto; /* 启用垂直滚动 */
    background-color: #f0f0f0;
    margin: 20px 0;
    padding: 10px;
    padding-bottom: 0;
    border-radius: 5px;
    white-space: pre-wrap; /* 使日志内容自动换行 */
    word-wrap: break-word;

    background: #0C0C0C;
    color: #D1D1D1;
  }
  </style>
