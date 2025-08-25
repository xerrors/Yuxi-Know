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
        <a-button
          type="text"
          @click="handleRefresh"
          :loading="refreshing"
          :icon="h(ReloadOutlined)"
          title="刷新"
        />
        <a-button
          @click="toggleAutoRefresh"
          size="small"
          :type="autoRefresh ? 'primary' : 'default'"
          title="自动刷新文件状态"
          class="auto-refresh-btn panel-action-btn"
        >
          Auto
        </a-button>
        <a-input
          v-model:value="filenameFilter"
          placeholder="搜索文件名"
          size="small"
          style="width: 120px; margin-right: 8px; border-radius: 6px; padding: 4px 8px;"
          allow-clear
          @change="onFilterChange"
        />
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

    <div class="batch-actions-compact" v-if="selectedRowKeys.length > 0">
      <div class="batch-info">
        <span>{{ selectedRowKeys.length }} 项</span>
        <a-button
          type="text"
          size="small"
          @click="selectAllFailedFiles"
          :disabled="lock"
          title="选择所有失败的文件"
        >
          选择失败
        </a-button>
      </div>
      <a-button
        type="text"
        danger
        @click="handleBatchDelete"
        :loading="batchDeleting"
        :disabled="!canBatchDelete"
        :icon="h(DeleteOutlined)"
        title="批量删除"
      />
    </div>

    <a-table
        :columns="columnsCompact"
        :data-source="filteredFiles"
        row-key="file_id"
        class="my-table-compact"
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
          <CheckCircleFilled v-if="text === 'done'" style="color: #41A317;"/>
          <CloseCircleFilled v-else-if="text === 'failed'" style="color: #FF4D4F;"/>
          <HourglassFilled v-else-if="text === 'processing'" style="color: #1677FF;"/>
          <ClockCircleFilled v-else-if="text === 'waiting'" style="color: #FFCD43;"/>
        </div>

        <a-tooltip v-else-if="column.key === 'created_at'" :title="formatRelativeTime(Math.round(text*1000))" placement="left">
          <span>{{ formatRelativeTime(Math.round(text*1000)) }}</span>
        </a-tooltip>

        <div v-else-if="column.key === 'action'" style="display: flex; gap: 4px;">
          <a-button class="del-btn" type="text"
            @click="handleDeleteFile(record.file_id)"
            :disabled="lock || record.status === 'processing' || record.status === 'waiting'"
            :icon="h(DeleteOutlined)"
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
import { Modal } from 'ant-design-vue';
import {
  CheckCircleFilled,
  HourglassFilled,
  CloseCircleFilled,
  ClockCircleFilled,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue';
import { ChevronLast } from 'lucide-vue-next';

const store = useDatabaseStore();

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
const autoRefresh = computed(() => store.state.autoRefresh);
const selectedRowKeys = computed({
  get: () => store.selectedRowKeys,
  set: (keys) => store.selectedRowKeys = keys,
});

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
    sorter: (a, b) => (a.created_at || 0) - (b.created_at || 0),
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
  { title: '', key: 'action', dataIndex: 'file_id', width: 40, align: 'center' }
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

const showAddFilesModal = () => {
  emit('showAddFilesModal');
};

const handleRefresh = () => {
  store.getDatabaseInfo();
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

// 选择所有失败的文件
const selectAllFailedFiles = () => {
  store.selectAllFailedFiles();
};

const openFileDetail = (record) => {
  store.openFileDetail(record);
};

// 导入工具函数
import { getFileIcon, getFileIconColor, formatRelativeTime } from '@/utils/file_utils';
</script>

<style scoped>
.file-table-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  flex-shrink: 0;
  padding: 4px 2px;
}

.search-container {
  display: flex;
  align-items: center;

  button {
    padding: 0 8px;
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
}

.batch-actions-compact {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 4px;
  background-color: var(--main-5);
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
  font-size: 11px;
  font-weight: 500;
  color: var(--gray-700);
}

.batch-actions-compact .ant-btn {
  font-size: 11px;
  padding: 0 6px;
  height: 22px;
  border-radius: 3px;
}

.batch-actions-compact .ant-btn:hover {
  background-color: var(--main-20);
  color: var(--main-color);
}

.my-table-compact {
  flex: 1;
  overflow: auto;
  background-color: transparent;
  min-height: 0; /* 让 flex 子项可以正确缩小 */
}

.my-table-compact .main-btn {
  padding: 0;
  height: auto;
  line-height: 1.4;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  text-decoration: none;
}

.my-table-compact .main-btn:hover {
  cursor: pointer;
  color: var(--main-color);
}

.my-table-compact .del-btn {
  color: var(--gray-500);
}

.my-table-compact .del-btn:hover {
  color: var(--error-color);
}

.my-table-compact .del-btn:disabled {
  cursor: not-allowed;
}

.my-table-compact .span-type {
  display: inline-block;
  padding: 1px 5px;
  font-size: 10px;
  font-weight: bold;
  color: white;
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
  border-radius: 6px;
  border: 1px solid var(--gray-300);
  background-color: var(--gray-50);
  color: var(--gray-700);
  transition: all 0.1s ease;

  &.expand {
    transform: scaleX(-1);
  }
}

.panel-action-btn.expanded {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  transform: scaleX(1);
  padding: 4px;
}

.panel-action-btn.auto-refresh-btn.ant-btn-primary {
  background-color: var(--main-color);
  border-color: var(--main-color);
  color: #fff;
}

.panel-action-btn.auto-refresh-btn.ant-btn-primary:hover {
  background-color: var(--main-color) !important;
  color: #fff !important;
}

.panel-action-btn:hover {
  background-color: var(--main-5);
  color: var(--main-color);
}

.panel-action-btn.expanded:hover {
  background-color: var(--main-5);
  border-color: var(--main-color);
  color: var(--main-color);
}

/* Table row selection styling */
:deep(.ant-table-tbody > tr.ant-table-row-selected > td) {
  background-color: var(--main-5);
}

:deep(.ant-table-tbody > tr:hover > td) {
  background-color: var(--main-5);
}
</style>