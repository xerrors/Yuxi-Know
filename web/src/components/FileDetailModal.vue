<template>
  <a-modal
    v-model:open="visible"
    :title="file?.filename || '文件详情'"
    width="1200px"
    :footer="null"
    wrap-class-name="file-detail"
    @after-open-change="afterOpenChange"
    :bodyStyle="{ height: '80vh', padding: '0' }"
  >
    <div class="file-detail-content" v-if="file">
      <div class="file-content-section" v-if="file.lines && file.lines.length > 0">
        <MarkdownContentViewer :chunks="file.lines" />
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
import MarkdownContentViewer from './MarkdownContentViewer.vue';
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
  color: #999;
}
</style>

<style lang="less">
.file-detail {
  .ant-modal {
    top: 20px;
  }
}
</style>