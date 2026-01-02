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
        <a-button
          type="secondary"
          @click="showCreateFolderModal"
          :loading="refreshing"
          :icon="h(FolderAddOutlined)"
          style="margin-left: 8px;"
        >新建文件夹</a-button>
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
          :icon="h(ReloadOutlined)"
          title="刷新"
          class="panel-action-btn"
        />
        <a-button
          type="text"
          @click="toggleSelectionMode"
          :icon="h(CheckSquare)"
          title="多选"
          class="panel-action-btn"
          :class="{ 'active': isSelectionMode }"
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
          选择所有失败的文件
        </a-button>
      </div>
      <div style="display: flex; gap: 4px;">
        <a-button
          v-if="!isLightRAG"
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

    <!-- 新建文件夹模态框 -->
    <a-modal
      v-model:open="createFolderModalVisible"
      title="新建文件夹"
      :confirm-loading="createFolderLoading"
      @ok="handleCreateFolder"
    >
      <a-input
        v-model:value="newFolderName"
        placeholder="请输入文件夹名称"
        @pressEnter="handleCreateFolder"
      />
    </a-modal>

    <a-table
        :columns="columnsCompact"
        :data-source="filteredFiles"
        row-key="file_id"
        class="my-table"
        size="small"
        :pagination="paginationCompact"
        v-model:expandedRowKeys="expandedRowKeys"
        :custom-row="customRow"
        :row-selection="isSelectionMode ? {
          selectedRowKeys: selectedRowKeys,
          onChange: onSelectChange,
          getCheckboxProps: getCheckboxProps
        } : null"
        :locale="{
          emptyText: emptyText
        }">
      <template #bodyCell="{ column, text, record }">
        <div v-if="column.key === 'filename'">
          <template v-if="record.is_folder">
            <span class="folder-row" @click="toggleExpand(record)">
              <component :is="expandedRowKeys.includes(record.file_id) ? h(FolderOpenFilled) : h(FolderFilled)" style="margin-right: 12px; color: #ffb800;" />
              {{ record.filename }}
            </span>
          </template>
          <a-button v-else class="main-btn" type="link" @click="openFileDetail(record)">
            <component :is="getFileIcon(record.displayName || text)" :style="{ marginRight: '6px', color: getFileIconColor(record.displayName || text) }" />
            {{ record.displayName || text }}
          </a-button>
        </div>
        <span v-else-if="column.key === 'type'">
           <span v-if="!record.is_folder" :class="['span-type', text]">{{ text?.toUpperCase() }}</span>
        </span>
        <div v-else-if="column.key === 'status'" style="display: flex; align-items: center; justify-content: flex-end;">
          <template v-if="!record.is_folder">
            <CheckCircleFilled v-if="text === 'done'" style="color: var(--color-success-500);"/>
            <CloseCircleFilled v-else-if="text === 'failed'" style="color: var(--color-error-500);"/>
            <HourglassFilled v-else-if="text === 'processing'" style="color: var(--color-info-500);"/>
            <ClockCircleFilled v-else-if="text === 'waiting'" style="color: var(--color-warning-500);"/>
          </template>
        </div>

        <a-tooltip v-else-if="column.key === 'created_at'" :title="formatRelativeTime(text)" placement="left">
          <span>{{ formatRelativeTime(text) }}</span>
        </a-tooltip>

        <div v-else-if="column.key === 'action'" class="table-row-actions">
          <a-popover placement="bottomRight" trigger="click" overlayClassName="file-action-popover">
            <template #content>
              <div class="file-action-list">
                <template v-if="record.is_folder">
                  <a-button type="text" block @click="showCreateFolderModal(record.file_id)">
                    <template #icon><component :is="h(FolderPlus)" style="width: 14px; height: 14px;" /></template>
                    新建子文件夹
                  </a-button>
                  <a-button type="text" block danger @click="handleDeleteFolder(record)">
                    <template #icon><component :is="h(Trash2)" style="width: 14px; height: 14px;" /></template>
                    删除文件夹
                  </a-button>
                </template>
                <template v-else>
                  <a-button type="text" block @click="handleDownloadFile(record)" :disabled="lock || record.status !== 'done'">
                    <template #icon><component :is="h(Download)" style="width: 14px; height: 14px;" /></template>
                    下载文件
                  </a-button>
                  <a-button v-if="!isLightRAG" type="text" block @click="handleRechunkFile(record)" :disabled="lock || record.status === 'processing' || record.status === 'waiting'">
                    <template #icon><component :is="h(RefreshCw)" style="width: 14px; height: 14px;" /></template>
                    重新分块
                  </a-button>
                  <a-button type="text" block danger @click="handleDeleteFile(record.file_id)" :disabled="lock || record.status === 'processing' || record.status === 'waiting'">
                    <template #icon><component :is="h(Trash2)" style="width: 14px; height: 14px;" /></template>
                    删除文件
                  </a-button>
                </template>
              </div>
            </template>
            <a-button type="text" :icon="h(Ellipsis)" class="action-trigger-btn" />
          </a-popover>
        </div>
        <span v-else>{{ text }}</span>
      </template>
    </a-table>
  </div>
