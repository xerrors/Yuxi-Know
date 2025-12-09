<template>
  <div class="file-table-container">
    <div class="panel-header">
      <div class="search-container">
        <a-button
          type="secondary"
          @click="showAddFilesModal"
          :loading="refreshing"
          :icon="h(PlusOutlined)"
        >添加文件</a-button>
      </div>
      <div class="panel-actions">
        <a-input
          v-model:value="filenameFilter"
          placeholder="搜索文件名"
          size="small"
          class="action-searcher"
          allow-clear
          @change="onFilterChange"
        />
        <a-button
          type="text"
          @click="handleRefresh"
          :loading="refreshing"
          :icon="h(RefreshCcw)"
          title="刷新"
          class="panel-action-btn"
        />
        <!-- <a-button
          @click="toggleAutoRefresh"
          size="small"
          :type="autoRefresh ? 'primary' : 'default'"
          title="自动刷新文件状态"
          class="auto-refresh-btn panel-action-btn"
        >
          Auto
        </a-button> -->
        <a-button
          type="text"
          @click="toggleRightPanel"
          :icon="h(ChevronLast)"
          title="切换右侧面板"
          class="panel-action-btn expand"
          :class="{ 'expanded': props.rightPanelVisible }"
        />
      </div>
    </div>

    <div class="batch-actions" v-if="selectedRowKeys.length > 0">
      <div class="batch-info">
        <span>{{ selectedRowKeys.length }} 项</span>
        <a-button
          type="link"
          size="small"
          @click="selectAllFailedFiles"
          :disabled="lock"
          title="选择所有失败的文件"
        >
          选择失败
        </a-button>
      </div>
      <div style="display: flex; gap: 4px;">
        <a-button
          type="link"
          @click="handleBatchRechunk"
          :loading="batchRechunking"
          :disabled="!canBatchRechunk"
          :icon="h(RefreshCw)"
          title="批量重新分块"
        />
        <a-button
          type="link"
          danger
          @click="handleBatchDelete"
          :loading="batchDeleting"
          :disabled="!canBatchDelete"
          :icon="h(Trash2)"
          title="批量删除"
        />
      </div>
    </div>

    <!-- 重新分块参数配置模态框 -->
    <a-modal
      v-model:open="rechunkModalVisible"
      title="重新分块参数配置"
      :confirm-loading="rechunkModalLoading"
      width="600px"
    >
      <template #footer>
        <a-button key="back" @click="handleRechunkCancel">取消</a-button>
        <a-button key="submit" type="primary" @click="handleRechunkConfirm">确定</a-button>
      </template>
      <div class="rechunk-params">
        <ChunkParamsConfig
          :temp-chunk-params="rechunkParams"
          :show-qa-split="true"
        />
      </div>
    </a-modal>

    <a-table
        :columns="columnsCompact"
        :data-source="filteredFiles"
        row-key="file_id"
        class="my-table"
        size="small"
        :pagination="paginationCompact"
        :row-selection="{
          selectedRowKeys: selectedRowKeys,
          onChange: onSelectChange,
          getCheckboxProps: getCheckboxProps
        }"
        :locale="{
          emptyText: emptyText
        }">
      <template #bodyCell="{ column, text, record }">
        <a-button v-if="column.key === 'filename'"  class="main-btn" type="link" @click="openFileDetail(record)">
          <component :is="getFileIcon(text)" :style="{ marginRight: '6px', color: getFileIconColor(text) }" />
          {{ text }}
        </a-button>
        <span v-else-if="column.key === 'type'" :class="['span-type', text]">{{ text?.toUpperCase() }}</span>
        <div v-else-if="column.key === 'status'" style="display: flex; align-items: center; justify-content: flex-end;">
          <CheckCircleFilled v-if="text === 'done'" style="color: var(--color-success-500);"/>
          <CloseCircleFilled v-else-if="text === 'failed'" style="color: var(--color-error-500);"/>
          <HourglassFilled v-else-if="text === 'processing'" style="color: var(--color-info-500);"/>
          <ClockCircleFilled v-else-if="text === 'waiting'" style="color: var(--color-warning-500);"/>
        </div>

        <a-tooltip v-else-if="column.key === 'created_at'" :title="formatRelativeTime(text)" placement="left">
          <span>{{ formatRelativeTime(text) }}</span>
        </a-tooltip>

        <div v-else-if="column.key === 'action'" class="table-row-actions">
          <a-button class="download-btn" type="link"
            @click="handleDownloadFile(record)"
            :disabled="lock || record.status !== 'done'"
            :icon="h(Download)"
            title="下载"
            />
          <a-button class="rechunk-btn" type="link"
            @click="handleRechunkFile(record)"
            :disabled="lock || record.status === 'processing' || record.status === 'waiting'"
            :icon="h(RefreshCw)"
            title="重新分块"
            />
          <a-button class="del-btn" type="link"
            @click="handleDeleteFile(record.file_id)"
            :disabled="lock || record.status === 'processing' || record.status === 'waiting'"
            :icon="h(Trash2)"
            title="删除"
            />
        </div>
        <span v-else>{{ text }}</span>
      </template>
    </a-table>
  </div>
