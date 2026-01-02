<template>
  <div class="query-section" :class="{ collapsed: !visible }" :style="style">
    <div class="query-section-layout">
      <!-- 主内容区域 -->
      <div class="query-main">
        <div class="query-input-container">
          <div class="search-input-wrapper">
            <a-textarea
              v-model:value="queryText"
              placeholder="输入查询内容..."
              :auto-size="{ minRows: 2, maxRows: 6 }"
              class="search-textarea"
              @press-enter.prevent="onQuery"
            />
            <div class="search-actions">
                <div class="query-examples-compact">
                  <div class="examples-label-group">
                    <a-tooltip title="点击手动生成测试问题" placement="bottom">
                      <a-button
                      type="text"
                      size="small"
                      class="examples-label-btn"
                      @click="() => generateSampleQuestions(false)"
                    >
                      示例:
                    </a-button>
                  </a-tooltip>
                </div>
                <div class="examples-container">
                  <!-- 加载中或生成中 -->
                  <div v-if="loadingQuestions || generatingQuestions" class="loading-text">
                    <a-spin size="small" />
                    <span>{{ generatingQuestions ? 'AI生成中...' : '加载中...' }}</span>
                  </div>

                  <!-- 示例轮播 -->
                  <transition v-else-if="queryExamples.length > 0" name="fade" mode="out-in">
                    <a-button
                      type="link"
                      :key="currentExampleIndex"
                      @click="useQueryExample(queryExamples[currentExampleIndex])"
                      size="small"
                      class="example-btn"
                    >
                      {{ queryExamples[currentExampleIndex] }}
                    </a-button>
                  </transition>

                  <!-- 空状态 - 添加文件后会自动生成 -->
                  <span v-else style="color: var(--gray-500); font-size: 12px;">暂无问题，请点击左侧按钮生成</span>
                </div>
              </div>
              <div style="display: flex; gap: 12px; align-items: center;">
                <a-switch
                  v-if="!isLightRAG"
                  v-model:checked="showRawData"
                  checked-children="格式化"
                  un-checked-children="原始"
                />
                <a-button
                  @click="onQuery"
                  :loading="searchLoading"
                  class="search-button"
                  type="primary"
                  :disabled="!queryText.trim()"
                  :icon=h(SearchOutlined)
                  shape="circle"
                />
              </div>
            </div>
          </div>
        </div>

        <div class="query-results" v-if="queryResult">
          <!-- 原始数据显示 -->
          <div v-if="!showRawData" class="result-raw">
            <pre>{{ JSON.stringify(queryResult, null, 2) }}</pre>
          </div>

          <!-- 格式化显示 -->
          <div v-else>
            <!-- LightRAG 返回字符串格式 -->
            <div v-if="typeof queryResult === 'string'" class="result-text">
              {{ queryResult }}
            </div>

            <!-- Milvus 返回列表格式 -->
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
import { ref, computed, onMounted, onUnmounted, watch, h } from 'vue';
import { useDatabaseStore } from '@/stores/database';
import { message } from 'ant-design-vue';
import { queryApi } from '@/apis/knowledge_api';
import {
  SearchOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue';

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

// 声明事件
const emit = defineEmits(['toggleVisible']);

const searchLoading = computed(() => store.state.searchLoading);
const queryResult = ref('');
const showRawData = ref(true);

// 判断是否为 LightRAG 类型知识库
const isLightRAG = computed(() => store.database?.kb_type?.toLowerCase() === 'lightrag');

// 查询测试
const queryText = ref('');

// 示例问题相关
const queryExamples = ref([]);
const currentExampleIndex = ref(0);
const loadingQuestions = ref(false);
const generatingQuestions = ref(false);
const searchConfigModalVisible = ref(false);

// 示例轮播相关
let exampleCarouselInterval = null;

// 方法定义

// 打开检索配置弹窗
const openSearchConfigModal = () => {
  searchConfigModalVisible.value = true;
};

// 处理检索配置保存
const handleSearchConfigSave = (config) => {
  console.log('查询测试中的检索配置已更新:', config);
  // 可以在这里添加配置更新后的处理逻辑，比如重新查询
};

// 加载示例问题
const loadSampleQuestions = async () => {
  if (!store.database?.db_id) return;

  try {
    loadingQuestions.value = true;
    const data = await queryApi.getSampleQuestions(store.database.db_id);
    if (data.questions && data.questions.length > 0) {
      queryExamples.value = data.questions;
    } else {
      // 如果没有问题，清空列表
      queryExamples.value = [];
    }
  } catch (error) {
    // 404表示还没有生成问题，清空问题列表
    if (error.status === 404 || error?.message?.includes('404') || error?.message?.includes('还没有生成')) {
      queryExamples.value = [];
    } else {
      console.error('加载示例问题失败:', error);
    }
  } finally {
    loadingQuestions.value = false;
  }
};

// 清空问题列表
const clearQuestions = () => {
  queryExamples.value = [];
  currentExampleIndex.value = 0;
  stopExampleCarousel();
};

// 生成示例问题
const generateSampleQuestions = async (silent = false) => {
  if (!store.database?.db_id) return;

  try {
    generatingQuestions.value = true;
    const data = await queryApi.generateSampleQuestions(store.database.db_id, 10);
    if (data.questions && data.questions.length > 0) {
      queryExamples.value = data.questions;
      if (!silent) {
        message.success(`成功生成 ${data.questions.length} 个测试问题`);
      }
      // 开始轮播
      if (!exampleCarouselInterval) {
        startExampleCarousel();
      }
    }
  } catch (error) {
    console.error('生成示例问题失败:', error);
    // 静默模式下不显示错误消息（自动生成时）
    if (!silent) {
      // 提取详细错误信息
      let errorMsg = '未知错误';
      if (error.response?.data?.detail) {
        errorMsg = error.response.data.detail;
      } else if (error.detail) {
        errorMsg = error.detail;
      } else if (error.message) {
        errorMsg = error.message;
      } else if (typeof error === 'string') {
        errorMsg = error;
      } else {
        errorMsg = JSON.stringify(error);
      }
      message.error('生成失败: ' + errorMsg);
    }
  } finally {
    generatingQuestions.value = false;
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
  }, 10000); // 每10秒切换一次
};

