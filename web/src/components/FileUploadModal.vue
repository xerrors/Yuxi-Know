<template>
  <a-modal
    v-model:open="visible"
    title="添加文件"
    width="800px"
    @cancel="handleCancel"
  >
    <template #footer>
      <a-button key="back" @click="handleCancel">取消</a-button>
      <a-button
        key="submit"
        type="primary"
        @click="chunkData"
        :loading="chunkLoading"
        :disabled="fileList.length === 0"
      >
        添加到知识库
      </a-button>
    </template>

    <div class="add-files-content">
      <div class="upload-header">
        <div class="source-selector">
          <a-segmented
            v-model:value="uploadMode"
            :options="uploadModeOptions"
            size="large"
            class="source-segmented"
            :disabled="true"
          />
        </div>
        <div class="config-controls">
          <a-button
            type="dashed"
            @click="showChunkConfigModal"
            :disabled="isGraphBased"
          >
            <SettingOutlined /> 分块参数 ({{ chunkParams.chunk_size }}/{{ chunkParams.chunk_overlap }})
          </a-button>
        </div>
      </div>

      <div class="ocr-config" v-if="uploadMode === 'file'">
        <a-form layout="horizontal">
          <a-form-item label="使用OCR" name="enable_ocr">
            <div class="ocr-controls">
              <a-select
                v-model:value="chunkParams.enable_ocr"
                :options="enableOcrOptions"
                style="width: 220px; margin-right: 12px;"
                :disabled="ocrHealthChecking"
              />
              <a-button
                size="small"
                type="dashed"
                @click="checkOcrHealth"
                :loading="ocrHealthChecking"
                :icon="h(CheckCircleOutlined)"
              >
                检查OCR服务
              </a-button>
            </div>
            <div class="param-description">
              <div v-if="chunkParams.enable_ocr !== 'disable' && selectedOcrStatus && selectedOcrStatus !== 'healthy'" class="ocr-warning">
                ⚠️ {{ selectedOcrMessage }}
              </div>
              <div v-else-if="chunkParams.enable_ocr !== 'disable' && selectedOcrStatus === 'healthy'" class="ocr-healthy">
                ✅ {{ selectedOcrMessage }}
              </div>
            </div>
          </a-form-item>
        </a-form>
      </div>

            <!-- PDF/图片OCR提醒 -->
      <div v-if="uploadMode === 'file' && hasPdfOrImageFiles && !isOcrEnabled" class="ocr-warning-alert">
        ⚠️ 检测到PDF或图片文件，请启用OCR功能以提取文本内容
      </div>

      <!-- 文件上传区域 -->
      <div class="upload" v-if="uploadMode === 'file'">
        <a-upload-dragger
          class="upload-dragger"
          v-model:fileList="fileList"
          name="file"
          :multiple="true"
          :disabled="chunkLoading"
          :accept="acceptedFileTypes"
          :before-upload="beforeUpload"
          :action="'/api/knowledge/files/upload?db_id=' + databaseId"
          :headers="getAuthHeaders()"
          @change="handleFileUpload"
          @drop="handleDrop"
        >
          <p class="ant-upload-text">点击或者把文件拖拽到这里上传</p>
          <p class="ant-upload-hint">
            支持的文件类型：{{ uploadHint }}
          </p>
          <div class="zip-support-tip" v-if="hasZipFiles">
            📦 zip 包会自动提取 Markdown 文件和图片，图片链接将替换为可访问的 URL
          </div>
        </a-upload-dragger>
      </div>

      <!-- 同名文件提示 -->
      <div v-if="sameNameFiles.length > 0" class="same-name-files-section">
        <div class="same-name-files-header">
          <InfoCircleOutlined />
          <span>当前知识库中已存在以下同名文件：</span>
        </div>
        <div class="same-name-files-list">
          <div v-for="file in sameNameFiles" :key="file.file_id" class="same-name-file-item">
            <div class="same-name-file-info">
              <span class="same-name-file-name">{{ file.filename }}</span>
              <span class="same-name-file-time">{{ formatFileTime(file.created_at) }}</span>
            </div>
            <div class="same-name-file-actions">
              <a-button size="small" type="link" class="download-btn" @click="downloadSameNameFile(file)">
                <template #icon><DownloadOutlined /></template>
                下载
              </a-button>
              <a-button size="small" type="link" danger @click="deleteSameNameFile(file)">
                <template #icon><DeleteOutlined /></template>
                删除
              </a-button>
            </div>
          </div>
        </div>
      </div>

    </div>
  </a-modal>

  <!-- 分块参数配置弹窗 -->
  <a-modal v-model:open="chunkConfigModalVisible" title="分块参数配置" width="500px">
    <template #footer>
      <a-button key="back" @click="chunkConfigModalVisible = false">取消</a-button>
      <a-button key="submit" type="primary" @click="handleChunkConfigSubmit">确定</a-button>
    </template>
    <div class="chunk-config-content">
      <ChunkParamsConfig
        :temp-chunk-params="tempChunkParams"
        :show-qa-split="isQaSplitSupported"
      />
    </div>
  </a-modal>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { message, Upload, Tooltip, Modal } from 'ant-design-vue';