</template>

<script setup>
import { ref, computed, watch, h } from 'vue';
import { useDatabaseStore } from '@/stores/database';
import { message } from 'ant-design-vue';
import { useUserStore } from '@/stores/user';
import { documentApi } from '@/apis/knowledge_api';
import {
  CheckCircleFilled,
  HourglassFilled,
  CloseCircleFilled,
  ClockCircleFilled,
  PlusOutlined,
} from '@ant-design/icons-vue';
import {
  Trash2,
  Download,
  RefreshCw,
  ChevronLast,
  RefreshCcw,
} from 'lucide-vue-next';

const store = useDatabaseStore();
const userStore = useUserStore();

const props = defineProps({
  rightPanelVisible: {
    type: Boolean,
    default: true
  },
});

const emit = defineEmits([
  'showAddFilesModal',
  'toggleRightPanel',
]);

const files = computed(() => Object.values(store.database.files || {}));
const refreshing = computed(() => store.state.refrashing);
const lock = computed(() => store.state.lock);
const batchDeleting = computed(() => store.state.batchDeleting);
const batchRechunking = ref(false);
const autoRefresh = computed(() => store.state.autoRefresh);
const selectedRowKeys = computed({
  get: () => store.selectedRowKeys,
  set: (keys) => store.selectedRowKeys = keys,
});

// 重新分块参数配置相关
const rechunkModalVisible = ref(false);
const rechunkModalLoading = computed(() => store.state.chunkLoading);

const rechunkParams = ref({
  chunk_size: 1000,
  chunk_overlap: 200,
  use_qa_split: false,
  qa_separator: '\n\n\n'
});
const currentRechunkFileIds = ref([]);
const isBatchRechunk = ref(false);

// 文件名过滤
const filenameFilter = ref('');

// 紧凑表格列定义
const columnsCompact = [
  {
    title: '文件名',
    dataIndex: 'filename',
    key: 'filename',
    ellipsis: true,
    width: undefined, // 不设置宽度，让它占据剩余空间
    sorter: (a, b) => (a.filename || '').localeCompare(b.filename || ''),
    sortDirections: ['ascend', 'descend']
  },
  {
    title: '时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 120,
    align: 'right',
    sorter: (a, b) => {
      const timeA = parseToShanghai(a.created_at)
      const timeB = parseToShanghai(b.created_at)
      if (!timeA && !timeB) return 0
      if (!timeA) return 1
      if (!timeB) return -1
      return timeA.valueOf() - timeB.valueOf()
    },
    sortDirections: ['ascend', 'descend']
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 60,
    align: 'right',
    sorter: (a, b) => {
      const statusOrder = { 'done': 1, 'processing': 2, 'waiting': 3, 'failed': 4 };
      return (statusOrder[a.status] || 5) - (statusOrder[b.status] || 5);
    },
    sortDirections: ['ascend', 'descend']
  },
  { title: '', key: 'action', dataIndex: 'file_id', width: 80, align: 'center' }
];

// 过滤后的文件列表
const filteredFiles = computed(() => {
  let filtered = files.value;

  // 应用文件名过滤
  if (filenameFilter.value.trim()) {
    const filterText = filenameFilter.value.toLowerCase().trim();
    filtered = files.value.filter(file =>
      file.filename && file.filename.toLowerCase().includes(filterText)
    );
  }

  return filtered;
});

// 空状态文本
const emptyText = computed(() => {
  return filenameFilter.value ? `没有找到包含"${filenameFilter.value}"的文件` : '暂无文件';
});

// 紧凑分页配置
const paginationCompact = ref({
  pageSize: 20,
  current: 1,
  total: 0,
  showSizeChanger: false,
  showTotal: (total) => `${total}`,
  size: 'small',
  showQuickJumper: false,
  onChange: (page, pageSize) => {
    paginationCompact.value.current = page;
    paginationCompact.value.pageSize = pageSize;
    selectedRowKeys.value = [];
  },
});

// 监听过滤后的文件列表变化，更新分页总数
watch(filteredFiles, (newFiles) => {
  paginationCompact.value.total = newFiles.length;
}, { immediate: true });

// 计算是否可以批量删除
const canBatchDelete = computed(() => {
  return selectedRowKeys.value.some(key => {
    const file = filteredFiles.value.find(f => f.file_id === key);
    return file && !(lock.value || file.status === 'processing' || file.status === 'waiting');
  });
});

