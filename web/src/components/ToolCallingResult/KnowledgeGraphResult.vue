<template>
  <div class="knowledge-graph-result">
    <div class="kg-header">
      <h4><DeploymentUnitOutlined /> 知识图谱查询结果</h4>
      <div class="result-summary">
        找到 {{ totalNodes }} 个节点, {{ totalRelations }} 个关系
      </div>
    </div>

    <!-- 图谱可视化容器 -->
    <div class="graph-visualization">
      <GraphContainer :graph-data="graphData" ref="graphContainer" />
    </div>

    <!-- 详细信息展示 -->
    <div class="kg-details">
      <a-collapse v-model:activeKey="activeKeys" ghost>
        <a-collapse-panel key="entities" header="实体节点">
          <div class="entities-list">
            <a-tag
              v-for="entity in uniqueEntities"
              :key="entity.name"
              color="blue"
              class="entity-tag"
            >
              {{ entity.name }}
            </a-tag>
          </div>
        </a-collapse-panel>

        <a-collapse-panel key="relations" header="关系详情">
          <div class="relations-list">
            <div
              v-for="(relation, index) in allRelations"
              :key="index"
              class="relation-item"
            >
              <div class="relation-content">
                <span class="entity-name">{{ relation.source }}</span>
                <span class="relation-type">{{ relation.type }}</span>
                <span class="entity-name">{{ relation.target }}</span>
              </div>
            </div>
          </div>
        </a-collapse-panel>

        <a-collapse-panel key="raw" header="原始数据">
          <pre class="raw-data">{{ JSON.stringify(data, null, 2) }}</pre>
        </a-collapse-panel>
      </a-collapse>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { DeploymentUnitOutlined } from '@ant-design/icons-vue'
import GraphContainer from '../GraphContainer.vue'

const props = defineProps({
  data: {
    type: Array,
    required: true
  }
})

const activeKeys = ref(['entities'])
const graphContainer = ref(null)

// 计算属性：解析图谱数据
const graphData = computed(() => {
  const nodes = new Map()
  const edges = []
  let edgeId = 0

  // 遍历所有路径数据
  props.data.forEach(pathData => {
    if (Array.isArray(pathData) && pathData.length >= 3) {
      const [startNode, relations, endNode] = pathData

      // 添加起始节点
      if (startNode && startNode.properties && startNode.properties.name) {
        nodes.set(startNode.element_id, {
          id: startNode.element_id,
          name: startNode.properties.name
        })
      }

      // 添加结束节点
      if (endNode && endNode.properties && endNode.properties.name) {
        nodes.set(endNode.element_id, {
          id: endNode.element_id,
          name: endNode.properties.name
        })
      }

      // 添加关系
      if (Array.isArray(relations)) {
        relations.forEach(relation => {
          if (relation && relation.nodes && relation.type && relation.properties) {
            const [sourceNode, targetNode] = relation.nodes

            // 确保源和目标节点存在
            if (sourceNode && sourceNode.properties && sourceNode.properties.name) {
              nodes.set(sourceNode.element_id, {
                id: sourceNode.element_id,
                name: sourceNode.properties.name
              })
            }

            if (targetNode && targetNode.properties && targetNode.properties.name) {
              nodes.set(targetNode.element_id, {
                id: targetNode.element_id,
                name: targetNode.properties.name
              })
            }

            // 添加边
            edges.push({
              source_id: sourceNode.element_id,
              target_id: targetNode.element_id,
              type: relation.properties.type || relation.type,
              id: `edge_${edgeId++}`
            })
          }
        })
      }
    }
  })

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
</script>

<style lang="less" scoped>
.knowledge-graph-result {
  background: var(--gray-0);
  border-radius: 8px;
  border: 1px solid var(--gray-200);

  .kg-header {
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

  .graph-visualization {
    margin: 8px;
    background: var(--gray-0);
    border-radius: 6px;
    border: 1px solid var(--gray-200);
    min-height: 350px;
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