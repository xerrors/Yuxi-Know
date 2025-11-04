<template>
  <div class="web-search-result">
    <div class="search-header">
      <h4><GlobalOutlined /> 网页搜索结果</h4>
      <div class="search-meta">
        <span class="query-text">查询: {{ data.query }}</span>
        <span class="response-time">响应时间: {{ data.response_time }}s</span>
      </div>
    </div>

    <div class="search-results">
      <div
        v-for="(result, index) in data.results"
        :key="index"
        class="search-result-item"
      >
        <div class="result-header">
          <h5 class="result-title">
            <a :href="result.url" target="_blank" rel="noopener noreferrer">
              {{ result.title }}
            </a>
          </h5>
          <span class="result-score">相关度: {{ (result.score * 100).toFixed(1) }}%</span>
        </div>

        <div class="result-meta">
          <!-- <span class="result-url">{{ result.url }}</span> -->
          <span v-if="result.published_date" class="result-date">
            {{ formatDate(result.published_date) }}
          </span>
        </div>

        <div class="result-content">
          {{ result.content }}
        </div>
      </div>
    </div>

    <div v-if="data.results.length === 0" class="no-results">
      <p>未找到相关搜索结果</p>
    </div>
  </div>
</template>

<script setup>
import { GlobalOutlined } from '@ant-design/icons-vue'
import { parseToShanghai } from '@/utils/time'

const props = defineProps({
  data: {
    type: Object,
    required: true
  }
})

const formatDate = (dateString) => {
  if (!dateString) return ''
  const parsed = parseToShanghai(dateString)
  if (!parsed) return ''
  return parsed.format('YYYY年MM月DD日')
}
</script>

<style lang="less" scoped>
.web-search-result {
  background: var(--gray-0);
  border-radius: 8px;

  .search-header {
    padding: 12px 16px;
    background: var(--gray-25);

    h4 {
      margin: 0 0 6px 0;
      color: var(--main-color);
      font-size: 14px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .search-meta {
      display: flex;
      gap: 16px;
      font-size: 12px;
      color: var(--gray-600);

      .query-text {
        font-weight: 500;
        color: var(--gray-800);
      }
    }
  }

  .search-results {
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .search-result-item {
    padding: 12px;
    border-bottom: 1px solid var(--gray-200);
    transition: all 0.2s ease;

    &:last-child {
      border-bottom: none;
    }

    .result-header {
      display: flex;
      justify-content: space-between;
      align-items: center;

      .result-title {
        margin: 0;
        font-size: 14px;
        line-height: 1.4;
        flex: 1;

        a {
          color: var(--main-color);
          text-decoration: none;
          font-weight: 500;

          &:hover {
            color: var(--main-color);
            text-decoration: underline;
          }
        }
      }

      .result-score {
        font-size: 11px;
        color: var(--gray-600);
        background: var(--gray-50);
        padding: 0px 6px;
        border-radius: 10px;
        margin-left: 8px;
      }
    }

    .result-meta {
      display: flex;
      gap: 12px;
      margin-bottom: 8px;
      font-size: 11px;
      color: var(--gray-500);

      .result-url {
        color: var(--main-400);
        word-break: break-all;
      }

      .result-date {
        color: var(--gray-500);
      }
    }

    .result-content {
      font-size: 13px;
      line-height: 1.5;
      color: var(--gray-700);
      overflow: hidden;
      display: -webkit-box;
      line-clamp: 2;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
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
