<template>
  <a-modal
    v-model:open="visible"
    :title="file?.filename || '文件详情'"
    width="1200px"
    :footer="null"
    @after-open-change="afterOpenChange"
  >
    <div class="file-detail-content" v-if="file">
      <div class="file-info-grid">
        <div class="info-item">
          <label>文件ID:</label>
          <span>{{ file.file_id }}</span>
        </div>
        <div class="info-item">
          <label>上传时间:</label>
          <span>{{ formatStandardTime(Math.round(file.created_at*1000)) }}</span>
        </div>
        <div class="info-item">
          <label>处理状态:</label>
          <span class="status-badge" :class="file.status">
            {{ getStatusText(file.status) }} - {{ file.lines?.length || 0 }} 行
          </span>
        </div>
      </div>

      <div class="file-content-section" v-if="file.lines && file.lines.length > 0">
        <h4>文件内容预览</h4>
        <div class="content-lines">
          <div
            v-for="(line, index) in file.lines"
            :key="index"
            class="content-line"
          >
            <span class="line-number">{{ index + 1 }}</span>
            <span class="line-text">{{ line.text || line }}</span>
          </div>
        </div>
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
import { computed } from 'vue';
import { useDatabaseStore } from '@/stores/database';

const store = useDatabaseStore();

const visible = computed({
  get: () => store.state.fileDetailModalVisible,
  set: (value) => store.state.fileDetailModalVisible = value
});

const file = computed(() => store.selectedFile);
const loading = computed(() => store.state.fileDetailLoading);

const afterOpenChange = (open) => {
  if (!open) {
    store.selectedFile = null;
  }
};

// 导入工具函数
import { getStatusText, formatStandardTime } from '@/utils/file_utils';
</script>

<style scoped>
.file-detail-content {
  max-height: 70vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.file-info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-item label {
  font-weight: bold;
  font-size: 14px;
}

.info-item span {
  font-size: 14px;
}

.status-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge.done {
  background-color: #f6ffed;
  color: #52c41a;
  border: 1px solid #b7eb8f;
}

.status-badge.failed {
  background-color: #fff2f0;
  color: #ff4d4f;
  border: 1px solid #ffccc7;
}

.status-badge.processing {
  background-color: #e6f7ff;
  color: #1890ff;
  border: 1px solid #91d5ff;
}

.status-badge.waiting {
  background-color: #fffbe6;
  color: #faad14;
  border: 1px solid #ffe58f;
}

.file-content-section h4 {
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
}

.content-lines {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  padding: 8px;
}

.content-line {
  display: flex;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  line-height: 1.5;
}

.line-number {
  width: 40px;
  color: #ccc;
  text-align: right;
  padding-right: 8px;
  user-select: none;
  flex-shrink: 0;
}

.line-text {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-all;
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
  color: #999;
}
</style>