<template>
  <div class="graph-section" v-if="isGraphSupported">
    <div class="graph-toolbar">
      <div class="toolbar-left">
        <!-- 移除了不准确的总节点数和总边数显示 -->
      </div>
    </div>
    <div class="graph-container-compact">
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
        :initial-limit="graphLimit"
        :initial-depth="graphDepth"
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
import { ref, computed, watch, nextTick, onUnmounted } from 'vue';
import { useDatabaseStore } from '@/stores/database';
import { ReloadOutlined } from '@ant-design/icons-vue';
import KnowledgeGraphViewer from '@/components/KnowledgeGraphViewer.vue';
import { h } from 'vue';
import { getKbTypeLabel } from '@/utils/kb_utils';

const props = defineProps({
  active: {
    type: Boolean,
    default: false,
  },
});

const store = useDatabaseStore();

const databaseId = computed(() => store.databaseId);
const kbType = computed(() => store.database.kb_type);
const kbTypeLabel = computed(() => getKbTypeLabel(kbType.value || 'lightrag'));

const graphViewerRef = ref(null);
const showSettings = ref(false);
const graphLimit = ref(50);
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

let pendingLoadTimer = null;

const loadGraph = async () => {
  console.log('loadGraph 调用:', {
    hasRef: !!graphViewerRef.value,
    hasLoadFullGraph: graphViewerRef.value && typeof graphViewerRef.value.loadFullGraph === 'function'
  });

  // 等待一小段时间确保子组件已经完全初始化
  await nextTick();

  if (graphViewerRef.value && typeof graphViewerRef.value.loadFullGraph === 'function') {
    console.log('调用 loadFullGraph');
    graphViewerRef.value.loadFullGraph();
  } else {
    console.warn('无法调用 loadFullGraph:', {
      hasRef: !!graphViewerRef.value,
      refValue: graphViewerRef.value,
      hasMethod: graphViewerRef.value && typeof graphViewerRef.value.loadFullGraph
    });
  }
};

const clearGraph = () => {
  if (graphViewerRef.value && typeof graphViewerRef.value.clearGraph === 'function') {
    graphViewerRef.value.clearGraph();
  }
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

const scheduleGraphLoad = (delay = 200) => {
  console.log('scheduleGraphLoad 调用:', {
    active: props.active,
    supported: isGraphSupported.value,
    databaseId: databaseId.value,
    hasGraphViewer: !!graphViewerRef.value
  });

  // 确保组件激活且数据库支持图谱功能
  if (!props.active) {
    console.log('组件未激活，跳过图谱加载');
    return;
  }

  if (!isGraphSupported.value) {
    console.log('数据库不支持图谱功能，跳过加载');
    return;
  }

  if (!databaseId.value) {
    console.log('没有选中数据库，跳过图谱加载');
    return;
  }

  if (pendingLoadTimer) {
    clearTimeout(pendingLoadTimer);
  }
  pendingLoadTimer = setTimeout(async () => {
    await nextTick();
    // 再次检查条件，防止在延迟期间状态发生变化
    if (props.active && isGraphSupported.value && databaseId.value) {
      console.log('执行图谱加载');
      await loadGraph();
    } else {
      console.log('延迟检查时条件不满足:', {
        active: props.active,
        supported: isGraphSupported.value,
        databaseId: databaseId.value
      });
    }
  }, delay);
};


watch(
  () => props.active,
  (active) => {
    if (active) {
      scheduleGraphLoad();
    }
  },
  { immediate: true }
);

watch(databaseId, () => {
  clearGraph();

  // 只有在新数据库支持图谱时才加载
  if (isGraphSupported.value) {
    scheduleGraphLoad(300);
  }
});

watch(isGraphSupported, (supported) => {
  if (!supported) {
    clearGraph();
    return;
  }
  scheduleGraphLoad(200);
});

onUnmounted(() => {
  if (pendingLoadTimer) {
    clearTimeout(pendingLoadTimer);
    pendingLoadTimer = null;
  }
});

</script>

<style scoped lang="less">
.graph-section {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.graph-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background-color: #fff;
  border-bottom: 1px solid var(--gray-200);

  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.graph-container-compact {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.graph-disabled {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
}

.disabled-content {
  text-align: center;
  color: #8c8c8c;

  h4 {
    margin-bottom: 8px;
  }
}
</style>
