<template>
  <a-popover
    v-model:open="visible"
    :title="null"
    placement="bottomRight"
    trigger="click"
    :overlayStyle="{ width: '400px', zIndex: 1030 }"
  >
    <template #content>
      <div class="popover-content">
        <div class="tabs">
          <button
            class="tab"
            :class="{ active: activeTab === 'todos' }"
            @click="activeTab = 'todos'"
            v-if="hasTodos"
          >
            任务 ({{ todoCount }})
          </button>
          <button
            class="tab"
            :class="{ active: activeTab === 'files' }"
            @click="activeTab = 'files'"
            v-if="hasFiles"
          >
            文件 ({{ fileCount }})
          </button>
        </div>
        <div class="tab-content">
          <!-- Todo Display -->
          <div v-if="activeTab === 'todos'" class="todo-display">
            <div v-if="!todos.length" class="empty">
              暂无任务
            </div>
            <div v-else class="todo-list">
              <div
                v-for="(todo, index) in todos"
                :key="index"
                class="todo-item"
              >
                <span class="todo-status" :class="todo.status">
                  {{ todo.status === 'completed' ? '✓' : todo.status === 'in_progress' ? '⟳' : '○' }}
                </span>
                <span class="todo-text">{{ todo.content }}</span>
              </div>
            </div>
          </div>

          <!-- Files Display -->
          <div v-if="activeTab === 'files'" class="files-display">
            <div v-if="!fileCount" class="empty">
              暂无文件
            </div>
            <div v-else class="file-list">
              <div
                v-for="(fileItem, index) in normalizedFiles"
                :key="fileItem.path || index"
                class="file-item"
                @click="showFileContent(fileItem.path, fileItem)"
              >
                <div class="file-info">
                  <div class="file-name">{{ getFileName(fileItem) }}</div>
                  <div class="file-time" v-if="fileItem.modified_at">
                    {{ formatDate(fileItem.modified_at) }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
    <slot></slot>
  </a-popover>

  <!-- 文件内容 Modal -->
  <a-modal
    v-model:open="modalVisible"
    :title="currentFilePath"
    width="80%"
    :footer="null"
    @cancel="closeModal"
  >
    <div class="file-content">
      <pre v-if="Array.isArray(currentFile?.content)">{{ formatContent(currentFile.content) }}</pre>
      <div v-else-if="typeof currentFile?.content === 'string'">{{ currentFile.content }}</div>
      <pre v-else>{{ JSON.stringify(currentFile, null, 2) }}</pre>
    </div>
  </a-modal>
</template>

<script setup>
import { computed, ref, watch } from 'vue';

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  agentState: {
    type: Object,
    default: () => ({})
  }
});

const emit = defineEmits(['update:visible']);

const activeTab = ref('todos');
const modalVisible = ref(false);
const currentFile = ref(null);
const currentFilePath = ref('');

// 计算属性
const visible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value)
});

const todos = computed(() => {
  return props.agentState?.todos || [];
});

const files = computed(() => {
  return props.agentState?.files || [];
});

const hasTodos = computed(() => {
  return todos.value.length > 0;
});

const hasFiles = computed(() => {
  return files.value.length > 0;
});

const todoCount = computed(() => {
  return todos.value.length;
});

// 适配实际数据格式
const normalizedFiles = computed(() => {
  if (!Array.isArray(files.value)) return [];

  const result = [];
  files.value.forEach(item => {
    if (typeof item === 'object' && item !== null) {
      Object.entries(item).forEach(([filePath, fileData]) => {
        result.push({
          path: filePath,
          ...fileData
        });
      });
    }
  });

  return result;
});

const fileCount = computed(() => {
  return normalizedFiles.value.length;
});

// 监听 agentState 变化，自动选择有内容的标签
watch(() => props.agentState, (newState) => {
  if (newState) {
    if (hasFiles.value && !hasTodos.value) {
      activeTab.value = 'files';
    } else {
      activeTab.value = 'todos';
    }
  }
}, { immediate: true });

// 方法
const getFileName = (fileItem) => {
  if (fileItem.path) {
    return fileItem.path.split('/').pop() || fileItem.path;
  }
  return '未知文件';
};

