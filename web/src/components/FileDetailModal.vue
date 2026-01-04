<template>
  <a-modal
    v-model:open="visible"
    width="1200px"
    :footer="null"
    wrap-class-name="file-detail"
    @after-open-change="afterOpenChange"
    :bodyStyle="{ height: '80vh', padding: '0' }"
  >
    <template #title>
      <div class="modal-title-wrapper">
        <span>{{ file?.filename || '文件详情' }}</span>
        <div class="download-buttons" v-if="file">
          <a-button
            type="text"
            size="small"
            @click="handleDownloadOriginal"
            :loading="downloadingOriginal"
            :disabled="!file.file_id"
            :icon="h(DownloadOutlined)"
          >
            下载原文
          </a-button>
          <a-button
            type="text"
            size="small"
            @click="handleDownloadMarkdown"
            :loading="downloadingMarkdown"
            :disabled="!((file.lines && file.lines.length > 0) || file.content)"
            :icon="h(DownloadOutlined)"
          >
            下载 Markdown
          </a-button>
        </div>
      </div>
    </template>
    <div class="file-detail-content" v-if="file">
      <div class="file-content-section" v-if="(file.lines && file.lines.length > 0) || file.content">
        <MarkdownContentViewer :chunks="file.lines" :content="file.content" />
      </div>

      <div v-else-if="loading" class="loading-container">
        <a-spin />
      </div>

      <div v-else class="empty-content">
        <p>暂无文件内容</p>
      </div>
    </div>
  </a-modal>
</template>

<script setup>
import { computed, ref, h } from 'vue';
import { useDatabaseStore } from '@/stores/database';
import { message } from 'ant-design-vue';
import { DownloadOutlined } from '@ant-design/icons-vue';
import { documentApi } from '@/apis/knowledge_api';
import { mergeChunks } from '@/utils/chunkUtils';
import MarkdownContentViewer from './MarkdownContentViewer.vue';

const store = useDatabaseStore();

const visible = computed({
  get: () => store.state.fileDetailModalVisible,
  set: (value) => store.state.fileDetailModalVisible = value
});

const file = computed(() => store.selectedFile);
const loading = computed(() => store.state.fileDetailLoading);
const downloadingOriginal = ref(false);
const downloadingMarkdown = ref(false);

const afterOpenChange = (open) => {
  if (!open) {
    store.selectedFile = null;
  }
};

// 下载原文
const handleDownloadOriginal = async () => {
  if (!file.value || !file.value.file_id) {
    message.error('文件信息不完整');
    return;
  }

  const dbId = store.databaseId;
  if (!dbId) {
    message.error('无法获取数据库ID，请刷新页面后重试');
    return;
  }

  downloadingOriginal.value = true;
  try {
    const response = await documentApi.downloadDocument(dbId, file.value.file_id);

    // 获取文件名
    const contentDisposition = response.headers.get('content-disposition');
    let filename = file.value.filename;
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
    message.success('下载成功');
  } catch (error) {
    console.error('下载文件时出错:', error);
    message.error(error.message || '下载文件失败');
  } finally {
    downloadingOriginal.value = false;
  }
};

// 下载 Markdown
const handleDownloadMarkdown = () => {
  let content = '';
  if (file.value.content) {
    content = file.value.content;
  } else if (file.value.lines && file.value.lines.length > 0) {
    content = mergeChunks(file.value.lines).content;
  }

  if (!content) {
    message.error('没有可下载的 Markdown 内容');
    return;
  }

  downloadingMarkdown.value = true;
  try {
    // 生成文件名（如果原文件没有 .md 扩展名，则添加）
    let filename = file.value.filename || 'document.md';
    if (!filename.toLowerCase().endsWith('.md')) {
      // 移除原扩展名，添加 .md
      const lastDotIndex = filename.lastIndexOf('.');
      if (lastDotIndex > 0) {
        filename = filename.substring(0, lastDotIndex) + '.md';
      } else {
        filename = filename + '.md';
      }
    }

    // 创建 blob 并下载
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    message.success('下载成功');
  } catch (error) {
    console.error('下载 Markdown 时出错:', error);
    message.error(error.message || '下载 Markdown 失败');
  } finally {
    downloadingMarkdown.value = false;
  }
};
</script>

<style scoped>
.file-detail-content {
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.file-content-section h4 {
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
}

.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
}

.empty-content {
  text-align: center;
  padding: 40px 0;
  color: var(--gray-400);
}
</style>

<style lang="less">
.file-detail {
  .ant-modal {
    top: 20px;
  }

  .ant-modal-header {
    .ant-modal-title {
      width: 100%;
    }
  }
}

.modal-title-wrapper {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding-right: 8px;
}

.download-buttons {
  display: flex;
  gap: 8px;
  margin: 0 16px;
  flex-shrink: 0;
}
</style>