</template>

<script setup>
import { ref, computed, watch, h } from 'vue';
import { useDatabaseStore } from '@/stores/database';
import { message, Modal } from 'ant-design-vue';
import { useUserStore } from '@/stores/user';
import { documentApi } from '@/apis/knowledge_api';
import {
  CheckCircleFilled,
  HourglassFilled,
  CloseCircleFilled,
  ClockCircleFilled,
  PlusOutlined,
  ReloadOutlined,
  FolderFilled,
  FolderAddOutlined,
  FolderOpenFilled,
} from '@ant-design/icons-vue';
import {
  Trash2,
  Download,
  RefreshCw,
  ChevronLast,
  Ellipsis,
  FolderPlus,
  CheckSquare,
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
const isLightRAG = computed(() => store.database?.kb_type?.toLowerCase() === 'lightrag');
const refreshing = computed(() => store.state.refrashing);
const lock = computed(() => store.state.lock);
const batchDeleting = computed(() => store.state.batchDeleting);
const batchRechunking = ref(false);
const autoRefresh = computed(() => store.state.autoRefresh);
const selectedRowKeys = computed({
  get: () => store.selectedRowKeys,
  set: (keys) => store.selectedRowKeys = keys,
});

const isSelectionMode = ref(false);

const expandedRowKeys = ref([]);

// 新建文件夹相关
const createFolderModalVisible = ref(false);
const newFolderName = ref('');
const createFolderLoading = ref(false);
const currentParentId = ref(null);

const showCreateFolderModal = (parentId = null) => {
  newFolderName.value = '';
  // 如果是事件对象（来自顶部按钮点击），则设为null
  if (parentId && typeof parentId === 'object') {
      parentId = null;
  }
  currentParentId.value = parentId;
  createFolderModalVisible.value = true;
};

const toggleExpand = (record) => {
  if (!record.is_folder) return;

  const index = expandedRowKeys.value.indexOf(record.file_id);
  if (index > -1) {
    expandedRowKeys.value.splice(index, 1);
  } else {
    expandedRowKeys.value.push(record.file_id);
  }
};

const toggleSelectionMode = () => {
  isSelectionMode.value = !isSelectionMode.value;
  if (!isSelectionMode.value) {
    selectedRowKeys.value = [];
  }
};

const handleCreateFolder = async () => {
  if (!newFolderName.value.trim()) {
    message.warning('请输入文件夹名称');
    return;
  }

  createFolderLoading.value = true;
  try {
    await documentApi.createFolder(store.databaseId, newFolderName.value, currentParentId.value);
    message.success('创建成功');
    createFolderModalVisible.value = false;
    handleRefresh();
  } catch (error) {
    console.error(error);
    message.error('创建失败: ' + (error.message || '未知错误'));
  } finally {
    createFolderLoading.value = false;
  }
};

// 拖拽相关逻辑
const customRow = (record) => {
  return {
    draggable: true,
    onDragstart: (event) => {
       // 检查是否是真实文件/文件夹（存在于 store 中）
       const files = store.database?.files || {};
       if (!files[record.file_id]) {
           event.preventDefault();
           return;
       }

       event.dataTransfer.setData('application/json', JSON.stringify({
           file_id: record.file_id,
           filename: record.filename
       }));
       event.dataTransfer.effectAllowed = 'move';
       // 可以设置一个更好看的拖拽图像
    },
    onDragover: (event) => {
       // 仅允许放置到真实文件夹中
       if (record.is_folder) {
           const files = store.database?.files || {};
           // 确保是真实的文件夹（有 ID 且在 store 中）
           if (files[record.file_id]) {
               event.preventDefault();
               event.dataTransfer.dropEffect = 'move';
               event.currentTarget.classList.add('drop-over-folder');
           }
       }
    },
    onDragleave: (event) => {
        event.currentTarget.classList.remove('drop-over-folder');
    },
    onDrop: async (event) => {
        event.preventDefault();
        event.currentTarget.classList.remove('drop-over-folder');

        const data = event.dataTransfer.getData('application/json');
        if (!data) return;

        try {
            const { file_id, filename } = JSON.parse(data);
            if (file_id === record.file_id) return;

            // 确认移动
            Modal.confirm({
                title: '移动文件',
                content: `确定要将 "${filename}" 移动到 "${record.filename}" 吗？`,
                onOk: async () => {
                    try {
                        await store.moveFile(file_id, record.file_id);
                    } catch (error) {
                        // error handled in store
                    }
                }
            });
        } catch (e) {
            console.error('Drop error:', e);
        }
    }
  };
};

// 重新分块参数配置相关
const rechunkModalVisible = ref(false);
const rechunkModalLoading = computed(() => store.state.chunkLoading);

const rechunkParams = ref({
  chunk_size: 1000,
  chunk_overlap: 200,
  qa_separator: '\\n\\n\\n'
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
    sorter: (a, b) => {
        if (a.is_folder && !b.is_folder) return -1;
        if (!a.is_folder && b.is_folder) return 1;
        return (a.filename || '').localeCompare(b.filename || '');
    },
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
  { title: '', key: 'action', dataIndex: 'file_id', width: 40, align: 'center' }
];

// 构建文件树
const buildFileTree = (fileList) => {
  const nodeMap = new Map();
  const roots = [];
  const processedIds = new Set();

  // 1. 初始化节点映射，确保 explicit folder 有 children
  fileList.forEach(file => {
    const item = { ...file, displayName: file.filename };
    if (item.is_folder && !item.children) {
      item.children = [];
    }
    nodeMap.set(item.file_id, item);
  });

  // 2. 处理 parent_id (强关联)
  fileList.forEach(file => {
    if (file.parent_id && nodeMap.has(file.parent_id)) {
      const parent = nodeMap.get(file.parent_id);
      const child = nodeMap.get(file.file_id);
      if (parent && child) {
         if (!parent.children) parent.children = [];
         parent.children.push(child);
         processedIds.add(file.file_id);
      }
    }
  });

  // 3. 处理剩余项 (Roots 或 路径解析)
  fileList.forEach(file => {
    if (processedIds.has(file.file_id)) return;

    const item = nodeMap.get(file.file_id);
    const normalizedName = file.filename.replace(/\\/g, '/');
    const parts = normalizedName.split('/');

    if (parts.length === 1) {
      // Root item
      // Check if it's an explicit folder that should merge with an existing implicit one?
      if (item.is_folder) {
         const existingIndex = roots.findIndex(n => n.is_folder && n.filename === item.filename);
         if (existingIndex !== -1) {
             const existing = roots[existingIndex];
             // Merge children from implicit to explicit
             if (existing.children && existing.children.length > 0) {
                 item.children = [...(item.children || []), ...existing.children];
             }
             // Replace implicit with explicit
             roots[existingIndex] = item;
         } else {
             roots.push(item);
         }
      } else {
         roots.push(item);
      }
    } else {
      // Path based logic for files like "A/B.txt"
      let currentLevel = roots;
      let currentPath = '';

      for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i];
        currentPath = currentPath ? `${currentPath}/${part}` : part;

        // Find existing node in currentLevel
        let node = currentLevel.find(n => n.filename === part && n.is_folder);

        if (!node) {
          node = {
            file_id: `folder-${currentPath}`,
            filename: part,
            displayName: part,
            is_folder: true,
            children: [],
            created_at: file.created_at,
            status: 'done',
          };
          currentLevel.push(node);
        }
        currentLevel = node.children;
      }

      const fileName = parts[parts.length - 1];
      item.displayName = fileName;
      currentLevel.push(item);
    }
  });

  // 排序：文件夹在前，文件在后，按名称排序
  const sortNodes = (nodes) => {
    nodes.sort((a, b) => {
      if (a.is_folder && !b.is_folder) return -1;
      if (!a.is_folder && b.is_folder) return 1;
      return (a.filename || '').localeCompare(b.filename || '');
    });
    nodes.forEach(node => {
      if (node.children) sortNodes(node.children);
    });
  };

  sortNodes(roots);
  return roots;
};

