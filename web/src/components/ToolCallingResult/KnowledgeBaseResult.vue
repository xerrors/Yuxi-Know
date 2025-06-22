<template>
  <div class="knowledge-base-result">
    <div class="kb-header">
      <h4><FileTextOutlined /> 知识库检索结果</h4>
      <div class="result-summary">
        找到 {{ data.length }} 个相关文档片段
      </div>
    </div>

    <div class="kb-results">
      <div
        v-for="(result, index) in data"
        :key="result.id"
        class="kb-result-item"
        :class="{ 'high-relevance': result.rerank_score > 0.5 }"
      >
        <div class="result-header">
          <div class="result-index">#{{ index + 1 }}</div>
          <div class="result-file">
            <FileOutlined />
            {{ result.file.filename }}
          </div>
          <div class="result-id">ID: {{ result.id }}</div>
        </div>

        <div class="result-scores">
          <div class="score-item">
            <span class="score-label">相似度:</span>
            <a-progress
              :percent="getPercent(result.distance)"
              size="small"
              :stroke-color="getScoreColor(result.distance)"
            />
            <span class="score-value">{{ result.distance.toFixed(4) }}</span>
          </div>

          <div v-if="result.rerank_score" class="score-item">
            <span class="score-label">重排序:</span>
            <a-progress
              :percent="getPercent(result.rerank_score)"
              size="small"
              :stroke-color="getScoreColor(result.rerank_score)"
            />
            <span class="score-value">{{ result.rerank_score.toFixed(4) }}</span>
          </div>
        </div>

        <div class="result-content">
          <div class="content-text">{{ result.entity.text }}</div>
        </div>
      </div>
    </div>

    <div v-if="data.length === 0" class="no-results">
      <p>未找到相关知识库内容</p>
    </div>
  </div>
</template>

<script setup>
import { FileTextOutlined, FileOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  data: {
    type: Array,
    required: true
  }
})

const getPercent = (score) => {
  // 相似度分数通常在0-1之间，需要转换为百分比
  if (score <= 1) {
    return Math.round(score * 100)
  }
  // 如果分数大于1，可能需要不同的处理
  return Math.min(Math.round(score * 100), 100)
}

const getScoreColor = (score) => {
  if (score >= 0.7) return '#52c41a'  // 绿色 - 高相关性
  if (score >= 0.5) return '#faad14'  // 橙色 - 中等相关性
  return '#ff4d4f'  // 红色 - 低相关性
}
</script>

<style lang="less" scoped>
.knowledge-base-result {
  background: var(--gray-0);
  border-radius: 8px;
  border: 1px solid var(--gray-200);

  .kb-header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--gray-200);
    background: var(--gray-50);

    h4 {
      margin: 0 0 4px 0;
      color: var(--main-color);
      font-size: 14px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .result-summary {
      font-size: 12px;
      color: var(--gray-600);
    }
  }

  .kb-results {
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .kb-result-item {
    background: var(--gray-0);
    padding: 12px;
    border-radius: 6px;
    border: 1px solid var(--gray-200);
    transition: all 0.2s ease;

    &.high-relevance {
      border-color: var(--main-300);
      background: var(--main-10);
    }

    &:hover {
      border-color: var(--main-200);
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06);
    }

    .result-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;

      .result-index {
        background: var(--main-color);
        color: var(--gray-0);
        padding: 2px 6px;
        border-radius: 10px;
        font-size: 11px;
        font-weight: 500;
        min-width: 24px;
        text-align: center;
      }

      .result-file {
        flex: 1;
        font-size: 13px;
        font-weight: 500;
        color: var(--gray-800);
        display: flex;
        align-items: center;
        gap: 4px;

        .anticon {
          color: var(--main-color);
        }
      }

      .result-id {
        font-size: 11px;
        color: var(--gray-500);
        background: var(--gray-100);
        padding: 1px 4px;
        border-radius: 3px;
      }
    }

    .result-scores {
      display: flex;
      gap: 16px;
      margin-bottom: 10px;

      .score-item {
        display: flex;
        align-items: center;
        gap: 6px;
        flex: 1;

        .score-label {
          font-size: 11px;
          color: var(--gray-600);
          min-width: 40px;
        }

        :deep(.ant-progress) {
          flex: 1;
          margin: 0;
        }

        .score-value {
          font-size: 10px;
          color: var(--gray-500);
          min-width: 40px;
          text-align: right;
        }
      }
    }

    .result-content {
      .content-text {
        font-size: 12px;
        line-height: 1.5;
        color: var(--gray-700);
        white-space: pre-wrap;
        word-break: break-word;
        background: var(--gray-50);
        padding: 10px;
        border-radius: 4px;
        border-left: 2px solid var(--main-color);
        max-height: 160px;
        overflow-y: auto;
      }
    }
  }

  .no-results {
    text-align: center;
    color: var(--gray-500);
    padding: 20px;
    font-size: 13px;
  }
}
</style>