import { useUserStore } from '@/stores/user';
import { useDatabaseStore } from '@/stores/database';
import { ocrApi } from '@/apis/system_api';
import { fileApi, documentApi } from '@/apis/knowledge_api';
import ChunkParamsConfig from '@/components/ChunkParamsConfig.vue';
import {
  FileOutlined,
  LinkOutlined,
  SettingOutlined,
  CheckCircleOutlined,
  InfoCircleOutlined,
  DownloadOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue';
import { h } from 'vue';

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
});

const emit = defineEmits(['update:visible']);

const store = useDatabaseStore();

const DEFAULT_SUPPORTED_TYPES = [
  '.txt',
  '.pdf',
  '.jpg',
  '.jpeg',
  '.md',
  '.docx',
  '.doc',
];

const normalizeExtensions = (extensions) => {
  if (!Array.isArray(extensions)) {
    return [];
  }
  const normalized = extensions
    .map((ext) => (typeof ext === 'string' ? ext.trim().toLowerCase() : ''))
    .filter((ext) => ext.length > 0)
    .map((ext) => (ext.startsWith('.') ? ext : `.${ext}`));

  return Array.from(new Set(normalized)).sort();
};

const supportedFileTypes = ref(normalizeExtensions(DEFAULT_SUPPORTED_TYPES));

const applySupportedFileTypes = (extensions) => {
  const normalized = normalizeExtensions(extensions);
  if (normalized.length > 0) {
    supportedFileTypes.value = normalized;
  } else {
    supportedFileTypes.value = normalizeExtensions(DEFAULT_SUPPORTED_TYPES);
  }
};

const acceptedFileTypes = computed(() => {
  if (!supportedFileTypes.value.length) {
    return '';
  }
  const exts = new Set(supportedFileTypes.value);
  exts.add('.zip');
  return Array.from(exts).join(',');
});

const uploadHint = computed(() => {
  if (!supportedFileTypes.value.length) {
    return '加载中...';
  }
  const exts = new Set(supportedFileTypes.value);
  exts.add('.zip');
  return Array.from(exts).join(', ');
});

const isSupportedExtension = (fileName) => {
  if (!fileName) {
    return true;
  }
  if (!supportedFileTypes.value.length) {
    return true;
  }
  const lastDotIndex = fileName.lastIndexOf('.');
  if (lastDotIndex === -1) {
    return false;
  }
  const ext = fileName.slice(lastDotIndex).toLowerCase();
  return supportedFileTypes.value.includes(ext) || ext === '.zip';
};

const loadSupportedFileTypes = async () => {
  try {
    const data = await fileApi.getSupportedFileTypes();
    applySupportedFileTypes(data?.file_types);
  } catch (error) {
    console.error('获取支持的文件类型失败:', error);
    message.warning('获取支持的文件类型失败，已使用默认配置');
    applySupportedFileTypes(DEFAULT_SUPPORTED_TYPES);
  }
};

onMounted(() => {
  loadSupportedFileTypes();
});

const visible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value)
});

const databaseId = computed(() => store.databaseId);
const kbType = computed(() => store.database.kb_type);
const chunkLoading = computed(() => store.state.chunkLoading);

// 上传模式
const uploadMode = ref('file');
const previousOcrSelection = ref('disable');