// 计算是否可以批量重新分块
const canBatchRechunk = computed(() => {
  return selectedRowKeys.value.some(key => {
    const file = filteredFiles.value.find(f => f.file_id === key);
    return file && !(lock.value || file.status === 'processing' || file.status === 'waiting');
  });
});

const showAddFilesModal = () => {
  emit('showAddFilesModal');
};

const handleRefresh = () => {
  store.getDatabaseInfo(undefined, true); // Skip query params for manual refresh
};

const toggleAutoRefresh = () => {
  store.toggleAutoRefresh();
};

const toggleRightPanel = () => {
  console.log(props.rightPanelVisible);
  emit('toggleRightPanel');
};

const onSelectChange = (keys) => {
  selectedRowKeys.value = keys;
};

const getCheckboxProps = (record) => ({
  disabled: lock.value || record.status === 'processing' || record.status === 'waiting',
});

const onFilterChange = (e) => {
  filenameFilter.value = e.target.value;
};

const handleDeleteFile = (fileId) => {
  store.handleDeleteFile(fileId);
};

const handleBatchDelete = () => {
  store.handleBatchDelete();
}

const handleBatchRechunk = async () => {
  const dbId = store.databaseId;
  if (!dbId) {
    console.error('无法获取数据库ID，数据库ID:', store.databaseId);
    message.error('无法获取数据库ID，请刷新页面后重试');
    return;
  }

  if (selectedRowKeys.value.length === 0) {
    message.warning('请选择要重新分块的文件');
    return;
  }

  try {
    // 设置当前重新分块的文件ID
    currentRechunkFileIds.value = [...selectedRowKeys.value];
    isBatchRechunk.value = true;

    // 显示参数配置模态框
    rechunkModalVisible.value = true;
  } catch (error) {
    console.error('批量重新分块操作出错:', error);
    message.error('操作失败，请稍后重试');
  }
};

// 选择所有失败的文件
const selectAllFailedFiles = () => {
  store.selectAllFailedFiles();
};

const openFileDetail = (record) => {
  console.log('openFileDetail', record);
  store.openFileDetail(record);
};

const handleDownloadFile = async (record) => {
  const dbId = store.databaseId;
  if (!dbId) {
    console.error('无法获取数据库ID，数据库ID:', store.databaseId, '记录:', record);
    message.error('无法获取数据库ID，请刷新页面后重试');
    return;
  }

  console.log('开始下载文件:', { dbId, fileId: record.file_id, record });

  try {
    const response = await documentApi.downloadDocument(dbId, record.file_id);

    // 获取文件名
    const contentDisposition = response.headers.get('content-disposition');
    let filename = record.filename;
    if (contentDisposition) {
      // 首先尝试匹配RFC 2231格式 filename*=UTF-8''...
      const rfc2231Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/);
      if (rfc2231Match) {
        try {
          filename = decodeURIComponent(rfc2231Match[1]);
        } catch (error) {
          console.warn('Failed to decode RFC2231 filename:', rfc2231Match[1], error);
        }
      } else {
        // 回退到标准格式 filename="..."
        const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
        if (filenameMatch && filenameMatch[1]) {
          filename = filenameMatch[1].replace(/['"]/g, '');
          // 解码URL编码的文件名
          try {
            filename = decodeURIComponent(filename);
          } catch (error) {
            console.warn('Failed to decode filename:', filename, error);
            // 如果解码失败，使用原文件名
          }
        }
      }
    }

    // 创建blob并下载
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error('下载文件时出错:', error);
    const errorMessage = error.message || '下载失败，请稍后重试';
    message.error(errorMessage);
  }
};

const handleRechunkFile = async (record) => {
  try {
    // 设置当前重新分块的文件ID
    currentRechunkFileIds.value = [record.file_id];
    isBatchRechunk.value = false;

    if (record?.processing_params) {
      rechunkParams.value = {
        ...record?.processing_params
      };
    }

    // 显示参数配置模态框
    rechunkModalVisible.value = true;
  } catch (error) {
    console.error('重新分块操作出错:', error);
    message.error('操作失败，请稍后重试');
  }
};

// 重新分块确认
const handleRechunkConfirm = async () => {
  try {
    // 调用 rechunks 接口
    const result = await store.rechunksFiles({fileIds: currentRechunkFileIds.value, params: rechunkParams.value});
    if (result) {
      currentRechunkFileIds.value = [];
      // 清空选择
      if (isBatchRechunk.value) {
        selectedRowKeys.value = [];
      }
      // 关闭模态框
      rechunkModalVisible.value = false;

      // 重置参数为默认值
      rechunkParams.value = {
        chunk_size: 1000,
        chunk_overlap: 200,
        use_qa_split: false,
        qa_separator: '\n\n\n'
      };
    } else {
      message.error(`重新分块失败: ${result.message}`);
    }
  } catch (error) {
    console.error('重新分块失败:', error);
    const errorMessage = error.message || '重新分块失败，请稍后重试';
    message.error(errorMessage);
  }
};

// 重新分块取消
const handleRechunkCancel = () => {
  rechunkModalVisible.value = false;
  // rechunkModalLoading.value = false;
  currentRechunkFileIds.value = [];
  isBatchRechunk.value = false;
  // 重置参数为默认值
  rechunkParams.value = {
    chunk_size: 1000,
    chunk_overlap: 200,
    use_qa_split: false,
    qa_separator: '\n\n\n'
  };
};

// 导入工具函数
import { getFileIcon, getFileIconColor, formatRelativeTime } from '@/utils/file_utils';
import { parseToShanghai } from '@/utils/time';
import ChunkParamsConfig from '@/components/ChunkParamsConfig.vue';
</script>

<style scoped>
.file-table-container {
  display: flex;
  flex-grow: 1;
  flex-direction: column;
  max-height: 100%;
  background: var(--gray-10);
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--gray-150);
  /* padding-top: 6px; */
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  flex-shrink: 0;
  padding: 4px 4px;
}

