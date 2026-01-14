<template>
  <div class="chunk-params-config">
    <div class="params-info">
      <p>调整分块参数可以控制文本的切分方式，影响检索质量和文档加载效率。</p>
    </div>
    <a-form :model="tempChunkParams" name="chunkConfig" autocomplete="off" layout="vertical">
      <div class="chunk-row">
        <a-form-item label="Chunk Size" name="chunk_size">
          <a-input-number
            v-model:value="tempChunkParams.chunk_size"
            :min="100"
            :max="10000"
            style="width: 100%"
          />
          <p class="param-description">每个文本片段的最大字符数</p>
        </a-form-item>
        <a-form-item label="Chunk Overlap" name="chunk_overlap">
          <a-input-number
            v-model:value="tempChunkParams.chunk_overlap"
            :min="0"
            :max="1000"
            style="width: 100%"
          />
          <p class="param-description">相邻文本片段间的重叠字符数</p>
        </a-form-item>
      </div>
      <a-form-item
        v-if="showQaSplit"
        class="qa-separator-item"
        label="分隔符 (Separator)"
        name="qa_separator"
      >
        <a-input
          v-model:value="tempChunkParams.qa_separator"
          placeholder="输入分隔符，例如 \n\n\n 或 ---"
          style="width: 100%"
        />
        <p class="param-description">支持 \n、\t 等转义字符。留空则不启用预分割</p>
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
  }
})
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

.chunk-row {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
}

.chunk-row > .ant-form-item {
  flex: 1;
  margin-bottom: 0;
}

.qa-separator-item {
  margin-top: 8px;
  margin-bottom: 0;
}

.param-description {
  font-size: 12px;
  color: var(--gray-400);
  margin: 4px 0 0 0;
  line-height: 1.4;
}
</style>
