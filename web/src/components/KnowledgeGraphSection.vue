<template>
  <div class="graph-section" :class="{ collapsed: !visible }" :style="style" v-if="isGraphSupported">
    <div class="section-header">
      <div class="header-left">
        <h3 class="section-title">知识图谱</h3>
        <div v-if="graphStats.displayed_nodes > 0 || graphStats.displayed_edges > 0" class="graph-stats">
          <a-tag color="blue" size="small">节点: {{ graphStats.displayed_nodes }}</a-tag>
          <a-tag color="green" size="small">边: {{ graphStats.displayed_edges }}</a-tag>
          <!-- <a-tag v-if="graphStats.is_truncated" color="red" size="small">已截断</a-tag> -->
        </div>
      </div>
      <div class="panel-actions">
        <a-button
          type="text"
          size="small"
          :icon="h(ReloadOutlined)"
          title="刷新"
          @click="refreshGraph"
          :disabled="!isGraphSupported"
        >
          刷新
        </a-button>
        <a-button
          type="text"
          size="small"
          :icon="h(DeleteOutlined)"
          title="清空"
          @click="clearGraph"
          :disabled="!isGraphSupported"
        >
          清空
        </a-button>
        <a-button
          type="text"
          size="small"
          :icon="h(ExpandOutlined)"
          title="最大化"
          @click="toggleGraphMaximize"
          :disabled="!isGraphSupported"
        >
          最大化
        </a-button>
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
    <div class="graph-container-compact content" v-show="visible">
      <div v-if="!isGraphSupported" class="graph-disabled">
        <div class="disabled-content">
          <h4>知识图谱不可用</h4>
          <p>当前知识库类型 "{{ kbTypeLabel }}" 不支持知识图谱功能。</p>
          <p>只有 LightRAG 类型的知识库支持知识图谱。</p>
        </div>
      </div>
      <KnowledgeGraphViewer
        v-else
        :initial-database-id="databaseId"
        :hide-db-selector="true"
        :hide-stats="true"
        @update:stats="handleStatsUpdate"
        ref="graphViewerRef"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import { useDatabaseStore } from '@/stores/database';
import { getKbTypeLabel } from '@/utils/kb_utils';
import { ReloadOutlined, DeleteOutlined, ExpandOutlined, UpOutlined, DownOutlined } from '@ant-design/icons-vue';
import KnowledgeGraphViewer from '@/components/KnowledgeGraphViewer.vue';
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
console.log('KnowledgeGraphSection props:', props);
console.log('KnowledgeGraphSection style prop:', props.style);

const emit = defineEmits(['toggleVisible']);

const databaseId = computed(() => store.databaseId);
const kbType = computed(() => store.database.kb_type);
const graphStats = computed({
    get: () => store.graphStats,
    set: (stats) => store.graphStats = stats
});

const graphViewerRef = ref(null);

// 计算属性：是否支持知识图谱
const isGraphSupported = computed(() => {
  const type = kbType.value?.toLowerCase();
  return type === 'lightrag';
});

const toggleVisible = () => {
  emit('toggleVisible');
};

const refreshGraph = () => {
  if (graphViewerRef.value && typeof graphViewerRef.value.loadFullGraph === 'function') {
    graphViewerRef.value.loadFullGraph();
  }
};

const clearGraph = () => {
  if (graphViewerRef.value && typeof graphViewerRef.value.clearGraph === 'function') {
    graphViewerRef.value.clearGraph();
  }
};

const toggleGraphMaximize = () => {
  store.state.isGraphMaximized = !store.state.isGraphMaximized;
};

const handleStatsUpdate = (stats) => {
  graphStats.value = stats;
};

watch(isGraphSupported, (supported) => {
    if (supported) {
        setTimeout(() => {
            refreshGraph();
        }, 800);
    }
});

</script>

<style scoped lang="less">
.graph-section {

  .graph-container-compact {
    flex: 1;
    min-height: 0;
    padding-top: 0;
    height: 100%;
  }

  .graph-disabled {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 200px;
  }

  .disabled-content {
    text-align: center;
    color: #8c8c8c;

    h4 {
      margin-bottom: 8px;
    }
  }
  
  .content {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    height: 100%;
  }
}
</style>