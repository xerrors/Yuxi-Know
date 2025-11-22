<template>
  <div class="chunk-params-config">
    <div class="params-info">
      <p>调整分块参数可以控制文本的切分方式，影响检索质量和文档加载效率。</p>
    </div>
    <a-form
      :model="tempChunkParams"
      name="chunkConfig"
      autocomplete="off"
      layout="vertical"
      >
        <a-form-item label="Chunk Size" name="chunk_size">
          <a-input-number v-model:value="tempChunkParams.chunk_size" :min="100" :max="10000" style="width: 100%;" />
          <p class="param-description">每个文本片段的最大字符数</p>
        </a-form-item>
        <a-form-item label="Chunk Overlap" name="chunk_overlap">
          <a-input-number v-model:value="tempChunkParams.chunk_overlap" :min="0" :max="1000" style="width: 100%;" />
          <p class="param-description">相邻文本片段间的重叠字符数</p>
        </a-form-item>
        <a-form-item v-if="showQaSplit" label="QA分割模式" name="use_qa_split">
          <a-switch v-model:checked="tempChunkParams.use_qa_split" />
          <p class="param-description">启用后将按QA对分割，忽略上述chunk大小设置</p>
        </a-form-item>
        <a-form-item v-if="tempChunkParams?.use_qa_split && showQaSplit" label="QA分隔符" name="qa_separator">
          <a-input v-model:value="tempChunkParams.qa_separator" placeholder="输入QA分隔符" style="width: 100%;" />
          <p class="param-description">用于分割不同QA对的分隔符</p>
        </a-form-item>
      </a-form>
  </div>
</template>

<script setup>

defineProps({
  tempChunkParams: {
    type: Object,
    required: true
  },
  showQaSplit: {
    type: Boolean,
    default: true
  },
});
</script>

<style scoped>
.chunk-params-config {
  width: 100%;
}

.params-info {
  margin-bottom: 16px;
}

.params-info p {
  margin: 0;
  color: var(--gray-500);
  font-size: 14px;
  line-height: 1.5;
}

.param-description {
  font-size: 12px;
  color: var(--gray-400);
  margin: 4px 0 0 0;
  line-height: 1.4;
}
</style>