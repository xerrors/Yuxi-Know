<template>
  <BaseToolCall :tool-call="toolCall" :hide-params="true">
    <template #header>
      <div class="sep-header">
        <span class="note">网络搜索</span>
        <span class="separator" v-if="query">|</span>
        <span class="description">{{ query }}</span>
      </div>
    </template>
    <template #result="{ resultContent }">
      <div class="web-search-result">
        <div class="search-results">
          <div
            v-for="(result, index) in parsedData(resultContent).results"
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

        <div v-if="parsedData(resultContent).results.length === 0" class="no-results">
          <p>未找到相关搜索结果</p>
        </div>
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import BaseToolCall from '../BaseToolCall.vue'
import { parseToShanghai } from '@/utils/time'
import { computed } from 'vue'

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

const parseData = (content) => {
  if (typeof content === 'string') {
    try {
      return JSON.parse(content)
    } catch (error) {
      return { query: '', results: [], response_time: 0 }
    }
  }
  return content || { query: '', results: [], response_time: 0 }
}

const parsedData = (content) => parseData(content)

const query = computed(() => {
  // First try to get it from result
  const result = parsedData(props.toolCall.tool_call_result?.content)
  if (result?.query) return result.query

  // Fallback to args
  const args = props.toolCall.args || props.toolCall.function?.arguments
  if (!args) return ''
  if (typeof args === 'object') return args.query || args.q || ''
  try {
    const parsed = JSON.parse(args)
    return parsed.query || parsed.q || ''
  } catch (e) {
    return ''
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

  .search-meta {
    padding: 12px 16px;
    background: var(--gray-25);
    display: flex;
    gap: 16px;
    font-size: 12px;
    color: var(--gray-600);
    border-bottom: 1px solid var(--gray-100);

    .query-text {
      font-weight: 500;
      color: var(--gray-800);
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