const uploadModeOptions = computed(() => [
  {
    value: 'file',
    label: h('div', { class: 'segmented-option' }, [
      h(FileOutlined, { class: 'option-icon' }),
      h('span', { class: 'option-text' }, '上传文件'),
    ]),
  },
  {
    value: 'url',
    label: h(Tooltip, { title: 'URL 文档上传与解析功能已禁用，出于安全考虑，当前版本仅支持文件上传' }, {
      default: () => h('div', { class: 'segmented-option' }, [
        h(LinkOutlined, { class: 'option-icon' }),
        h('span', { class: 'option-text' }, '输入网址'),
      ])
    }),
  },
]);

// 文件列表
const fileList = ref([]);

// 同名文件列表（用于显示提示）
const sameNameFiles = ref([]);


// URL相关功能已移除

// OCR服务健康状态
const ocrHealthStatus = ref({
  onnx_rapid_ocr: { status: 'unknown', message: '' },
  mineru_ocr: { status: 'unknown', message: '' },
  mineru_official: { status: 'unknown', message: '' },
  paddlex_ocr: { status: 'unknown', message: '' }
});

// OCR健康检查状态
const ocrHealthChecking = ref(false);

// 分块参数
const chunkParams = ref({
  chunk_size: 1000,
  chunk_overlap: 200,
  enable_ocr: 'disable',
  use_qa_split: false,
  qa_separator: '\n\n\n',
});

// 分块参数配置弹窗
const chunkConfigModalVisible = ref(false);

// 临时分块参数（用于配置弹窗）
const tempChunkParams = ref({
  chunk_size: 1000,
  chunk_overlap: 200,
  use_qa_split: false,
  qa_separator: '\n\n\n',
});

// 计算属性：是否支持QA分割
const isQaSplitSupported = computed(() => {
  const type = kbType.value?.toLowerCase();
  return type === 'chroma' || type === 'milvus';
});

const isGraphBased = computed(() => {
  const type = kbType.value?.toLowerCase();
  return type === 'lightrag';
});

// 计算属性：是否启用了OCR
const isOcrEnabled = computed(() => {
  return chunkParams.value.enable_ocr !== 'disable';
});

// 上传模式切换相关逻辑已移除

// 计算属性：是否有PDF或图片文件
const hasPdfOrImageFiles = computed(() => {
  if (fileList.value.length === 0) {
    return false;
  }

  const pdfExtensions = ['.pdf'];
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp'];
  const ocrExtensions = [...pdfExtensions, ...imageExtensions];

  return fileList.value.some(file => {
    if (file.status !== 'done') {
      return false;
    }

    const filePath = file.response?.file_path || file.name;
    if (!filePath) {
      return false;
    }

    const ext = filePath.substring(filePath.lastIndexOf('.')).toLowerCase();
    return ocrExtensions.includes(ext);
  });
});

// 计算属性：是否有ZIP文件
const hasZipFiles = computed(() => {
  if (fileList.value.length === 0) {
    return false;
  }

  return fileList.value.some(file => {
    if (file.status !== 'done') {
      return false;
    }

    const filePath = file.response?.file_path || file.name;
    if (!filePath) {
      return false;
    }

    const ext = filePath.substring(filePath.lastIndexOf('.')).toLowerCase();
    return ext === '.zip';
  });
});

// 计算属性：OCR选项
const enableOcrOptions = computed(() => [
  {
    value: 'disable',
    label: '不启用',
    title: '不启用'
  },
  {
    value: 'onnx_rapid_ocr',
    label: getRapidOcrLabel(),
    title: 'ONNX with RapidOCR',
    disabled: ocrHealthStatus.value?.onnx_rapid_ocr?.status === 'unavailable' || ocrHealthStatus.value?.onnx_rapid_ocr?.status === 'error'
  },
  {
    value: 'mineru_ocr',
    label: getMinerULabel(),
    title: 'MinerU OCR',
    disabled: ocrHealthStatus.value?.mineru_ocr?.status === 'unavailable' || ocrHealthStatus.value?.mineru_ocr?.status === 'error'
  },
  {
    value: 'mineru_official',
    label: getMinerUOfficialLabel(),
    title: 'MinerU Official API',
    disabled: ocrHealthStatus.value?.mineru_official?.status === 'unavailable' || ocrHealthStatus.value?.mineru_official?.status === 'error'
  },
  {
    value: 'paddlex_ocr',
    label: getPaddleXLabel(),
    title: 'PaddleX OCR',
    disabled: ocrHealthStatus.value?.paddlex_ocr?.status === 'unavailable' || ocrHealthStatus.value?.paddlex_ocr?.status === 'error'
  },
]);

