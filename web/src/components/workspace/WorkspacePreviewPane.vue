<template>
  <aside class="workspace-preview-pane">
    <AgentFilePreview
      v-if="file"
      :file="file"
      :file-path="filePath"
      :show-download="false"
      :show-close="true"
      :show-fullscreen="true"
      :full-height="true"
      container-class="workspace-preview-container"
      content-class="workspace-preview-content"
      @close="$emit('close')"
    />
    <div v-else-if="loading" class="preview-state">
      <a-spin />
      <span>正在加载预览...</span>
    </div>
    <div v-else class="preview-empty">
      <FileSearch :size="28" />
      <h3>选择文件以预览</h3>
      <p>支持 Markdown、文本、代码、图片与 PDF 的只读预览。</p>
    </div>
  </aside>
</template>

<script setup>
import { FileSearch } from 'lucide-vue-next'
import AgentFilePreview from '@/components/AgentFilePreview.vue'

defineProps({
  file: { type: Object, default: null },
  filePath: { type: String, default: '' },
  loading: { type: Boolean, default: false }
})

defineEmits(['close'])
</script>

<style scoped lang="less">
.workspace-preview-pane {
  min-width: 0;
  min-height: 0;
  border-left: 1px solid var(--gray-100);
  background: var(--gray-0);
  overflow: hidden;
}

:deep(.workspace-preview-container) {
  height: 100%;
  border-radius: 0;
}

:deep(.workspace-preview-content) {
  flex: 1 1 auto;
  max-height: none;
  min-height: 0;
}

.preview-state,
.preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 260px;
  padding: 24px;
  color: var(--gray-500);
  text-align: center;
}

.preview-state {
  gap: 10px;
}

.preview-empty {
  gap: 8px;

  h3 {
    margin: 6px 0 0;
    color: var(--gray-800);
    font-size: 15px;
    font-weight: 600;
  }

  p {
    max-width: 240px;
    margin: 0;
    color: var(--gray-500);
    font-size: 13px;
    line-height: 1.6;
  }
}
</style>
