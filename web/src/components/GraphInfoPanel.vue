<template>
  <div class="graph-info-panel">
    <div class="info-item">
      <span class="info-label">实体</span>
      <span class="info-value">{{ graphData.nodes.length }}</span>
      <span v-if="graphInfo?.entity_count" class="info-total">/ {{ graphInfo.entity_count }}</span>
    </div>

    <div class="info-item">
      <span class="info-label">关系</span>
      <span class="info-value">{{ graphData.edges.length }}</span>
      <span v-if="graphInfo?.relationship_count" class="info-total">/ {{ graphInfo.relationship_count }}</span>
    </div>

    <div v-if="graphInfo?.graph_name" class="info-item">
      <span class="info-label">图谱</span>
      <span class="info-value">{{ graphInfo.graph_name }}</span>
    </div>

    <div v-if="unindexedCount > 0" class="info-item warning">
      <span class="info-label">未索引</span>
      <span class="info-value warning">{{ unindexedCount }}</span>
      <a-button
        v-if="modelMatched"
        type="primary"
        size="small"
        @click="$emit('index-nodes')"
      >
        添加索引
      </a-button>
      <a-tooltip v-else title="向量模型不匹配，无法添加索引">
        <a-button type="default" size="small" disabled>
          模型不匹配
        </a-button>
      </a-tooltip>
    </div>

    <div class="actions">
      <a-button type="default" size="small" @click="$emit('export-data')">
        <ExportOutlined />
        导出数据
      </a-button>
    </div>
  </div>
</template>

<script setup>
import { ExportOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  graphInfo: {
    type: Object,
    default: () => ({})
  },
  graphData: {
    type: Object,
    default: () => ({ nodes: [], edges: [] })
  },
  unindexedCount: {
    type: Number,
    default: 0
  },
  modelMatched: {
    type: Boolean,
    default: true
  }
})

defineEmits(['index-nodes', 'export-data'])
</script>

<style lang="less" scoped>
.graph-info-panel {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 24px;
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-radius: 8px;
  margin: 0;
  border: 1px solid white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  flex-wrap: wrap;
  align-self: flex-start;

  @media (max-width: 768px) {
    gap: 16px;
    padding: 12px 16px;
  }
}

.info-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;

  &.warning {
    color: #fa8c16;
  }
}

.info-label {
  color: var(--gray-700);
  font-weight: 500;
}

.info-value {
  color: var(--gray-1000);
  font-weight: 600;

  &.warning {
    color: #fa8c16;
  }
}

.info-total {
  color: var(--gray-600);
  font-size: 12px;
}

.actions {
  margin-left: auto;
  display: flex;
  gap: 8px;

  @media (max-width: 768px) {
    margin-left: 0;
    width: 100%;
    justify-content: flex-end;
  }
}

:deep(.ant-btn-default) {
  font-size: 12px;
  height: 28px;
  padding: 0 12px;
  border-radius: 6px;
  border-color: var(--main-300);
  color: var(--main-600);
  background: var(--main-20);
  transition: all 0.2s ease;

  &:hover {
    border-color: var(--main-500);
    color: var(--main-700);
    background: var(--main-40);
    box-shadow: 0 2px 4px rgba(1, 97, 121, 0.1);
  }

  &:active {
    transform: translateY(1px);
  }
}

:deep(.ant-btn-primary) {
  font-size: 12px;
  height: 28px;
  padding: 0 12px;
  border-radius: 6px;
  background: var(--main-500);
  border-color: var(--main-500);
  transition: all 0.2s ease;

  &:hover {
    background: var(--main-600);
    border-color: var(--main-600);
    box-shadow: 0 2px 4px rgba(1, 97, 121, 0.2);
  }

  &:active {
    transform: translateY(1px);
  }
}
</style>