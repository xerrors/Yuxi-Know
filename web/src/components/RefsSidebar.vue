<template>
  <div>
    <a-drawer
      :open="visible"
      title="参考信息"
      :width="700"
      :contentWrapperStyle="{ maxWidth: '100%'}"
      placement="right"
      class="refs-sidebar"
      rootClassName="root"
      @close="$emit('update:visible', false)"
      @afterOpenChange="handleAfterVisibleChange"
    >
      <a-tabs v-model:activeKey="activeTab">
        <!-- 关系图 -->
        <a-tab-pane key="graph" tab="关系图" :disabled="!hasGraphData">
          <div v-if="hasGraphData" class="graph-container">
            <GraphContainer :graphData="latestRefs.graph_base.results" ref="graphContainerRef" />
          </div>
          <div v-else class="empty-data">
            <p>当前对话没有关系图数据</p>
          </div>
        </a-tab-pane>

        <!-- 网页搜索 -->
        <a-tab-pane key="webSearch" tab="网页搜索" :disabled="!hasWebSearchData">
          <div v-if="hasWebSearchData" class="results-list">
            <div v-for="result in latestRefs.web_search.results" :key="result.url" class="result-item">
              <div class="result-meta">
                <div class="score-info">
                  <span>
                    <strong>相关度：</strong>
                    <a-progress :percent="getPercent(result.score)"/>
                  </span>
                </div>
              </div>
              <div class="result-content">
                <h3 class="result-title">{{ result.title }}</h3>
                <div class="result-url">
                  <a :href="result.url" target="_blank">{{ result.url }}</a>
                </div>
                <div class="result-text">{{ result.content }}</div>
              </div>
            </div>
          </div>
          <div v-else class="empty-data">
            <p>当前对话没有网页搜索数据</p>
          </div>
        </a-tab-pane>

        <!-- 知识库 -->
        <a-tab-pane key="knowledgeBase" tab="知识库" :disabled="!hasKnowledgeBaseData">
          <div v-if="hasKnowledgeBaseData">
            <div class="file-list">
              <a-collapse v-model:activeKey="activeFiles">
                <a-collapse-panel
                  v-for="(results, filename) in groupedKnowledgeResults"
                  :key="filename"
                  :header="filename"
                >
                  <div class="fileinfo" v-if="results.length > 0">
                    <p><FileOutlined /> {{ results[0].file.type }}</p>
                    <p><ClockCircleOutlined /> {{ formatDate(results[0].file.created_at) }}</p>
                  </div>
                  <div class="results-list">
                    <div v-for="res in results" :key="res.id" class="result-item">
                      <div class="result-meta">
                        <div class="score-info">
                          <span>
                            <strong>相似度：</strong>
                            <a-progress :percent="getPercent(res.distance)"/>
                          </span>
                          <span v-if="res.rerank_score">
                            <strong>重排序：</strong>
                            <a-progress :percent="getPercent(res.rerank_score)"/>
                          </span>
                        </div>
                        <div class="result-id">ID: #{{ res.id }}</div>
                      </div>
                      <div class="result-text">{{ res.entity.text }}</div>
                    </div>
                  </div>
                </a-collapse-panel>
              </a-collapse>
            </div>
          </div>
          <div v-else class="empty-data">
            <p>当前对话没有知识库查询数据</p>
          </div>
        </a-tab-pane>
      </a-tabs>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch, nextTick } from 'vue'
import {
  FileOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons-vue'
import GraphContainer from './GraphContainer.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  latestRefs: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:visible'])

// 标签页相关
const activeTab = ref('graph')
const activeFiles = ref([])

// 计算属性：是否有各类数据
const hasGraphData = computed(() => {
  try {
    return !!(props.latestRefs &&
      props.latestRefs.graph_base &&
      props.latestRefs.graph_base.results &&
      props.latestRefs.graph_base.results.nodes &&
      Array.isArray(props.latestRefs.graph_base.results.nodes) &&
      props.latestRefs.graph_base.results.nodes.length > 0);
  } catch (e) {
    console.error('Error checking graph data:', e);
    return false;
  }
})

