
import { defineStore } from 'pinia';
import { ref, reactive } from 'vue';
import { message, Modal } from 'ant-design-vue';
import { databaseApi, documentApi, queryApi } from '@/apis/knowledge_api';
import { useTaskerStore } from '@/stores/tasker';
import { useRouter } from 'vue-router';

export const useDatabaseStore = defineStore('database', () => {
  const router = useRouter();
  const taskerStore = useTaskerStore();

  // State
  const database = ref({});
  const databaseId = ref(null);
  const selectedFile = ref(null);

  const queryParams = ref([]);
  const meta = reactive({});
  const graphStats = ref({
    total_nodes: 0,
    total_edges: 0,
    displayed_nodes: 0,
    displayed_edges: 0,
    is_truncated: false,
  });
  const selectedRowKeys = ref([]);

  const state = reactive({
    databaseLoading: false,
    refrashing: false,
    searchLoading: false,
    lock: false,
    fileDetailModalVisible: false,
    fileDetailLoading: false,
    batchDeleting: false,
    chunkLoading: false,
    autoRefresh: false,
    queryParamsLoading: false,
    rightPanelVisible: true,
  });

  let refreshInterval = null;
  let autoRefreshSource = null; // Tracks whether auto-refresh was user-triggered or automatic
  let autoRefreshManualOverride = false; // Indicates user explicitly disabled auto-refresh

  // Actions
  async function getDatabaseInfo(id, skipQueryParams = false) {
    const db_id = id || databaseId.value;
    if (!db_id) return;

    state.lock = true;
    state.databaseLoading = true;
    try {
      const data = await databaseApi.getDatabaseInfo(db_id);
      database.value = data;
      ensureAutoRefreshForProcessing(data?.files);

      // Only load query parameters if explicitly requested or if not loaded yet
      if (!skipQueryParams && queryParams.value.length === 0) {
        await loadQueryParams(db_id);
      }
    } catch (error) {
      console.error(error);
      message.error(error.message || '获取数据库信息失败');
    } finally {
      state.lock = false;
      state.databaseLoading = false;
    }
  }

  async function updateDatabaseInfo(formData) {
    try {
      state.lock = true;
      await databaseApi.updateDatabase(databaseId.value, formData);
      message.success('知识库信息更新成功');
      await getDatabaseInfo(); // Load query params after updating database info
    } catch (error) {
      console.error(error);
      message.error(error.message || '更新失败');
    } finally {
      state.lock = false;
    }
  }

  function deleteDatabase() {
    Modal.confirm({
      title: '删除数据库',
      content: '确定要删除该数据库吗？',
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        state.lock = true;
        try {
          const data = await databaseApi.deleteDatabase(databaseId.value);
          message.success(data.message || '删除成功');
          router.push('/database');
        } catch (error) {
          console.error(error);
          message.error(error.message || '删除失败');
        } finally {
          state.lock = false;
        }
      },
    });
  }

  async function deleteFile(fileId) {
    state.lock = true;
    try {
      await documentApi.deleteDocument(databaseId.value, fileId);
      await getDatabaseInfo(undefined, true); // Skip query params for file deletion
    } catch (error) {
      console.error(error);
      message.error(error.message || '删除失败');
      throw error;
    } finally {
      state.lock = false;
    }
  }

  function handleDeleteFile(fileId) {
    Modal.confirm({
      title: '删除文件',
      content: '确定要删除该文件吗？',
      okText: '确认',
      cancelText: '取消',
      onOk: () => deleteFile(fileId),
    });
  }

  function handleBatchDelete() {
    const files = database.value.files || {};
    const validFileIds = selectedRowKeys.value.filter(fileId => {
      const file = files[fileId];
      return file && !(file.status === 'processing' || file.status === 'waiting');
    });

    if (validFileIds.length === 0) {
      message.info('没有可删除的文件');
      return;
    }

    Modal.confirm({
      title: '批量删除文件',
      content: `确定要删除选中的 ${validFileIds.length} 个文件吗？`,
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        state.batchDeleting = true;
        let successCount = 0;
        let failureCount = 0;
        let progressMessage = message.loading(`正在删除文件 0/${validFileIds.length}`, 0);

        try {
          for (let i = 0; i < validFileIds.length; i++) {
            const fileId = validFileIds[i];
            try {
              await deleteFile(fileId);
              successCount++;
            } catch (error) {
              console.error(`删除文件 ${fileId} 失败:`, error);
              failureCount++;
            }
            progressMessage?.();
            if (i + 1 < validFileIds.length) {
              progressMessage = message.loading(`正在删除文件 ${i + 1}/${validFileIds.length}`, 0);
            }
          }
          progressMessage?.();
          if (successCount > 0 && failureCount === 0) {
            message.success(`成功删除 ${successCount} 个文件`);
          } else if (successCount > 0 && failureCount > 0) {
            message.warning(`成功删除 ${successCount} 个文件，${failureCount} 个文件删除失败`);
          } else if (failureCount > 0) {
            message.error(`${failureCount} 个文件删除失败`);
          }
          selectedRowKeys.value = [];
          await getDatabaseInfo(undefined, true); // Skip query params for batch deletion
        } catch (error) {
          progressMessage?.();
          console.error('批量删除出错:', error);
          message.error('批量删除过程中发生错误');
        } finally {
          state.batchDeleting = false;
        }
      },
    });
  }

  const processingStatuses = new Set(['processing', 'waiting']);

  function enableAutoRefresh(source = 'auto') {
    if (autoRefreshManualOverride && source === 'auto') {
      return;
    }

    if (!state.autoRefresh) {
      state.autoRefresh = true;
      autoRefreshSource = source;
      autoRefreshManualOverride = false;
      startAutoRefresh();
      return;
    }

    if (source === 'auto' && autoRefreshSource !== 'manual') {
      autoRefreshSource = 'auto';
    }
  }

  function ensureAutoRefreshForProcessing(filesMap) {
    const files = Object.values(filesMap || {});
    const hasPending = files.some((file) => file && processingStatuses.has(file.status));
    if (hasPending) {
      enableAutoRefresh('auto');
    } else if (autoRefreshSource === 'auto' && state.autoRefresh) {
      state.autoRefresh = false;
      autoRefreshSource = null;
      autoRefreshManualOverride = false;
      stopAutoRefresh();
    }
    return hasPending;
  }

  async function addFiles({ items, contentType, params }) {
    if (items.length === 0) {
      message.error(contentType === 'file' ? '请先上传文件' : '请输入有效的网页链接');
      return;
    }

    state.chunkLoading = true;
    try {
      const data = await documentApi.addDocuments(databaseId.value, items, { ...params, content_type: contentType });
      if (data.status === 'success' || data.status === 'queued') {
        const itemType = contentType === 'file' ? '文件' : 'URL';
        enableAutoRefresh('auto');
        message.success(data.message || `${itemType}已提交处理，请在任务中心查看进度`);
        if (data.task_id) {
          taskerStore.registerQueuedTask({
            task_id: data.task_id,
            name: `知识库导入 (${databaseId.value || ''})`,
            task_type: 'knowledge_ingest',
            message: data.message,
            payload: {
              db_id: databaseId.value,
              count: items.length,
              content_type: contentType,
            }
          });
        }
        await getDatabaseInfo(undefined, true); // Skip query params when adding files
        return true; // Indicate success
      } else {
        message.error(data.message || '处理失败');
        return false;
      }
    } catch (error) {
      console.error(error);
      message.error(error.message || '处理请求失败');
      return false;
    } finally {
      state.chunkLoading = false;
    }
  }

  async function openFileDetail(record) {
    if (record.status !== 'done') {
      message.error('文件未处理完成，请稍后再试');
      return;
    }
    state.fileDetailModalVisible = true;
    selectedFile.value = { ...record, lines: [] };
    state.fileDetailLoading = true;
    state.lock = true;

    try {
      const data = await documentApi.getDocumentInfo(databaseId.value, record.file_id);
      if (data.status == "failed") {
        message.error(data.message);
        state.fileDetailModalVisible = false;
        return;
      }
      selectedFile.value = { ...record, lines: data.lines || [] };
    } catch (error) {
      console.error(error);
      message.error(error.message);
      state.fileDetailModalVisible = false;
    } finally {
      state.fileDetailLoading = false;
      state.lock = false;
    }
  }

  async function loadQueryParams(id) {
    const db_id = id || databaseId.value;
    if (!db_id) return;

    state.queryParamsLoading = true;
    try {
      const response = await queryApi.getKnowledgeBaseQueryParams(db_id);
      queryParams.value = response.params?.options || [];

      // Create a set of currently supported parameter keys
      const supportedParamKeys = new Set(queryParams.value.map(param => param.key));

      // Remove unsupported parameters from meta
      for (const key in meta) {
        if (key !== 'db_id' && !supportedParamKeys.has(key)) {
          delete meta[key];
        }
      }

      // Add default values for supported parameters that are not in meta
      queryParams.value.forEach(param => {
        if (!(param.key in meta)) {
          meta[param.key] = param.default;
        }
      });
    } catch (error) {
      console.error('Failed to load query params:', error);
      message.error('加载查询参数失败');
    } finally {
      state.queryParamsLoading = false;
    }
  }



  function startAutoRefresh() {
    if (state.autoRefresh && !refreshInterval) {
      refreshInterval = setInterval(() => {
        getDatabaseInfo(undefined, true); // Skip loading query params during auto-refresh
      }, 1000);
    }
  }

  function stopAutoRefresh() {
    if (refreshInterval) {
      clearInterval(refreshInterval);
      refreshInterval = null;
    }
  }

  function toggleAutoRefresh() {
    const nextState = !state.autoRefresh;
    state.autoRefresh = nextState;
    if (nextState) {
      autoRefreshSource = 'manual';
      autoRefreshManualOverride = false;
      startAutoRefresh();
    } else {
      autoRefreshManualOverride = true;
      autoRefreshSource = null;
      stopAutoRefresh();
    }
  }

  function selectAllFailedFiles() {
    const files = Object.values(database.value.files || {});
    const failedFiles = files
      .filter(file => file.status === 'failed')
      .map(file => file.file_id);

    const newSelectedKeys = [...new Set([...selectedRowKeys.value, ...failedFiles])];
    selectedRowKeys.value = newSelectedKeys;

    if (failedFiles.length > 0) {
      message.success(`已选择 ${failedFiles.length} 个失败的文件`);
    } else {
      message.info('当前没有失败的文件');
    }
  }

  return {
    database,
    databaseId,
    selectedFile,
    queryParams,
    meta,
    graphStats,
    selectedRowKeys,
    state,
    getDatabaseInfo,
    updateDatabaseInfo,
    deleteDatabase,
    deleteFile,
    handleDeleteFile,
    handleBatchDelete,
    addFiles,
    openFileDetail,
    loadQueryParams,

    startAutoRefresh,
    stopAutoRefresh,
    toggleAutoRefresh,
    selectAllFailedFiles,
  };
});
