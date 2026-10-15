<template>
  <article class="result-item" :class="{ selected }">
    <div class="result-header">
      <span class="result-index">#{{ index + 1 }}</span>
      <button
        v-if="chunk.metadata?.file_id"
        type="button"
        class="result-open"
        :aria-pressed="selected"
        :title="chunk.metadata.source || '查看原文'"
        @click.stop="$emit('select', chunk)"
      >
        <span class="result-filename">{{ chunk.metadata.source || '查看原文' }}</span>
        <span v-if="chunk.metadata.start_line" class="result-lines">
          · 行 {{ chunk.metadata.start_line }}–{{ chunk.metadata.end_line }}
        </span>
        <span v-else class="result-lines"> · 查看原文</span>
      </button>
      <span
        v-else-if="chunk.metadata?.source"
        class="result-filename result-source"
        :title="chunk.metadata.source"
      >{{ chunk.metadata.source }}</span>
    </div>
    <div
      :id="contentId"
      ref="previewRef"
      class="result-content"
      :class="{ 'is-collapsed': !expanded }"
    >
      <template v-if="chunk.highlights?.length && !expanded">
        <p v-for="(fragment, fragmentIndex) in chunk.highlights" :key="fragmentIndex">
          <template v-for="(segment, segmentIndex) in fragment" :key="segmentIndex">
            <mark v-if="segment.matched">{{ segment.text }}</mark>
            <span v-else>{{ segment.text }}</span>
          </template>
        </p>
      </template>
      <template v-else>{{ chunk.content }}</template>
    </div>
    <button
      v-if="expanded || overflowing || chunk.highlights?.length"
      type="button"
      class="result-expand"
      :aria-expanded="expanded"
      :aria-controls="contentId"
      @click="expanded = !expanded"
    >
      {{ expanded ? '收起片段' : '展开完整片段' }}
    </button>
    <div
      v-if="Number.isFinite(chunk.score) || Number.isFinite(chunk.rerank_score) || chunk.metadata?.chunk_index !== undefined"
      class="result-metadata"
    >
      <span v-if="Number.isFinite(chunk.score)" class="result-score">
        {{ scoreLabel }}: {{ chunk.score.toFixed(4) }}
      </span>
      <span v-if="Number.isFinite(chunk.rerank_score)" class="result-rerank-score">
        重排序分数: {{ chunk.rerank_score.toFixed(4) }}
      </span>
      <span v-if="chunk.metadata?.chunk_index !== undefined">
        块索引: {{ chunk.metadata.chunk_index }}
      </span>
    </div>
  </article>
</template>

<script setup>
import { computed, ref, useId, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'

const props = defineProps({
  chunk: { type: Object, required: true },
  index: { type: Number, required: true },
  selected: { type: Boolean, default: false }
})

defineEmits(['select'])

const contentId = useId()
const previewRef = ref(null)
const expanded = ref(false)
const overflowing = ref(false)

useResizeObserver(previewRef, () => {
  const element = previewRef.value
  overflowing.value = Boolean(element && element.scrollHeight > element.clientHeight + 1)
})
watch(() => props.chunk, () => { expanded.value = false })

const scoreLabel = computed(
  () =>
    ({
      cosine: '向量相似度',
      bm25: '关键词相关度',
      hybrid: '混合检索分数',
      graph: '图检索分数',
      fusion: '融合排名分数'
    })[props.chunk.score_type] || '检索分数'
)
</script>

<style scoped lang="less">
.result-item {
  padding: 12px;
  margin-bottom: 12px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  background: var(--gray-0);
  color: var(--color-text);
}

.result-item.selected {
  border-color: var(--main-color);
}
.result-open {
  display: flex;
  align-items: baseline;
  flex: 1;
  min-width: 0;
  gap: 4px;
  border: none;
  background: none;
  padding: 0;
  color: var(--main-color);
  font: inherit;
  cursor: pointer;
  text-align: left;
  &:hover {
    text-decoration: underline;
  }
  &:focus-visible {
    outline: 2px solid var(--main-color);
    outline-offset: 3px;
  }
}

.result-filename {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-source {
  flex: 1;
}

.result-lines {
  flex: none;
  white-space: nowrap;
}

.result-header,
.result-metadata {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  font-size: 12px;
}

.result-header {
  padding-bottom: 8px;
  border-bottom: 1px solid var(--gray-150);
}

.result-index {
  color: var(--main-color);
  font-weight: 600;
}

.result-score,
.result-rerank-score {
  color: var(--color-text-secondary);
}

.result-content {
  margin: 8px 0;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;

  p {
    margin: 0 0 8px;
  }
}

.result-content.is-collapsed {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 6;
  overflow: hidden;
}

mark {
  background: var(--color-warning-50);
  color: var(--color-warning-900);
}

.result-expand {
  padding: 2px 0 8px;
  border: 0;
  background: none;
  color: var(--main-color);
  cursor: pointer;
  font: inherit;
  font-size: 12px;

  &:hover { text-decoration: underline; }
  &:focus-visible {
    outline: 2px solid var(--main-color);
    outline-offset: 2px;
  }
}

.result-metadata {
  padding-top: 8px;
  border-top: 1px solid var(--gray-150);
  color: var(--color-text-secondary);

  span {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>
