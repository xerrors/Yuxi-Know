<template>
  <div class="knowledge-graph-result">
    <div class="kg-header">
      <h4><DeploymentUnitOutlined /> 知识图谱查询结果</h4>
      <div class="result-summary">
        找到 {{ totalNodes }} 个节点, {{ totalRelations }} 个关系
      </div>
    </div>

    <!-- 图谱可视化容器 -->
    <div class="graph-visualization" ref="graphContainerRef" v-if="totalNodes > 0 || totalRelations > 0">
      <GraphCanvas :graph-data="graphData" ref="graphContainer" style="height: 360px;">
        <template #top>
          <div class="graph-controls">
            <a-button
              @click="refreshGraph"
              :loading="isRefreshing"
              title="重新渲染图谱"
              class="refresh-btn"
            >
              <ReloadOutlined v-if="!isRefreshing" />
            </a-button>
            </div>
        </template>
      </GraphCanvas>
    </div>

  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick, onMounted, onUpdated } from 'vue'
import { DeploymentUnitOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import GraphCanvas from '../GraphCanvas.vue'

const props = defineProps({
  data: {
    type: [Array, Object],
    required: true
  }
})

const activeKeys = ref(['entities'])
const graphContainer = ref(null)
const graphContainerRef = ref(null)
const isVisible = ref(false)
const isRefreshing = ref(false)

// 计算属性：解析图谱数据
const graphData = computed(() => {
  const nodes = new Map()
  const edges = []
  let edgeId = 0

  // 处理新格式数据：只关注 triples 字段
  if (props.data && typeof props.data === 'object' && 'triples' in props.data) {
    const { triples = [] } = props.data

    // 处理 triples 数据
    triples.forEach(triple => {
      if (Array.isArray(triple) && triple.length >= 3) {
        const [source, relation, target] = triple

        // 添加源节点
        if (source && typeof source === 'string') {
          if (!nodes.has(source)) {
            nodes.set(source, {
              id: source,
              name: source
            })
          }
        }

        // 添加目标节点
        if (target && typeof target === 'string') {
          if (!nodes.has(target)) {
            nodes.set(target, {
              id: target,
              name: target
            })
          }
        }

        // 添加边
        if (source && target && relation &&
            typeof source === 'string' &&
            typeof target === 'string' &&
            typeof relation === 'string') {
          edges.push({
            source_id: source,
            target_id: target,
            type: relation,
            id: `edge_${edgeId++}`
          })
        }
      }
    })
  }

  return {
    nodes: Array.from(nodes.values()),
    edges: edges
  }
})

// 唯一实体列表
const uniqueEntities = computed(() => {
  return graphData.value.nodes
})

// 所有关系列表
const allRelations = computed(() => {
  return graphData.value.edges.map(edge => {
    const sourceNode = graphData.value.nodes.find(n => n.id === edge.source_id)
    const targetNode = graphData.value.nodes.find(n => n.id === edge.target_id)
    return {
      source: sourceNode?.name || edge.source_id,
      target: targetNode?.name || edge.target_id,
      type: edge.type
    }
  })
})

// 统计信息
const totalNodes = computed(() => graphData.value.nodes.length)
const totalRelations = computed(() => graphData.value.edges.length)

// 检查容器是否可见
const checkVisibility = () => {
  if (graphContainerRef.value) {
    const rect = graphContainerRef.value.getBoundingClientRect();
    isVisible.value = rect.width > 0 && rect.height > 0;
    console.log('GraphContainer visibility:', isVisible.value, 'dimensions:', rect.width, 'x', rect.height);
  }
};

// 当数据变化时强制刷新图表
watch(() => props.data, async (newData, oldData) => {
  // 确保数据确实发生了变化
  if (newData !== oldData) {
    await nextTick();
    if (graphContainer.value && typeof graphContainer.value.refreshGraph === 'function') {
      // 增加延迟确保容器完全展开
      setTimeout(() => {
        graphContainer.value.refreshGraph();
      }, 300);
    }
  }
}, { deep: true });

// 组件挂载后确保图表正确初始化
onMounted(() => {
  // 检查可见性
  checkVisibility();

  // 如果已经有数据，确保图表初始化
  if (graphData.value.nodes.length > 0 || graphData.value.edges.length > 0) {
    nextTick(() => {
      if (graphContainer.value && typeof graphContainer.value.refreshGraph === 'function') {
        // 增加延迟确保容器完全展开
        setTimeout(() => {
          graphContainer.value.refreshGraph();
        }, 300);
      }
    });
  }

  // 添加一个间隔检查器，定期检查容器是否可见
  const visibilityChecker = setInterval(() => {
    checkVisibility();
    if (isVisible.value && graphContainer.value && typeof graphContainer.value.refreshGraph === 'function') {
      console.log('GraphContainer is now visible, rendering graph');
      graphContainer.value.refreshGraph();
      clearInterval(visibilityChecker);
    }
  }, 500);

  // 5秒后清除检查器
  setTimeout(() => {
    clearInterval(visibilityChecker);
  }, 5000);
});

// 组件更新后再次确保图表正确初始化
onUpdated(() => {
  // 检查可见性
  checkVisibility();

  // 如果已经有数据，确保图表初始化
  if (graphData.value.nodes.length > 0 || graphData.value.edges.length > 0) {
    nextTick(() => {
      if (graphContainer.value && typeof graphContainer.value.refreshGraph === 'function') {
        // 增加延迟确保容器完全展开
        setTimeout(() => {
          graphContainer.value.refreshGraph();
        }, 300);
      }
    });
  }
});

// 添加供父组件调用的刷新方法
const refreshGraph = () => {
  console.log('KnowledgeGraphResult: refreshGraph called');
  isRefreshing.value = true;
  if (graphContainer.value && typeof graphContainer.value.refreshGraph === 'function') {
    // 增加延迟确保容器完全展开
    setTimeout(() => {
      graphContainer.value.refreshGraph();
      setTimeout(() => {
        isRefreshing.value = false;
      }, 500);
    }, 300);
  } else {
    isRefreshing.value = false;
  }
};


// 向父组件暴露方法
defineExpose({
  refreshGraph
});
</script>

<style lang="less" scoped>
.knowledge-graph-result {
  background: var(--gray-0);
  border-radius: 8px;
  // border: 1px solid var(--gray-200);

  .kg-header {
    padding: 12px 16px;
    // border-bottom: 1px solid var(--gray-200);
    background: var(--gray-25);

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

  .graph-visualization {
    margin: 8px;
    background: var(--gray-0);
    border-radius: 6px;
    border: 1px solid var(--gray-200);
    min-height: 350px;

    .graph-controls {
      position: absolute;
      top: 8px;
      right: 8px;
      z-index: 1000;

      .refresh-btn {
        width: 24px;
        height: 24px;
        min-width: 24px;
        padding: 0;
        border-radius: 4px;
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid var(--gray-300);
        color: var(--gray-600);
        font-size: 12px;
        display: flex;
        align-items: center;
        justify-content: center;

        &:hover {
          background: rgba(255, 255, 255, 1);
          border-color: var(--main-color);
          color: var(--main-color);
        }
      }
    }
  }

  .kg-details {
    margin: 8px;
    background: var(--gray-0);
    border-radius: 6px;
    border: 1px solid var(--gray-200);

    :deep(.ant-collapse-header) {
      background: var(--gray-50) !important;
      border-radius: 4px !important;
      margin-bottom: 2px;
      font-size: 13px;
    }

    .entities-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 6px 0;

      .entity-tag {
        margin: 0;
        cursor: default;
        font-size: 11px;
        padding: 2px 6px;
      }
    }

    .relations-list {
      display: flex;
      flex-direction: column;
      gap: 6px;

      .relation-item {
        padding: 8px 10px;
        background: var(--gray-50);
        border-radius: 4px;
        border-left: 2px solid var(--main-color);

        .relation-content {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 12px;

          .entity-name {
            font-weight: 500;
            color: var(--main-color);
            background: var(--main-50);
            padding: 2px 6px;
            border-radius: 10px;
          }

          .relation-type {
            color: var(--main-color);
            font-weight: 500;
            background: var(--gray-100);
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid var(--gray-300);
          }
        }
      }
    }

    .raw-data {
      background: var(--gray-50);
      padding: 10px;
      border-radius: 4px;
      font-size: 11px;
      line-height: 1.4;
      max-height: 200px;
      overflow-y: auto;
      margin: 0;
      color: var(--gray-700);
    }
  }
}

</style>