// 获取当前选中OCR服务的状态
const selectedOcrStatus = computed(() => {
  switch (chunkParams.value.enable_ocr) {
    case 'onnx_rapid_ocr':
      return ocrHealthStatus.value?.onnx_rapid_ocr?.status || 'unknown';
    case 'mineru_ocr':
      return ocrHealthStatus.value?.mineru_ocr?.status || 'unknown';
    case 'mineru_official':
      return ocrHealthStatus.value?.mineru_official?.status || 'unknown';
    case 'paddlex_ocr':
      return ocrHealthStatus.value?.paddlex_ocr?.status || 'unknown';
    default:
      return null;
  }
});

// 获取当前选中OCR服务的状态消息
const selectedOcrMessage = computed(() => {
  switch (chunkParams.value.enable_ocr) {
    case 'onnx_rapid_ocr':
      return ocrHealthStatus.value?.onnx_rapid_ocr?.message || '';
    case 'mineru_ocr':
      return ocrHealthStatus.value?.mineru_ocr?.message || '';
    case 'mineru_official':
      return ocrHealthStatus.value?.mineru_official?.message || '';
    case 'paddlex_ocr':
      return ocrHealthStatus.value?.paddlex_ocr?.message || '';
    default:
      return '';
  }
});

// OCR选项标签生成函数
const getRapidOcrLabel = () => {
  const status = ocrHealthStatus.value?.onnx_rapid_ocr?.status || 'unknown';
  const statusIcons = {
    'healthy': '✅',
    'unavailable': '❌',
    'error': '⚠️',
    'unknown': '❓'
  };
  return `${statusIcons[status] || '❓'} RapidOCR (ONNX)`;
};

const getMinerULabel = () => {
  const status = ocrHealthStatus.value?.mineru_ocr?.status || 'unknown';
  const statusIcons = {
    'healthy': '✅',
    'unavailable': '❌',
    'unhealthy': '⚠️',
    'timeout': '⏰',
    'error': '⚠️',
    'unknown': '❓'
  };
  return `${statusIcons[status] || '❓'} MinerU OCR`;
};

const getMinerUOfficialLabel = () => {
  const status = ocrHealthStatus.value?.mineru_official?.status || 'unknown';
  const statusIcons = {
    'healthy': '✅',
    'unavailable': '❌',
    'unhealthy': '⚠️',
    'timeout': '⏰',
    'error': '⚠️',
    'unknown': '❓'
  };
  return `${statusIcons[status] || '❓'} MinerU Official API`;
};

const getPaddleXLabel = () => {
  const status = ocrHealthStatus.value?.paddlex_ocr?.status || 'unknown';
  const statusIcons = {
    'healthy': '✅',
    'unavailable': '❌',
    'unhealthy': '⚠️',
    'timeout': '⏰',
    'error': '⚠️',
    'unknown': '❓'
  };
  return `${statusIcons[status] || '❓'} PaddleX OCR`;
};

// 验证OCR服务可用性
const validateOcrService = () => {
  if (chunkParams.value.enable_ocr === 'disable') {
    return true;
  }

  const status = selectedOcrStatus.value;
  if (status === 'unavailable' || status === 'error') {
    const ocrMessage = selectedOcrMessage.value;
    message.error(`OCR服务不可用: ${ocrMessage}`);
    return false;
  }

  return true;
};

const handleCancel = () => {
  emit('update:visible', false);
};

const beforeUpload = (file) => {
  if (!isSupportedExtension(file?.name)) {
    message.error(`不支持的文件类型：${file?.name || '未知文件'}`);
    return Upload.LIST_IGNORE;
  }
  return true;
};