.search-container {
  display: flex;
  align-items: center;

  button {
    padding: 0 8px;

    svg {
      width: 16px;
      height: 16px;
    }
  }

  button:hover {
    background-color: var(--gray-50);
    color: var(--main-color);
  }
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 6px;

  .action-searcher {
    width: 120px;
    margin-right: 8px;
    border-radius: 6px;
    padding: 4px 8px;
    border: none;
  }
}

.batch-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 12px;
  background-color: var(--main-10);
  border-radius: 4px;
  margin-bottom: 4px;
  flex-shrink: 0;
}

.batch-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.batch-info span {
  font-size: 12px;
  font-weight: 500;
  color: var(--gray-700);
}

.batch-actions .ant-btn {
  font-size: 12px;
  padding: 0 6px;
  height: 22px;
  border-radius: 3px;

  svg {
    width: 14px;
    height: 14px;
  }
}


.my-table {
  flex: 1;
  overflow: auto;
  background-color: transparent;
  min-height: 0; /* 让 flex 子项可以正确缩小 */
}

.my-table .main-btn {
  padding: 0;
  height: auto;
  line-height: 1.4;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  text-decoration: none;
}

.my-table .main-btn:hover {
  cursor: pointer;
  color: var(--main-color);
}



.my-table .del-btn {
  color: var(--gray-500);
}

.my-table .download-btn {
  color: var(--gray-500);
}

.my-table .download-btn:hover {
  color: var(--main-color);
}

.my-table .rechunk-btn {
  color: var(--gray-500);
}

/* 统一设置表格操作按钮的图标尺寸 */
.my-table .table-row-actions {
  display: flex;
}

.my-table .table-row-actions button {
  display: flex;
  align-items: center;
}

.my-table .table-row-actions button svg {
  width: 16px;
  height: 16px;
}

.my-table .rechunk-btn:hover {
  color: var(--color-warning-500);
}

.my-table .del-btn:hover {
  color: var(--color-error-500);
}

.my-table .del-btn:disabled {
  cursor: not-allowed;
}

.my-table .span-type {
  display: inline-block;
  padding: 1px 5px;
  font-size: 10px;
  font-weight: bold;
  color: var(--gray-0);
  border-radius: 4px;
  text-transform: uppercase;
  opacity: 0.9;
}

.auto-refresh-btn {
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
}

.panel-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  /* border: 1px solid var(--gray-300); */
  /* background-color: var(--gray-50); */
  color: var(--gray-700);
  transition: all 0.1s ease;
  font-size: 12px;

  svg {
    height: 16px;
  }

  &.expand {
    transform: scaleX(-1);
  }

  &.expanded {
    transform: scaleX(1);
  }
}

.panel-action-btn.auto-refresh-btn.ant-btn-primary {
  background-color: var(--main-color);
  border-color: var(--main-color);
  color: var(--gray-0);
}

.panel-action-btn:hover {
  background-color: var(--gray-50);
  color: var(--main-color);
  /* border: 1px solid var(--main-100); */
}


/* Table row selection styling */
:deep(.ant-table-tbody > tr.ant-table-row-selected > td) {
  background-color: var(--main-5);
}

:deep(.ant-table-tbody > tr.ant-table-row-selected.ant-table-row:hover > td) {
  background-color: var(--main-20);
}

:deep(.ant-table-tbody > tr:hover > td) {
  background-color: var(--main-5);
}
</style>