const stopExampleCarousel = () => {
  if (exampleCarouselInterval) {
    clearInterval(exampleCarouselInterval);
    exampleCarouselInterval = null;
  }
};

// 监听知识库ID变化，切换知识库时重新加载问题
watch(
  () => store.database?.db_id,
  async (newDbId, oldDbId) => {
    // 如果知识库ID发生变化
    if (newDbId && newDbId !== oldDbId) {
      // 停止当前轮播
      stopExampleCarousel();
      // 清空当前问题列表
      queryExamples.value = [];
      currentExampleIndex.value = 0;
      // 重新加载新知识库的问题
      await loadSampleQuestions();
      // 如果有问题，启动轮播
      if (queryExamples.value.length > 0) {
        startExampleCarousel();
      }
    }
  },
  { immediate: false }
);


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

  } catch (error) {
    console.error(error);
    message.error(error.message);
    queryResult.value = '';
  } finally {
    store.state.searchLoading = false;
  }
};

// 组件挂载时启动示例轮播
onMounted(async () => {
  // 加载查询参数
  store.loadQueryParams();

  // 加载示例问题
  await loadSampleQuestions();

  // 如果有示例问题，启动轮播
  if (queryExamples.value.length > 0) {
    startExampleCarousel();
  }
  // 不自动生成，只在创建知识库和添加文件时由 DataBaseInfoView 触发生成
});

// 组件卸载时停止示例轮播
onUnmounted(() => {
  // 停止示例轮播
  stopExampleCarousel();
});

// 检查是否已有问题
const hasQuestions = () => {
  return queryExamples.value.length > 0;
};

