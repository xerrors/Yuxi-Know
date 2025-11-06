<template>
  <div class="query-section" :class="{ collapsed: !visible }" :style="style">
    <div class="query-section-layout">
      <!-- 主内容区域 -->
      <div class="query-main">
        <div class="query-header">
          <div class="header-status">
            <a-switch
              v-model:checked="showRawData"
              size="small"
              checked-children="原始数据"
              un-checked-children="格式化"
            />
            <span v-if="searchLoading" class="search-status">
              <a-spin size="small" />
              搜索中...
            </span>
            <span v-else-if="queryResult" class="result-count">
              找到 {{ resultCount }} 条结果
            </span>
          </div>
        </div>

        <div class="query-input-container">
          <a-textarea
            v-model:value="queryText"
            placeholder="输入查询内容"
            :auto-size="{ minRows: 3, maxRows: 6 }"
            class="compact-query-textarea"
          />
          <div class="query-actions-row">
            <a-button
              @click="onQuery"
              :loading="searchLoading"
              class="search-button"
              type="primary"
            >
              <template #icon>
                <SearchOutlined />
              </template>
              搜索
            </a-button>
            <div class="query-examples-compact">
              <span class="examples-label">示例：</span>
              <div class="examples-container">
                <a-button
                  type="text"
                  :key="currentExampleIndex"
                  @click="useQueryExample(queryExamples[currentExampleIndex])"
                  size="small"
                  class="example-btn"
                >
                  {{ queryExamples[currentExampleIndex] }}
                </a-button>
              </div>
            </div>
          </div>
        </div>

        <div class="query-results" v-if="queryResult">
          <!-- 原始数据显示 -->
          <div v-if="showRawData" class="result-raw">
            <pre>{{ JSON.stringify(queryResult, null, 2) }}</pre>
          </div>

          <!-- 格式化显示 -->
          <div v-else>
            <!-- LightRAG 返回字符串格式 -->
            <div v-if="typeof queryResult === 'string'" class="result-text">
              {{ queryResult }}
            </div>

            <!-- Chroma/Milvus 返回列表格式 -->
            <div v-else-if="Array.isArray(queryResult)" class="result-list">
              <div v-if="queryResult.length === 0" class="no-results">
                <p>未找到相关结果</p>
              </div>
              <div v-else>
                <div class="result-summary">
                  <strong>检索到 {{ queryResult.length }} 个相关文档块：</strong>
                </div>
                <div
                  v-for="(chunk, index) in queryResult"
                  :key="index"
                  class="result-item"
                >
                  <div class="result-header">
                    <span class="result-index">#{{ index + 1 }}</span>
                    <span v-if="chunk.score" class="result-score">
                      相似度: {{ (chunk.score * 100).toFixed(2) }}%
                    </span>
                    <span v-if="chunk.rerank_score" class="result-rerank-score">
                      重排序分数: {{ (chunk.rerank_score * 100).toFixed(2) }}%
                    </span>
                  </div>

                  <div class="result-content">
                    {{ chunk.content }}
                  </div>

                  <div class="result-metadata">
                    <span v-if="chunk.metadata?.source" class="metadata-item">
                      <strong>来源:</strong> {{ chunk.metadata.source }}
                    </span>
                    <span v-if="chunk.metadata?.file_id" class="metadata-item">
                      <strong>文件ID:</strong> {{ chunk.metadata.file_id }}
                    </span>
                    <span v-if="chunk.metadata?.chunk_index !== undefined" class="metadata-item">
                      <strong>块索引:</strong> {{ chunk.metadata.chunk_index }}
                    </span>
                    <span v-if="chunk.distance !== undefined" class="metadata-item">
                      <strong>距离:</strong> {{ chunk.distance.toFixed(4) }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 其他格式（降级处理） -->
            <div v-else class="result-unknown">
              <pre>{{ JSON.stringify(queryResult, null, 2) }}</pre>
            </div>
          </div> <!-- 关闭格式化显示的div -->
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useDatabaseStore } from '@/stores/database';
import { message } from 'ant-design-vue';
import { queryApi } from '@/apis/knowledge_api';
import {
  SearchOutlined,
  SettingOutlined,
  CloseOutlined,
} from '@ant-design/icons-vue';
import { h } from 'vue';

const store = useDatabaseStore();

const props = defineProps({
  visible: {
    type: Boolean,
    default: true
  },
  style: {
    type: Object,
    default: () => ({})
  },
});


const searchLoading = computed(() => store.state.searchLoading);
const queryResult = ref('');
const showRawData = ref(false);
const resultCount = ref(0);

// 查询测试
const queryText = ref('');

// 添加更多示例查询
const queryExamples = ref([
  '孕妇应该避免吃哪些水果？',
  '荔枝应该怎么清洗？',
  '如何判断西瓜是否成熟？',
  '苹果有哪些营养价值？',
  '什么季节最适合吃梨？',
  '如何保存草莓以延长保质期？',
  '香蕉变黑后还能吃吗？',
  '橙子皮可以用来做什么？'
]);