const formatDate = (dateString) => {
  if (!dateString) return '';
  try {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch (error) {
    return dateString;
  }
};

const formatContent = (contentArray) => {
  if (!Array.isArray(contentArray)) return String(contentArray);
  return contentArray.join('\n');
};

const showFileContent = (filePath, fileData) => {
  currentFilePath.value = filePath;
  currentFile.value = fileData;
  modalVisible.value = true;
};

const closeModal = () => {
  modalVisible.value = false;
  currentFile.value = null;
  currentFilePath.value = '';
};
</script>

<style scoped lang="less">
.popover-content {
  padding: 0;
  background: var(--main-0);
  border-radius: 6px;
  overflow: hidden;
}

.tabs {
  display: flex;
  border-bottom: 1px solid var(--gray-200);
  position: relative;
}

.tab {
  padding: 10px 16px;
  border: none;
  background: none;
  color: var(--gray-600);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s ease;
  position: relative;
  border-radius: 6px 6px 0 0;

  &:hover {
    color: var(--main-700);
  }

  &.active {
    color: var(--main-700);

    &::after {
      content: '';
      position: absolute;
      bottom: -1px;
      left: 0;
      right: 0;
      height: 2px;
      background: var(--main-500);
      border-radius: 1px;
    }
  }
}

.tab-content {
  max-height: 400px;
  overflow-y: auto;
  background: var(--main-0);

  /* 自定义滚动条 */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: var(--gray-50);
  }

  &::-webkit-scrollbar-thumb {
    background: var(--gray-300);
    border-radius: 3px;

    &:hover {
      background: var(--gray-400);
    }
  }
}

.todo-display,
.files-display {
  padding: 16px 0;
}

.empty {
  text-align: center;
  color: var(--gray-500);
  padding: 40px 0;
  font-size: 14px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;

  &::before {
    content: '📋';
    font-size: 28px;
    opacity: 0.6;
  }
}

.todo-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: var(--main-5);
  border-radius: 6px;
  border: 1px solid var(--gray-150);
  transition: all 0.15s ease;

  &:hover {
    background: var(--main-10);
    border-color: var(--gray-200);
  }
}

.todo-status {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  margin-top: 2px;
  border-radius: 50%;
  transition: all 0.15s ease;

  &.completed {
    background: var(--stats-success-bg);
    color: var(--stats-success-color);
  }

  &.in_progress {
    background: var(--stats-warning-bg);
    color: var(--stats-warning-color);
  }

  &.pending {
    background: var(--gray-100);
    color: var(--gray-500);
  }
}

.todo-text {
  flex: 1;
  font-size: 14px;
  line-height: 1.5;
  color: var(--gray-1000);
  word-break: break-word;

  .todo-item.completed & {
    color: var(--gray-500);
    text-decoration: line-through;
  }
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.file-item {
  padding: 12px 14px;
  background: var(--main-5);
  border: 1px solid var(--gray-150);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;

  &:hover {
    background: var(--main-10);
    border-color: var(--main-300);
  }
}

.file-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.file-name {
  font-size: 14px;
  color: var(--gray-1000);
  font-family: 'JetBrains Mono', 'Fira Code', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-weight: 500;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-time {
  font-size: 12px;
  color: var(--gray-500);
  font-weight: 400;
  white-space: nowrap;
}

.file-content {
  max-height: 60vh;
  overflow-y: auto;
  background: var(--main-5);
  border-radius: 6px;
  padding: 16px;
  border: 1px solid var(--gray-200);

  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: var(--gray-50);
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--gray-300);
    border-radius: 4px;

    &:hover {
      background: var(--gray-400);
    }
  }

  pre {
    font-family: 'JetBrains Mono', 'Fira Code', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    color: var(--gray-1000);
    background: transparent;
  }
}


/* Modal 样式优化 - shadcn 风格 */
:deep(.ant-modal) {
  z-index: 1050;
}

:deep(.ant-modal-content) {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--gray-200);
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
}

:deep(.ant-modal-header) {
  background: var(--main-5);
  border-bottom: 1px solid var(--gray-200);
  padding: 16px 20px;
}

:deep(.ant-modal-title) {
  font-weight: 600;
  color: var(--gray-1000);
  font-family: 'JetBrains Mono', 'Fira Code', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

:deep(.ant-modal-body) {
  padding: 0;
}

:deep(.ant-modal-close) {
  top: 12px;
  right: 12px;

  .ant-modal-close-x {
    width: 28px;
    height: 28px;
    border-radius: 4px;
    transition: all 0.15s ease;
    color: var(--gray-500);

    &:hover {
      background: var(--gray-100);
      color: var(--gray-700);
    }
  }
}
</style>