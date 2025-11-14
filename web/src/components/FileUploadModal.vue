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
        :disabled="(uploadMode === 'file' && fileList.length === 0) || (uploadMode === 'folder' && folderFileList.length === 0) || (uploadMode === 'url' && !urlList.trim())"
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

      <div class="ocr-config" v-if="uploadMode !== 'folder'">
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
        </a-upload-dragger>
      </div>

      <!-- 文件夹上传区域 -->
      <div class="upload" v-if="uploadMode === 'folder'">
        <a-upload-dragger
          class="upload-dragger"
          v-model:fileList="folderFileList"
          name="file"
          :multiple="false"
          :disabled="chunkLoading"
          accept=".zip"
          :before-upload="beforeFolderUpload"
          :customRequest="handleFolderCustomRequest"
          @change="handleFolderUploadChange"
          @drop="handleDrop"
        >
          <p class="ant-upload-text">点击或者把zip文件夹拖拽到这里上传</p>
          <p class="ant-upload-hint">
            支持上传zip格式的文件夹，文件夹应包含：
            <br />• full.md (或其他 .md 文件)
            <br />• images/ 文件夹（包含图片文件）
          </p>
        </a-upload-dragger>
        <div class="folder-upload-tip" style="margin-top: 12px; padding: 12px; background: #f0f7ff; border-radius: 4px; color: #666; font-size: 12px;">
          <p style="margin: 0 0 8px 0; font-weight: 500;">📁 文件夹结构示例：</p>
          <pre style="margin: 0; font-size: 11px; line-height: 1.6;">your-folder/
  ├── full.md
  └── images/
      ├── image1.jpg
      └── image2.png</pre>
        </div>
      </div>

      <!-- URL 输入区域 -->
      <div class="url-input" v-if="uploadMode === 'url'">
        <a-form layout="vertical">
          <a-form-item label="网页链接 (每行一个URL)">
            <a-textarea
              v-model:value="urlList"
              placeholder="请输入网页链接，每行一个"
              :rows="6"
              :disabled="chunkLoading"
            />
          </a-form-item>
        </a-form>
        <p class="url-hint">
          支持添加网页内容，系统会自动抓取网页文本并进行分块。请确保URL格式正确且可以公开访问。
        </p>
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
import { message, Upload } from 'ant-design-vue';
import { useUserStore } from '@/stores/user';
import { useDatabaseStore } from '@/stores/database';
import { useTaskerStore } from '@/stores/tasker';
import { ocrApi } from '@/apis/system_api';
import { fileApi } from '@/apis/knowledge_api';
import ChunkParamsConfig from '@/components/ChunkParamsConfig.vue';
import {
  FileOutlined,
  FolderOutlined,
  LinkOutlined,
  SettingOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
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
const taskerStore = useTaskerStore();

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
  return supportedFileTypes.value.join(',');
});

const uploadHint = computed(() => {
  if (!supportedFileTypes.value.length) {
    return '加载中...';
  }
  return supportedFileTypes.value.join(', ');
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
  return supportedFileTypes.value.includes(ext);
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
    value: 'folder',
    label: h('div', { class: 'segmented-option' }, [
      h(FolderOutlined, { class: 'option-icon' }),
      h('span', { class: 'option-text' }, '上传文件夹'),
    ]),
  },
  {
    value: 'url',
    label: h('div', { class: 'segmented-option' }, [
      h(LinkOutlined, { class: 'option-icon' }),
      h('span', { class: 'option-text' }, '输入网址'),
    ]),
  },
]);

// 文件列表
const fileList = ref([]);

// 文件夹列表（zip文件）
const folderFileList = ref([]);

// URL列表
const urlList = ref('');

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

watch(uploadMode, (mode, previous) => {
  if (mode === 'url') {
    previousOcrSelection.value = chunkParams.value.enable_ocr;
    chunkParams.value.enable_ocr = 'disable';
  } else if (mode === 'file' && previous === 'url') {
    chunkParams.value.enable_ocr = previousOcrSelection.value || 'disable';
  }
});

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

const handleFileUpload = (info) => {
  if (info?.file?.status === 'error') {
    const errorMessage = info.file?.response?.detail || `文件上传失败：${info.file.name}`;
    message.error(errorMessage);
  }
  fileList.value = info?.fileList ?? [];
};

const handleDrop = () => {};

