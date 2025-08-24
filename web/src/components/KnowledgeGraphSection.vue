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
          type="primary"
          size="small"
          @click="loadGraph"
          :disabled="!isGraphSupported"
          :icon='h(ReloadOutlined)'
        >
          加载图谱
        </a-button>
        <!-- 导出功能暂禁，等待 LightRAG 库修复
        <a-button
          type="primary"
          size="small"
          @click="showExportModal = true"
          :disabled="!isGraphSupported"
        >
          导出图谱
        </a-button>
        -->
        <a-button
          type="text"
          size="small"
          @click="showSettings = true"
        >
          <SettingOutlined />
          查询参数
        </a-button>
        <!-- <a-button
          type="text"
          size="small"
          :icon="h(DeleteOutlined)"
          title="清空"
          @click="clearGraph"
          :disabled="!isGraphSupported"
        >
          清空
        </a-button> -->
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
        :hide-controls="!store.state.isGraphMaximized"
        :initial-limit="graphLimit"
        :initial-depth="graphDepth"
        @update:stats="handleStatsUpdate"
        ref="graphViewerRef"
      />
    </div>

    <!-- 设置模态框 -->
    <a-modal
      v-model:open="showSettings"
      title="图谱设置"
      :footer="null"
      width="300px"
    >
      <div class="settings-form">
        <a-form layout="vertical">
          <a-form-item label="最大节点数 (limit)">
            <a-input-number
              v-model:value="graphLimit"
              :min="10"
              :max="1000"
              :step="10"
              style="width: 100%"
            />
          </a-form-item>
          <a-form-item label="搜索深度 (depth)">
            <a-input-number
              v-model:value="graphDepth"
              :min="1"
              :max="5"
              :step="1"
              style="width: 100%"
            />
          </a-form-item>
          <a-form-item>
            <a-button type="primary" @click="applySettings" style="width: 100%">
              应用
            </a-button>
          </a-form-item>
        </a-form>
      </div>
    </a-modal>

    <!-- 导出功能暂禁，等待 LightRAG 库修复
    <a-modal
      v-model:open="showExportModal"
      title="导出图谱数据"
      @ok="handleExport"
      ok-text="导出"
      cancel-text="取消"
    >
      <a-form layout="vertical">
        <a-form-item label="导出格式">
          <a-select v-model:value="exportOptions.format">
            <a-select-option value="zip">ZIP 压缩包</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item>
          <a-checkbox v-model:checked="exportOptions.include_vectors" disabled>
            包含向量数据 (暂不支持)
          </a-checkbox>
        </a-form-item>
      </a-form>
    </a-modal>
    -->

  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import { useDatabaseStore } from '@/stores/database';
import { useUserStore } from '@/stores/user';
import { ReloadOutlined, DeleteOutlined, ExpandOutlined, UpOutlined, DownOutlined, SettingOutlined } from '@ant-design/icons-vue';
import { message } from 'ant-design-vue';
import KnowledgeGraphViewer from '@/components/KnowledgeGraphViewer.vue';
import { h } from 'vue';

const store = useDatabaseStore();
const userStore = useUserStore();

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
const showSettings = ref(false);
const graphLimit = ref(200);
const graphDepth = ref(2);

const showExportModal = ref(false);
const exportOptions = ref({
  format: 'zip',
  include_vectors: false,
});

// 计算属性：是否支持知识图谱
const isGraphSupported = computed(() => {
  const type = kbType.value?.toLowerCase();
  return type === 'lightrag';
});

const toggleVisible = () => {
  emit('toggleVisible');
};

const loadGraph = () => {
  if (!(Object.keys(store.database?.files).length > 0)) {
    return;
  }
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

const applySettings = () => {
  showSettings.value = false;
  // 设置已通过props传递给子组件，不需要额外操作
};

// const handleExport = async () => {
//   const dbId = store.databaseId;
//   if (!dbId) {
//     message.error('请先选择一个知识库');
//     return;
//   }
//   try {
//     const response = await fetch(`/api/knowledge/databases/${dbId}/export?format=${exportOptions.value.format}`, {
//       headers: {
//         ...userStore.getAuthHeaders()
//       }
//     });

//     if (!response.ok) {
//       const errorData = await response.json();
//       throw new Error(errorData.detail || `导出失败: ${response.statusText}`);
//     }

//     const blob = await response.blob();
//     const url = window.URL.createObjectURL(blob);
//     const a = document.createElement('a');
//     a.style.display = 'none';
//     a.href = url;

//     const disposition = response.headers.get('content-disposition');
//     let filename = `export_${dbId}.zip`;
//     if (disposition) {
//         const filenameMatch = disposition.match(/filename="([^"]+)"/);
//         if (filenameMatch && filenameMatch[1]) {
//             filename = filenameMatch[1];
//         }
//     }
//     a.download = filename;
//     document.body.appendChild(a);
//     a.click();
//     window.URL.revokeObjectURL(url);
//     document.body.removeChild(a);

//     message.success('导出任务已开始');
//     showExportModal.value = false;
//   } catch (error) {
//     console.error('导出图谱失败:', error);
//     message.error(error.message || '导出图谱失败');
//   }
// };

watch(isGraphSupported, (supported) => {
    if (supported) {
        setTimeout(() => {
            loadGraph();
        }, 800);
    }
});

</script>

<style scoped lang="less">
.graph-section {

  .graph-container-compact {
    flex: 1;
    min-height: 0;
    padding: 0;
    height: 100%;
    border-radius: 0;
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

<style lang="less">
.graph-section {
  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    border-bottom: 1px solid #f0f0f0;
    background-color: #fafafa;

    .header-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .section-title {
      font-size: 16px;
      font-weight: 500;
      margin: 0;
    }

    .graph-stats {
      display: flex;
      gap: 8px;
    }

    .panel-actions {
      display: flex;
      align-items: center;
      gap: 4px;
    }
  }
}
</style>
