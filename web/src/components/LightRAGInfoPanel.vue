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

    
      </div>
</template>

<script setup>
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
</style>