const hasWebSearchData = computed(() => {
  try {
    // 更加容忍数据结构的不完整
    return !!(props.latestRefs &&
      props.latestRefs.web_search &&
      Array.isArray(props.latestRefs.web_search.results) &&
      props.latestRefs.web_search.results.length > 0);
  } catch (e) {
    console.error('Error checking web search data:', e);
    return false;
  }
})

const hasKnowledgeBaseData = computed(() => {
  try {
    return !!(props.latestRefs &&
      props.latestRefs.knowledge_base &&
      props.latestRefs.knowledge_base.results &&
      Array.isArray(props.latestRefs.knowledge_base.results) &&
      props.latestRefs.knowledge_base.results.length > 0);
  } catch (e) {
    console.error('Error checking knowledge base data:', e);
    return false;
  }
})

// 知识库结果按文件分组
const groupedKnowledgeResults = computed(() => {
  if (!hasKnowledgeBaseData.value) return {}

  return props.latestRefs.knowledge_base.results
    .filter(result => result.file && result.file.filename)
    .reduce((acc, result) => {
      const { filename } = result.file
      if (!acc[filename]) {
        acc[filename] = []
      }
      acc[filename].push(result)
      return acc
    }, {})
})

// 自动选择有数据的第一个标签页
watch(() => props.visible, (newValue) => {
  console.log('RefsSidebar visible changed to', newValue, 'activeTab is', activeTab.value);

  if (newValue) {
    console.log('Checking which tabs are available');
    // 只有在activeTab无效的情况下才自动选择标签页
    const currentTabValid =
      (activeTab.value === 'graph' && hasGraphData.value) ||
      (activeTab.value === 'webSearch' && hasWebSearchData.value) ||
      (activeTab.value === 'knowledgeBase' && hasKnowledgeBaseData.value);

    if (!currentTabValid) {
      console.log('Current tab is invalid, finding first available tab');
      // 当前标签无效，需要寻找一个有效的标签
      if (hasGraphData.value) {
        console.log('Selected graph tab');
        activeTab.value = 'graph';
      } else if (hasWebSearchData.value) {
        console.log('Selected webSearch tab');
        activeTab.value = 'webSearch';
      } else if (hasKnowledgeBaseData.value) {
        console.log('Selected knowledgeBase tab');
        activeTab.value = 'knowledgeBase';
        // 打开第一个文件
        if (Object.keys(groupedKnowledgeResults.value).length > 0) {
          activeFiles.value = [Object.keys(groupedKnowledgeResults.value)[0]];
        }
      } else {
        console.log('No valid tabs available');
      }
    } else {
      console.log('Current tab is valid, keeping it:', activeTab.value);
    }
  }
});

// 百分比计算函数
const getPercent = (value) => {
  return parseFloat((value * 100).toFixed(2))
}

// 日期格式化函数
const formatDate = (timestamp) => {
  return new Date(timestamp * 1000).toLocaleString()
}

// 手动设置活动标签页
const setActiveTab = (tab) => {
  console.log('RefsSidebar setActiveTab called with tab:', tab);
  console.log('Current tabs available:', {
    graph: hasGraphData.value,
    webSearch: hasWebSearchData.value,
    knowledgeBase: hasKnowledgeBaseData.value
  });
  console.log('Full latestRefs structure:', JSON.stringify(props.latestRefs));

  // 如果要设置的标签是有效的，直接设置
  if ((tab === 'graph' && hasGraphData.value) ||
      (tab === 'webSearch' && hasWebSearchData.value) ||
      (tab === 'knowledgeBase' && hasKnowledgeBaseData.value)) {
    console.log('Setting activeTab to:', tab);
    activeTab.value = tab;
  } else {
    console.warn(`Cannot set tab to ${tab}, tab is disabled or invalid`);

    // 如果特定标签数据不可用，但数据存在，尝试强制启用相应标签
    if (tab === 'webSearch' && props.latestRefs.web_search) {
      console.log('Forcing webSearch tab even though hasWebSearchData is false');
      activeTab.value = 'webSearch';
    } else if (tab === 'knowledgeBase' && props.latestRefs.knowledge_base) {
      console.log('Forcing knowledgeBase tab even though hasKnowledgeBaseData is false');
      activeTab.value = 'knowledgeBase';
    } else if (tab === 'graph' && props.latestRefs.graph_base) {
      console.log('Forcing graph tab even though hasGraphData is false');
      activeTab.value = 'graph';
    }
  }
}