const formatFileSize = (bytes) => {
  if (bytes === 0 || !bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

const formatFileTime = (timestamp) => {
  if (!timestamp) return '';
  try {
    const date = new Date(timestamp);
    return date.toLocaleString();
  } catch (e) {
    return timestamp;
  }
};

const showSameNameFilesInUploadArea = (files) => {
  sameNameFiles.value = files;
  // 可以在这里添加其他逻辑，比如自动滚动到提示区域
};

const downloadSameNameFile = async (file) => {
  try {
    // 获取当前数据库ID
    const currentDbId = databaseId.value;
    if (!currentDbId) {
      message.error('知识库ID不存在');
      return;
    }

    message.loading('正在下载文件...', 0);
    const response = await documentApi.downloadDocument(currentDbId, file.file_id);
    message.destroy();

    // 创建下载链接
    const blob = await response.blob();  // 从 Response 对象中提取 Blob 数据
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = file.filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);

    message.success(`文件 ${file.filename} 下载成功`);
  } catch (error) {
    message.destroy();
    console.error('下载文件失败:', error);
    message.error(`下载文件失败: ${error.message || '未知错误'}`);
  }
};

const deleteSameNameFile = (file) => {
  Modal.confirm({
    title: '确认删除文件',
    content: `确定要删除文件 "${file.filename}" 吗？此操作不可恢复。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        // 获取当前数据库ID
        const currentDbId = databaseId.value;
        if (!currentDbId) {
          message.error('知识库ID不存在');
          return;
        }

        message.loading('正在删除文件...', 0);
        await documentApi.deleteDocument(currentDbId, file.file_id);
        message.destroy();

        // 从同名文件列表中移除
        sameNameFiles.value = sameNameFiles.value.filter(f => f.file_id !== file.file_id);

        message.success(`文件 ${file.filename} 删除成功`);
      } catch (error) {
        message.destroy();
        console.error('删除文件失败:', error);
        message.error(`删除文件失败: ${error.message || '未知错误'}`);
      }
    }
  });
};

const handleFileUpload = (info) => {
  if (info?.file?.status === 'error') {
    const errorMessage = info.file?.response?.detail || `文件上传失败：${info.file.name}`;
    message.error(errorMessage);
  }

  // 检查是否有同名文件提示
  if (info?.file?.status === 'done' && info.file.response) {
    const response = info.file.response;
    if (response.has_same_name && response.same_name_files && response.same_name_files.length > 0) {
      // 显示同名文件提示
      showSameNameFilesInUploadArea(response.same_name_files);
    }
  }

  fileList.value = info?.fileList ?? [];
};

const handleDrop = () => {};

// 已移除文件夹上传逻辑

const showChunkConfigModal = () => {
  tempChunkParams.value = {
    chunk_size: chunkParams.value.chunk_size,
    chunk_overlap: chunkParams.value.chunk_overlap,
    use_qa_split: isQaSplitSupported.value ? chunkParams.value.use_qa_split : false,
    qa_separator: chunkParams.value.qa_separator,
  };
  chunkConfigModalVisible.value = true;
};

const handleChunkConfigSubmit = () => {
  chunkParams.value.chunk_size = tempChunkParams.value.chunk_size;
  chunkParams.value.chunk_overlap = tempChunkParams.value.chunk_overlap;
  // 只有支持QA分割的知识库类型才保存QA分割配置
  if (isQaSplitSupported.value) {
    chunkParams.value.use_qa_split = tempChunkParams.value.use_qa_split;
    chunkParams.value.qa_separator = tempChunkParams.value.qa_separator;
  } else {
    chunkParams.value.use_qa_split = false;
  }
  chunkConfigModalVisible.value = false;
  message.success('分块参数配置已更新');
};

const checkOcrHealth = async () => {
  if (ocrHealthChecking.value) return;

  ocrHealthChecking.value = true;
  try {
    const healthData = await ocrApi.getHealth();
    ocrHealthStatus.value = healthData.services;
  } catch (error) {
    console.error('OCR健康检查失败:', error);
    message.error('OCR服务健康检查失败');
  } finally {
    ocrHealthChecking.value = false;
  }
};

const getAuthHeaders = () => {
  const userStore = useUserStore();
  return userStore.getAuthHeaders();
};

const chunkData = async () => {
  if (!databaseId.value) {
    message.error('请先选择知识库');
    return;
  }

  // 验证OCR服务可用性
  if (!validateOcrService()) {
    return;
  }

  let success = false;
  if (uploadMode.value === 'file') {
    const files = fileList.value.filter(file => file.status === 'done').map(file => file.response?.file_path);
    // 过滤掉 undefined 或 null 的文件路径
    const validFiles = files.filter(file => file);
    if (validFiles.length === 0) {
      message.error('请先上传文件');
      return;
    }

    // 验证图片文件是否启用OCR
    const imageExtensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'];
    const hasImageFiles = validFiles.some(filePath => {
      const ext = filePath.substring(filePath.lastIndexOf('.')).toLowerCase();
      return imageExtensions.includes(ext);
    });

    if (hasImageFiles && chunkParams.value.enable_ocr === 'disable') {
      message.error({
        content: '检测到图片文件,必须启用 OCR 才能提取文本内容。请在上方选择 OCR 方式 (RapidOCR/MinerU/MinerU Official/PaddleX) 或移除图片文件。',
        duration: 5,
      });
      return;
    }

    try {
      store.state.chunkLoading = true;
      success = await store.addFiles({ items: validFiles, contentType: 'file', params: chunkParams.value });
    } catch (error) {
      console.error('文件上传失败:', error);
      message.error('文件上传失败: ' + (error.message || '未知错误'));
    } finally {
      store.state.chunkLoading = false;
    }
  }

  if (success) {
    emit('update:visible', false);
    fileList.value = [];
    sameNameFiles.value = [];  // 清空同名文件列表
  }
};

</script>

<style lang="less" scoped>
.add-files-content {
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  height: 100%;

  .ant-form-item {
    margin: 0;
  }
}

.upload-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.source-selector {
  display: flex;
  align-items: center;
}

.config-controls {
  display: flex;
  align-items: center;
}

.source-segmented {
  background-color: var(--gray-100);
  border: 1px solid var(--gray-200);
}


.source-segmented :deep(.ant-segmented-item-label) {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  color: var(--gray-600);
}

.source-segmented :deep(.ant-segmented-item-selected .ant-segmented-item-label) {
  color: var(--main-color);
}

.source-segmented :deep(.segmented-option) {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.source-segmented :deep(.option-icon) {
  font-size: 14px;
}

.ocr-config {
  margin-bottom: 20px;
  padding: 16px;
  background-color: var(--gray-50);
  border-radius: 6px;
}

.param-description {
  font-size: 12px;
  color: var(--gray-600);
  margin-top: 4px;
}

.ocr-warning {
  color: #faad14;
}

.ocr-healthy {
  color: #52c41a;
}

.upload-dragger {
  margin-bottom: 16px;
}

.url-hint {
  font-size: 12px;
  color: var(--gray-600);
  margin-top: 8px;
}

.chunk-config-content .params-info {
  margin-bottom: 16px;
}

// OCR警告提醒样式
.ocr-warning-alert {
  margin: 12px 0;
  padding: 8px 12px;
  background: #fff7e6;
  border: 1px solid #ffd666;
  border-radius: 4px;
  color: #d46b08;
  font-size: 13px;
}

.folder-upload-tip {
  margin-top: 12px;
  padding: 12px;
  background: #f0f7ff;
  border-radius: 4px;
  color: var(--gray-500);
  font-size: 12px;
}

.zip-support-tip {
  font-size: 12px;
  color: var(--color-warning-500);
}

// 同名文件提示样式
.same-name-files-section {
  margin-top: 16px;
  padding: 12px;
  background: var(--main-50);
  border: 1px solid var(--main-200);
  border-radius: 6px;
}

.same-name-files-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  color: var(--main-700);
  font-weight: 500;
  font-size: 14px;
}

.same-name-files-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.same-name-file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #fff;
  border: 1px solid var(--gray-300);
  border-radius: 6px;
}

.same-name-file-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.same-name-file-name {
  font-weight: 500;
  color: var(--gray-800);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.same-name-file-size {
  font-size: 12px;
  color: var(--gray-500);
  flex-shrink: 0;
}

.same-name-file-time {
  font-size: 12px;
  color: var(--gray-500);
  flex-shrink: 0;
}

.same-name-file-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.download-btn {
  color: var(--main-600);
}

.download-btn:hover {
  color: var(--main-700);
  background-color: var(--main-50);
}
</style>