// 暴露给父组件的方法和属性
defineExpose({
  generateSampleQuestions,
  loadSampleQuestions,
  hasQuestions,
  clearQuestions,
  queryExamples
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
  max-height: 100%;
}

.query-input-container {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background-color: var(--gray-0);
}

.search-input-wrapper {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 16px 8px;
  border-radius: 12px;
  border: 1px solid var(--gray-200);
  background-color: var(--gray-0);
  box-shadow: 0 1px 3px var(--shadow-1);
  transition: border-color 0.5s ease, box-shadow 0.5s ease;

  &:hover {
    border-color: var(--main-400);
    box-shadow: 0 4px 12px var(--shadow-2);
  }

  :deep(.ant-input) {
    border-radius: 8px;
    background-color: var(--gray-0);
    color: var(--gray-1000);
    outline: none;
    border: none;
    box-shadow: none;
    padding: 0;
    transition: border-color 0.3s ease, box-shadow 0.3s ease;

    &:focus {
      outline: none;
      border: none;
    }

    &::placeholder {
      color: var(--gray-500);
    }
  }
}

.search-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.search-button {
  background-color: var(--main-color);
  border-color: var(--main-color);
  box-shadow: 0 2px 4px var(--shadow-3);
  transition: all 0.2s ease;

  &:hover:not(:disabled) {
    background-color: var(--main-bright);
    border-color: var(--main-bright);
    box-shadow: 0 4px 8px rgba(1, 136, 166, 0.25);
    transform: translateY(-1px);
  }

  &:disabled {
    opacity: 0.5;
    color: var(--gray-0);
    cursor: not-allowed;
    box-shadow: none;
    transform: none;
  }
}

.query-results {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background-color: var(--gray-25);
  min-height: 0;

  .result-raw {
    background-color: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 6px;
    padding: 16px;
    overflow-x: auto;

    pre {
      margin: 0;
      font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
      font-size: 12px;
      line-height: 1.5;
      color: var(--gray-1000);
      white-space: pre-wrap;
      word-break: break-word;
    }
  }

  .result-text {
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.6;
    color: var(--gray-1000);
  }

  .result-list {
    .no-results {
      text-align: center;
      padding: 32px;
      color: var(--gray-500);
    }

    .result-summary {
      margin-bottom: 12px;
      padding: 8px 12px;
      background-color: var(--main-50);
      border-left: 3px solid var(--main-color);
      border-radius: 2px;
      color: var(--gray-800);
    }

    .result-item {
      background-color: var(--gray-0);
      border: 1px solid var(--gray-200);
      border-radius: 6px;
      padding: 12px;
      margin-bottom: 12px;
      transition: all 0.2s ease;

      &:hover {
        border-color: var(--main-300);
        box-shadow: 0 2px 8px rgba(1, 97, 121, 0.08);
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
        border-bottom: 1px solid var(--gray-150);

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
          background-color: var(--gray-100);
          color: var(--gray-700);
        }

        .result-rerank-score {
          background-color: var(--color-warning-50);
          color: var(--color-warning-700);
        }
      }

      .result-content {
        padding: 8px 0;
        line-height: 1.6;
        color: var(--gray-900);
        white-space: pre-wrap;
        word-break: break-word;
      }

      .result-metadata {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px solid var(--gray-150);

        .metadata-item {
          font-size: 12px;
          color: var(--gray-700);

          strong {
            color: var(--gray-500);
            font-weight: 500;
            margin-right: 4px;
          }
        }
      }
    }
  }

  .result-unknown {
    pre {
      background-color: var(--gray-0);
      border: 1px solid var(--gray-200);
      padding: 12px;
      border-radius: 4px;
      overflow-x: auto;
      font-size: 12px;
      color: var(--gray-1000);
    }
  }
}

.query-examples-compact {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.examples-label-btn {
  color: var(--gray-500);
  font-size: 12px;
  display: flex;
  align-items: center;
  margin-left: -8px;
  margin-right: -6px;

  &:hover {
    color: var(--main-color);
    background-color: var(--gray-100);
  }

  .anticon { /* Target Ant Design icons directly */
    font-size: 10px; /* Make icon smaller */
  }
}

.examples-container {
  min-height: 24px;
  display: flex;
  align-items: center;
}

.loading-text {
  font-size: 12px;
  color: var(--gray-400);
  display: flex;
  align-items: center;
  gap: 6px;
}

.example-btn {
  text-align: left;
  white-space: normal;
  height: auto;
  padding: 0;
  font-size: 12px;
  color: var(--gray-500);

  &:hover {
    color: var(--main-color);
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

</style>