// 图表ref
const graphContainerRef = ref(null);

// 处理抽屉完全打开后的事件
const handleAfterVisibleChange = (visible) => {
  console.log('RefsSidebar afterOpenChange fired, visible:', visible, 'activeTab:', activeTab.value);

  if (!visible) return;

  // 根据当前活动标签页执行相应的刷新操作
  nextTick(() => {
    if (activeTab.value === 'graph' && hasGraphData.value) {
      console.log('Refreshing graph after drawer opened');
      // 触发图表容器的重新布局
      if (graphContainerRef.value && graphContainerRef.value.refreshGraph) {
        graphContainerRef.value.refreshGraph();
      }
    } else {
      console.log('Current active tab is', activeTab.value, 'no need to refresh graph');
    }
  });
};

// 监听标签页变化
watch(activeTab, (newTab) => {
  if (newTab === 'graph' && hasGraphData.value && props.visible) {
    // 切换到图表标签时，需要延迟一下重新渲染图表
    nextTick(() => {
      if (graphContainerRef.value && graphContainerRef.value.refreshGraph) {
        graphContainerRef.value.refreshGraph();
      }
    });
  }
});

// 监视latestRefs的变化，便于调试
watch(() => props.latestRefs, (newRefs) => {
  console.log('RefsSidebar latestRefs changed:', {
    hasGraph: hasGraphData.value,
    hasWeb: hasWebSearchData.value,
    hasKB: hasKnowledgeBaseData.value,
    graph: newRefs.graph_base?.results?.nodes?.length,
    web: newRefs.web_search?.results?.length,
    kb: newRefs.knowledge_base?.results?.length
  });
}, { deep: true });

// 向父组件暴露方法
defineExpose({
  setActiveTab
})
</script>

<style lang="less" scoped>
.refs-sidebar {
  .empty-data {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 200px;
    color: #999;
    font-size: 14px;
    background-color: #f9f9f9;
    border-radius: 4px;
  }

  .graph-container {
    min-height: 500px;
    width: 100%;
    display: flex;
    justify-content: center;
    align-items: center;
  }

  .fileinfo {
    display: flex;
    justify-content: space-between;
    padding: 12px 16px;
    background-color: #f5f5f5;
    border-radius: 4px;
    margin-bottom: 16px;

    p {
      margin: 0;
      color: #666;
    }
  }

  .results-list {
    .result-item {
      border-bottom: 1px solid #f0f0f0;
      padding: 16px 0;

      &:last-child {
        border-bottom: none;
      }
    }

    .result-meta {
      margin-bottom: 12px;

      .score-info {
        display: flex;
        flex-wrap: wrap;
        gap: 2rem;
        margin-bottom: 8px;

        span {
          display: flex;
          align-items: center;

          strong {
            margin-right: 8px;
            white-space: nowrap;
            color: #666;
          }

          .ant-progress {
            width: 170px;
            margin-bottom: 0;
            margin-inline: 10px;

            .ant-progress-bg {
              background-color: #666;
            }
          }
        }
      }

      .result-id {
        font-size: 12px;
        color: #999;
        margin-bottom: 8px;
      }
    }

    .result-content {
      .result-title {
        font-size: 16px;
        font-weight: bold;
        margin-bottom: 8px;
        color: #333;
      }


      .result-url {
        font-size: 12px;
        color: #0563e7;
        margin-bottom: 8px;
        a {
          color: #0563e7;
          word-break: break-all;
        }
      }

      .result-text {
        font-size: 14px;
        line-height: 1.6;
        white-space: pre-wrap;
        word-break: break-word;
        background-color: #f9f9f9;
        padding: 12px;
        border-radius: 4px;
        border: 1px solid #e8e8e8;
      }
    }
  }
}
</style>