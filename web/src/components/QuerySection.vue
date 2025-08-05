<template>
  <div class="query-section" :class="{ collapsed: !visible }" :style="style">
    <div class="section-header">
      <h3 class="section-title">检索测试</h3>
      <div class="panel-actions">
        <a-popover trigger="click" placement="bottomRight" class="query-params-popover">
          <template #content>
            <div class="query-params-compact">
              <div v-if="loading" class="params-loading">
                <a-spin size="small" />
              </div>
              <div v-else class="params-grid">
                <div v-for="param in queryParams" :key="param.key" class="param-item">
                  <label>{{ param.label }}:</label>
                  <a-select
                    v-if="param.type === 'select'"
                    v-model:value="meta[param.key]"
                    size="small"
                    style="width: 80px;"
                  >
                    <a-select-option
                      v-for="option in param.options"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </a-select-option>
                  </a-select>
                  <a-switch
                    v-else-if="param.type === 'boolean'"
                    v-model:checked="meta[param.key]"
                    size="small"
                  />
                  <a-input-number
                    v-else-if="param.type === 'number'"
                    v-model:value="meta[param.key]"
                    size="small"
                    style="width: 60px;"
                    :min="param.min || 0"
                    :max="param.max || 100"
                  />
                </div>
              </div>
            </div>
          </template>
          <a-button
            type="text"
            size="small"
            :icon="h(SettingOutlined)"
            title="查询参数"
          >查询参数</a-button>
        </a-popover>
        <a-button
          type="text"
          size="small"
          @click="toggleVisible"
          title="折叠/展开"
        >
          <component :is="visible ? UpOutlined : DownOutlined" />
        </a-button>
      </div>
    </div>

    <div class="query-content content" v-show="visible">
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
          >
            <template #icon>
              <SearchOutlined />
            </template>
            搜索
          </a-button>
          <div class="query-examples-compact">
            <span class="examples-label">示例：</span>
            <div class="examples-container">
              <transition name="fade" mode="out-in">
                <a-button
                  type="text"
                  :key="currentExampleIndex"
                  @click="useQueryExample(queryExamples[currentExampleIndex])"
                  size="small"
                  class="example-btn"
                >
                  {{ queryExamples[currentExampleIndex] }}
                </a-button>
              </transition>
            </div>
          </div>
        </div>
      </div>

      <div class="query-results" v-if="queryResult">
        {{ queryResult }}
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
  UpOutlined,
  DownOutlined,
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

// 添加调试日志
console.log('QuerySection props:', props);
console.log('QuerySection style prop:', props.style);

const emit = defineEmits(['toggleVisible']);

const loading = computed(() => store.state.queryParamsLoading);
const searchLoading = computed(() => store.state.searchLoading);
const queryParams = computed(() => store.queryParams);
const meta = computed({
  get: () => store.meta,
  set: (value) => Object.assign(store.meta, value)
});
const queryResult = ref('');

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

const toggleVisible = () => {
  emit('toggleVisible');
};

const onQuery = async () => {
  if (!queryText.value.trim()) {
    message.error('请输入查询内容');
    return;
  }

  store.state.searchLoading = true;

  // 确保只传递当前知识库类型支持的参数
  const supportedParamKeys = new Set(queryParams.value.map(param => param.key));
  const queryMeta = {};

  console.log('Supported param keys:', Array.from(supportedParamKeys));
  console.log('All meta params:', meta.value);
  console.log('Database info:', store.database);

  // 遍历 meta 中的参数，只保留当前知识库类型支持的参数
  for (const [key, value] of Object.entries(meta.value)) {
    // 跳过 db_id 参数
    if (key === 'db_id') continue;

    // 只保留当前知识库类型支持的参数
    if (supportedParamKeys.has(key)) {
      queryMeta[key] = value;
    } else {
      console.log(`Skipping unsupported parameter: ${key}`);
    }
  }

  console.log('Filtered query meta:', queryMeta);

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
  .query-content {
    padding: 8px 8px;
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .query-input-container {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 12px;
  }

  .compact-query-textarea {
    flex: 1;
    // background: white;
    // box-shadow: 0 0px 4px rgba(0, 0, 0, 0.1);
    // border: none;
    // outline: none;

    &:focus {
      // border: none;
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
    padding: 12px;
    background-color: #f5f5f5;
    border-radius: 4px;
    white-space: pre-wrap;
    word-break: break-all;
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    font-size: small;
  }

  .query-params-compact {
    min-width: 200px;
  }

  .params-loading {
    display: flex;
    justify-content: center;
    padding: 16px;
  }

  .params-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  .param-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .param-item label {
    font-size: 12px;
    color: #666;
  }
}
</style>