// 过滤后的文件列表
const filteredFiles = computed(() => {
  let filtered = files.value;

  // 应用文件名过滤
  if (filenameFilter.value.trim()) {
    const filterText = filenameFilter.value.toLowerCase().trim();
    // 搜索模式下使用扁平列表
    return files.value.filter(file =>
      file.filename && file.filename.toLowerCase().includes(filterText)
    ).map(f => ({ ...f, displayName: f.filename }));
  }

  return buildFileTree(filtered);
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

const onSelectChange = (keys, selectedRows) => {
  // 只保留非文件夹的文件ID
  const fileKeys = selectedRows
    .filter(row => !row.is_folder)
    .map(row => row.file_id);

  selectedRowKeys.value = fileKeys;
};

const getCheckboxProps = (record) => ({
  disabled: lock.value || record.status === 'processing' || record.status === 'waiting' || record.is_folder,
});

const onFilterChange = (e) => {
  filenameFilter.value = e.target.value;
};

const handleDeleteFile = (fileId) => {
  store.handleDeleteFile(fileId);
};

const handleDeleteFolder = (record) => {
    Modal.confirm({
      title: '删除文件夹',
      content: `确定要删除文件夹 "${record.filename}" 及其包含的所有内容吗？`,
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        try {
          await store.deleteFile(record.file_id);
          message.success('删除成功');
        } catch (error) {
          // Error handled in store but we can add extra handling if needed
        }
      },
    });
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
        qa_separator: '\\n\\n\\n'
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
    qa_separator: '\\n\\n\\n'
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
  gap: 0px;

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

.panel-action-btn.active {
  color: var(--main-color);
  background-color: var(--main-10);
}

.action-trigger-btn {
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: var(--gray-500);
  transition: all 0.2s;

  &:hover {
    background-color: var(--gray-100);
    color: var(--main-color);
  }

  svg {
    width: 16px;
    height: 16px;
  }
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

.folder-row {
  display: flex;
  align-items: center;
  cursor: pointer;

  &:hover {
    color: var(--main-color);
  }
}

:deep(.drop-over-folder) {
  background-color: var(--primary-50) !important;
  outline: 2px dashed var(--main-color);
  outline-offset: -2px;
  z-index: 10;

  td {
    background-color: transparent !important;
  }
}
</style>

<style lang="less">
.file-action-popover {
  .ant-popover-inner {
    padding: 4px;
  }

  .ant-popover-inner {
    border-radius: 8px;
    border: 1px solid var(--gray-150);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    overflow: hidden;
  }

  .ant-popover-arrow {
    display: none;
  }
}

.file-action-list {
  display: flex;
  flex-direction: column;
  gap: 2px;

  .ant-btn {
    text-align: left;
    height: 36px;
    font-size: 14px;
    display: flex;
    align-items: center;
    border-radius: 6px;
    padding: 0 12px;
    border: none;
    box-shadow: none;

    &:hover {
      background-color: var(--gray-50);
      color: var(--main-color);
    }

    &.ant-btn-dangerous:hover {
      background-color: var(--color-error-50);
      color: var(--color-error-500);
    }

    .anticon, .lucide {
      margin-right: 10px;
    }

    span {
      font-size: 13px;
    }
  }

  .ant-btn:disabled {
    background-color: transparent;
    color: var(--gray-300);
    cursor: not-allowed;
  }
}
</style>