// 文件夹上传前的验证
const beforeFolderUpload = (file) => {
  if (!file.name.endsWith('.zip')) {
    message.error('只支持上传 .zip 格式的文件夹');
    return Upload.LIST_IGNORE;
  }
  // 返回 true 允许上传，使用 customRequest 自定义上传逻辑
  return true;
};

// 文件夹自定义上传处理 - 显示上传进度（与文件上传一致）
const handleFolderCustomRequest = async (options) => {
  const { file, onProgress, onSuccess, onError } = options;
  
  try {
    // 验证文件格式
    if (!file.name.endsWith('.zip')) {
      onError(new Error('只支持上传 .zip 格式的文件夹'));
      return;
    }
    
    // 如果没有选择知识库，先标记为已选择，不上传
    if (!databaseId.value) {
      setTimeout(() => {
        onSuccess({ 
          message: '请先选择知识库，然后点击"添加到知识库"按钮开始上传和处理'
        }, file);
      }, 100);
      return;
    }
    
    // 实际上传文件，显示进度条（与文件上传一致）
    const formData = new FormData();
    formData.append('file', file);
    
    const xhr = new XMLHttpRequest();
    
    // 监听上传进度
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        if (onProgress) {
          onProgress({ percent });
        }
      }
    });
    
    // 上传成功
    xhr.addEventListener('load', () => {
      if (xhr.status === 200) {
        try {
          const response = JSON.parse(xhr.responseText);
          onSuccess(response, file);
        } catch (e) {
          // 如果解析失败，尝试作为文本处理
          onSuccess({ message: '上传成功' }, file);
        }
      } else {
        try {
          const error = JSON.parse(xhr.responseText);
          onError(new Error(error.detail || error.message || '上传失败'));
        } catch (e) {
          onError(new Error(`上传失败: ${xhr.status} ${xhr.statusText}`));
        }
      }
    });
    
    // 上传错误
    xhr.addEventListener('error', () => {
      onError(new Error('上传失败：网络错误'));
    });
    
    // 上传取消
    xhr.addEventListener('abort', () => {
      onError(new Error('上传已取消'));
    });
    
    // 设置请求头和发送请求
    const userStore = useUserStore();
    const authHeaders = userStore.getAuthHeaders();
    
    xhr.open('POST', `/api/knowledge/files/upload-folder?db_id=${databaseId.value}`);
    Object.keys(authHeaders).forEach(key => {
      xhr.setRequestHeader(key, authHeaders[key]);
    });
    
    xhr.send(formData);
    
  } catch (error) {
    console.error('文件夹上传失败:', error);
    onError(error);
  }
};

