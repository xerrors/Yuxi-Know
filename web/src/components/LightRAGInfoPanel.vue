<template>
  <div class="lightrag-info-panel">
    <div class="info-item">
      <span class="info-label">节点</span>
      <span class="info-value">{{ stats?.total_nodes || 0 }}</span>
    </div>

    <div class="info-item">
      <span class="info-label">边</span>
      <span class="info-value">{{ stats?.total_edges || 0 }}</span>
    </div>

    <div class="info-item">
      <span class="info-label">知识库</span>
      <span class="info-value">{{ databaseName }}</span>
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
import { computed } from 'vue'

const props = defineProps({
  stats: {
    type: Object,
    default: () => ({})
  },
  graphData: {
    type: Object,
    default: () => ({ nodes: [], edges: [] })
  },
  databaseName: {
    type: String,
    default: ''
  }
})

defineEmits(['export-data'])
</script>

<style lang="less" scoped>
.lightrag-info-panel {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 8px 16px;
  background: var(--gray-50);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-radius: 8px;
  margin: 0;
  border: 1px solid var(--gray-0);
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
}

.info-label {
  color: var(--gray-700);
  font-weight: 500;
}

.info-value {
  color: var(--gray-1000);
  font-weight: 600;
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
</style>