// 当前示例索引
const currentExampleIndex = ref(0);

// 示例轮播相关
let exampleCarouselInterval = null;


const onQuery = async () => {
  if (!queryText.value.trim()) {
    message.error('请输入查询内容');
    return;
  }

  store.state.searchLoading = true;

  // 从store中获取配置参数
  const queryMeta = { ...store.meta };

  try {
    const data = await queryApi.queryTest(store.database.db_id, queryText.value.trim(), queryMeta);
    queryResult.value = data;

    // 计算结果数量
    if (data?.data && Array.isArray(data.data)) {
      resultCount.value = data.data.length;
    } else if (data) {
      resultCount.value = 1;
    }

  } catch (error) {
    console.error(error);
    message.error(error.message);
    queryResult.value = '';
    resultCount.value = 0;
  } finally {
    store.state.searchLoading = false;
  }
};

const useQueryExample = (example) => {
  queryText.value = example;
  onQuery();
};

const startExampleCarousel = () => {
  if (exampleCarouselInterval) return;

  exampleCarouselInterval = setInterval(() => {
    currentExampleIndex.value = (currentExampleIndex.value + 1) % queryExamples.value.length;
  }, 6000); // 每6秒切换一次
};

const stopExampleCarousel = () => {
  if (exampleCarouselInterval) {
    clearInterval(exampleCarouselInterval);
    exampleCarouselInterval = null;
  }
};

// 组件挂载时启动示例轮播
onMounted(() => {
  // 启动示例轮播
  startExampleCarousel();

  // 加载查询参数
  store.loadQueryParams();

  });

// 组件卸载时停止示例轮播
onUnmounted(() => {
  // 停止示例轮播
  stopExampleCarousel();
});
</script>

<style scoped lang="less">
.query-section {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.query-section-layout {
  height: 100%;
  overflow: hidden;
}

// 主内容区域
.query-main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.query-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--gray-200);
  background-color: #fff;

  .header-status {
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 13px;
    color: var(--gray-600);

    .search-status {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .result-count {
      font-weight: 500;
    }
  }
}

.query-input-container {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background-color: #fff;
  border-bottom: 1px solid var(--gray-200);
}

.compact-query-textarea {
  flex: 1;

  &:focus {
    outline: none;
  }
}

.query-actions-row {
  display: flex;
  gap: 16px;
  align-items: center;
}

.search-button {
  flex-shrink: 0;
}

.query-examples-compact {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.examples-label {
  font-size: 12px;
  color: #8c8c8c;
  white-space: nowrap;
}

.examples-container {
  min-height: 24px;
  display: flex;
}

.example-btn {
  text-align: left;
  white-space: normal;
  height: auto;
  padding: 4px 8px;
  font-size: 12px;
}

.query-results {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background-color: #fafafa;
  min-height: 0;

  .result-raw {
    background-color: #f8f9fa;
    border: 1px solid var(--gray-200);
    border-radius: 6px;
    padding: 16px;
    overflow-x: auto;

    pre {
      margin: 0;
      font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
      font-size: 12px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
  }

  .result-text {
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.6;
  }

  .result-list {
    .no-results {
      text-align: center;
      padding: 32px;
      color: #999;
    }

    .result-summary {
      margin-bottom: 12px;
      padding: 8px 12px;
      background-color: #e6f7ff;
      border-left: 3px solid var(--main-color);
      border-radius: 2px;
    }

    .result-item {
      background-color: white;
      border: 1px solid #e8e8e8;
      border-radius: 6px;
      padding: 12px;
      margin-bottom: 12px;

      &:hover {
        border-color: var(--gray-400);
      }

      &:last-child {
        margin-bottom: 0;
      }

      .result-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 8px;
        padding-bottom: 8px;
        border-bottom: 1px solid #f0f0f0;

        .result-index {
          font-weight: 600;
          color: var(--main-color);
          font-size: 14px;
        }

        .result-score,
        .result-rerank-score {
          font-size: 12px;
          padding: 2px 8px;
          border-radius: 12px;
          background-color: #f0f0f0;
          color: #666;
        }

        .result-rerank-score {
          background-color: #fff7e6;
          color: #fa8c16;
        }
      }

      .result-content {
        padding: 8px 0;
        line-height: 1.6;
        color: #333;
        white-space: pre-wrap;
        word-break: break-word;
      }

      .result-metadata {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px solid #f0f0f0;

        .metadata-item {
          font-size: 12px;
          color: #666;

          strong {
            color: #999;
            font-weight: 500;
            margin-right: 4px;
          }
        }
      }
    }
  }

  .result-unknown {
    pre {
      background-color: white;
      padding: 12px;
      border-radius: 4px;
      overflow-x: auto;
      font-size: 12px;
    }
  }
}

</style>