// 处理文件夹上传状态变化
const handleFolderUploadChange = (info) => {
  console.log('文件夹上传状态变化:', info);
  if (info?.file?.status === 'error') {
    const errorMessage = info.file?.response?.detail || info.file?.response?.message || `文件夹选择失败：${info.file.name}`;
    message.error(errorMessage);
  }
  folderFileList.value = info?.fileList ?? [];
};

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
  } else if (uploadMode.value === 'folder') {
    // 文件夹上传模式 - 像文件上传那样，先上传，然后提交到任务中心
    if (folderFileList.value.length === 0) {
      message.error('请选择要上传的文件夹');
      return;
    }

    // 获取已上传成功的文件夹文件（与文件上传保持一致）
    const validFolders = folderFileList.value.filter(file => 
      file.status === 'done' && file.response
    );

    if (validFolders.length === 0) {
      message.error('请先上传文件夹，或等待上传完成');
      return;
    }

    try {
      store.state.chunkLoading = true;
      
      // 显示统一的loading消息
      const hideLoading = message.loading('正在处理文件夹...', 0);
      
      // 提交处理任务（文件已上传，只需要处理）
      const results = [];
      const errors = [];
      
      for (let i = 0; i < validFolders.length; i++) {
        const file = validFolders[i];
        const fileIndex = validFolders.length > 1 ? ` (${i + 1}/${validFolders.length})` : '';
        
        try {
          // 获取上传响应
          const uploadResponse = file.response;
          console.log(`文件夹${fileIndex}上传响应:`, uploadResponse);
          
          // 验证上传响应
          if (!uploadResponse) {
            throw new Error('上传响应为空');
          }
          
          // 如果响应是字符串，尝试解析为JSON
          let responseData = uploadResponse;
          if (typeof uploadResponse === 'string') {
            try {
              responseData = JSON.parse(uploadResponse);
            } catch (e) {
              throw new Error('服务器返回格式错误：无法解析响应');
            }
          }
          
          // 检查响应格式
          if (typeof responseData !== 'object' || responseData === null) {
            throw new Error('服务器返回格式错误：响应不是对象');
          }
          
          // 如果响应包含 task_id，说明后端直接返回了处理任务结果
          if (responseData.task_id && (responseData.status === 'queued' || responseData.status === 'processing')) {
            responseData.isDirectProcess = true;
          } else {
            // 检查必需的字段
            if (!responseData.file_path || !responseData.content_hash) {
              throw new Error('服务器返回格式错误：缺少必要字段');
            }
          }
          
          let processResponse;
          
          // 如果上传响应直接包含了处理任务结果，直接使用它
          if (responseData.isDirectProcess && responseData.task_id) {
            console.log('使用上传响应中的处理任务结果');
            processResponse = responseData;
          } else {
            // 第二步：提交处理任务到任务中心
            processResponse = await fileApi.processFolder({
              file_path: responseData.file_path,
              db_id: databaseId.value,
              content_hash: responseData.content_hash
            });
            
            // 验证处理响应
            if (!processResponse) {
              throw new Error('处理任务提交失败：服务器未返回数据');
            }
          }
          
          // 注册任务到任务中心（像文件上传那样）
          if (processResponse.task_id) {
            taskerStore.registerQueuedTask({
              task_id: processResponse.task_id,
              name: `文件夹处理 (${databaseId.value || ''})`,
              task_type: 'knowledge_ingest',
              message: processResponse.message || '文件夹处理任务已提交',
              payload: {
                db_id: databaseId.value,
                file_path: responseData.file_path || '',
                content_hash: responseData.content_hash || '',
                content_type: 'folder',
              }
            });
          }
          
          results.push(processResponse);
          
        } catch (error) {
          console.error(`文件夹${fileIndex}上传或处理失败:`, error);
          const errorMessage = error.message || '未知错误';
          errors.push(`${file.name}: ${errorMessage}`);
        }
      }
      
      // 清除loading消息
      hideLoading();
      
      // 显示结果消息 - 与文件上传保持一致
      if (results.length > 0) {
        const taskIds = results.map(r => r.task_id).filter(Boolean);
        const itemType = '文件夹';
        
        // 使用与文件上传相同的消息格式
        const successMessage = results[0].message || `${itemType}已提交处理，请在任务中心查看进度`;
        message.success(successMessage);
        
        // 启用自动刷新（与文件上传保持一致）
        try {
          if (!store.state.autoRefresh) {
            store.state.autoRefresh = true;
          }
          store.startAutoRefresh();
        } catch (e) {
          console.warn('启用自动刷新失败:', e);
        }
        
        // 立即刷新知识库信息（与文件上传保持一致）
        // 这会触发 DataBaseInfoView 中的 watch，自动生成导图和示例问题
        try {
          await store.getDatabaseInfo();
          console.log('知识库信息已刷新，将触发导图生成和AI分析');
        } catch (e) {
          console.warn('刷新知识库信息失败:', e);
        }
        
        success = true;
      }
      
      // 显示错误消息
      if (errors.length > 0) {
        if (results.length > 0) {
          // 部分成功
          message.warning(`部分文件夹处理失败: ${errors.join('; ')}`);
        } else {
          // 全部失败
          message.error(`所有文件夹处理失败: ${errors.join('; ')}`);
        }
      }
      
    } catch (error) {
      console.error('文件夹处理失败:', error);
      const errorMessage = error.message || '未知错误';
      message.error(`文件夹处理失败: ${errorMessage}`);
    } finally {
      store.state.chunkLoading = false;
    }
  } else if (uploadMode.value === 'url') {
    const urls = urlList.value.split('\n')
      .map(url => url.trim())
      .filter(url => url.length > 0 && (url.startsWith('http://') || url.startsWith('https://')));

    if (urls.length === 0) {
      message.error('请输入有效的网页链接（必须以http://或https://开头）');
      return;
    }

    try {
      store.state.chunkLoading = true;
      success = await store.addFiles({ items: urls, contentType: 'url', params: chunkParams.value });
    } catch (error) {
      console.error('URL上传失败:', error);
      message.error('URL上传失败: ' + (error.message || '未知错误'));
    } finally {
      store.state.chunkLoading = false;
    }
  }

  if (success) {
    emit('update:visible', false);
    fileList.value = [];
    folderFileList.value = [];
    urlList.value = '';
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
  color: #666;
  font-size: 12px;
}
</style>
