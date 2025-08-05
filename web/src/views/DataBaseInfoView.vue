<template>
<div class="database-info-container">
  <DatabaseHeader />

  <!-- Maximize Graph Modal -->
  <a-modal
    v-model:open="isGraphMaximized"
    :footer="null"
    :closable="false"
    width="100%"
    wrap-class-name="full-modal"
    :mask-closable="false"
  >
    <template #title>
      <div class="maximized-graph-header">
        <h3>知识图谱 (最大化)</h3>
        <a-button type="text" @click="toggleGraphMaximize">
          <CompressOutlined /> 退出最大化
        </a-button>
      </div>
    </template>
    <div class="maximized-graph-content">
      <div v-if="!isGraphSupported" class="graph-disabled">
        <div class="disabled-content">
          <h4>知识图谱不可用</h4>
          <p>当前知识库类型 "{{ getKbTypeLabel(database.kb_type || 'lightrag') }}" 不支持知识图谱功能。</p>
          <p>只有 LightRAG 类型的知识库支持知识图谱。</p>
        </div>
      </div>
      <KnowledgeGraphViewer
        v-else-if="isGraphMaximized"
        :initial-database-id="databaseId"
        :hide-db-selector="true"
      />
    </div>
  </a-modal>

  <FileDetailModal />

  <FileUploadModal
    v-model:visible="addFilesModalVisible"
  />

  <div class="unified-layout">
    <div class="left-panel" :style="{ width: leftPanelWidth + '%' }">
      <FileTable
        :right-panel-visible="state.rightPanelVisible"
        @show-add-files-modal="showAddFilesModal"
        @toggle-right-panel="toggleRightPanel"
      />
    </div>

    <div class="resize-handle" ref="resizeHandle"></div>

    <div class="right-panel" :style="{ width: (100 - leftPanelWidth) + '%', display: store.state.rightPanelVisible ? 'flex' : 'none' }">
      <KnowledgeGraphSection
        :visible="panels.graph.visible"
        :style="computePanelStyles().graph"
        @toggle-visible="togglePanel('graph')"
      />

      <div class="resize-handle-horizontal" ref="resizeHandleHorizontal" v-show="panels.query.visible && panels.graph.visible"></div>

      <QuerySection
        :visible="panels.query.visible"
        :style="computePanelStyles().query"
        @toggle-visible="togglePanel('query')"
      />
    </div>
  </div>
</div>
</template>

<script setup>
import { onMounted, reactive, ref, watch, onUnmounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { useDatabaseStore } from '@/stores/database';
import { getKbTypeLabel } from '@/utils/kb_utils';
import { CompressOutlined } from '@ant-design/icons-vue';
import KnowledgeGraphViewer from '@/components/KnowledgeGraphViewer.vue';
import DatabaseHeader from '@/components/DatabaseHeader.vue';
import FileTable from '@/components/FileTable.vue';
import FileDetailModal from '@/components/FileDetailModal.vue';
import FileUploadModal from '@/components/FileUploadModal.vue';
import KnowledgeGraphSection from '@/components/KnowledgeGraphSection.vue';
import QuerySection from '@/components/QuerySection.vue';

const route = useRoute();
const store = useDatabaseStore();

const databaseId = computed(() => store.databaseId);
const database = computed(() => store.database);
const state = computed(() => store.state);
const isGraphMaximized = computed({
    get: () => store.state.isGraphMaximized,
    set: (val) => store.state.isGraphMaximized = val
});

// 计算属性：是否支持知识图谱
const isGraphSupported = computed(() => {
  const kbType = database.value.kb_type?.toLowerCase();
  return kbType === 'lightrag';
});

// 面板可见性控制
const panels = reactive({
  query: { visible: true },
  graph: { visible: true },
});

// 添加调试日志
console.log('Initial panels state:', panels);

const togglePanel = (panel) => {
  panels[panel].visible = !panels[panel].visible;
};

// 切换右侧面板显示/隐藏
const toggleRightPanel = () => {
  store.state.rightPanelVisible = !store.state.rightPanelVisible;
};

// 拖拽调整大小
const leftPanelWidth = ref(45);
const isDragging = ref(false);
const resizeHandle = ref(null);

const rightPanelHeight = reactive({ query: 50, graph: 50 });
const isDraggingVertical = ref(false);
const resizeHandleHorizontal = ref(null);

// 计算面板样式的方法
const computePanelStyles = () => {
  const queryVisible = panels.query.visible;
  const graphVisible = panels.graph.visible && isGraphSupported.value;

  if (queryVisible && graphVisible) {
    const styles = {
      query: { height: rightPanelHeight.query + '%', flex: 'none' },
      graph: { height: rightPanelHeight.graph + '%', flex: 'none' }
    };
    console.log('Computed panel styles:', styles);
    return styles;
  } else if (queryVisible && !graphVisible) {
    return {
      query: { height: '100%', flex: '1' },
      graph: { height: '36px', flex: 'none' }
    };
  } else if (!queryVisible && graphVisible) {
    return {
      query: { height: '36px', flex: 'none' },
      graph: { height: '100%', flex: '1' }
    };
  } else {
    return {
      query: { height: '36px', flex: 'none' },
      graph: { height: '36px', flex: 'none' }
    };
  }
};

// 添加调试日志
console.log('Panel styles computed:', computePanelStyles());

// 添加文件弹窗
const addFilesModalVisible = ref(false);

// 显示添加文件弹窗
const showAddFilesModal = () => {
  addFilesModalVisible.value = true;
};

// 切换图谱最大化状态
const toggleGraphMaximize = () => {
  isGraphMaximized.value = !isGraphMaximized.value;
};

watch(() => route.params.database_id, async (newId) => {
    store.databaseId = newId;
    store.stopAutoRefresh();
    await store.getDatabaseInfo(newId);
    store.startAutoRefresh();
  },
  { immediate: true }
);

// 组件挂载时启动示例轮播
onMounted(() => {
  store.databaseId = route.params.database_id;
  store.getDatabaseInfo();
  store.startAutoRefresh();

  // 添加拖拽事件监听
  if (resizeHandle.value) {
    resizeHandle.value.addEventListener('mousedown', handleMouseDown);
  }
  if (resizeHandleHorizontal.value) {
    resizeHandleHorizontal.value.addEventListener('mousedown', handleMouseDownHorizontal);
  }

  // 添加调试日志
  console.log('Resize handles initialized', resizeHandle.value, resizeHandleHorizontal.value);
});

// 组件卸载时停止示例轮播
onUnmounted(() => {
  store.stopAutoRefresh();
  if (resizeHandle.value) {
    resizeHandle.value.removeEventListener('mousedown', handleMouseDown);
  }
  if (resizeHandleHorizontal.value) {
    resizeHandleHorizontal.value.removeEventListener('mousedown', handleMouseDownHorizontal);
  }
  document.removeEventListener('mousemove', handleMouseMove);
  document.removeEventListener('mouseup', handleMouseUp);
  document.removeEventListener('mousemove', handleMouseMoveHorizontal);
  document.removeEventListener('mouseup', handleMouseUpHorizontal);
});

// 拖拽调整大小功能
const handleMouseDown = () => {
  isDragging.value = true;
  document.addEventListener('mousemove', handleMouseMove);
  document.addEventListener('mouseup', handleMouseUp);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
};

const handleMouseMove = (e) => {
  if (!isDragging.value) return;

  const container = document.querySelector('.unified-layout');
  if (!container) return;

  const containerRect = container.getBoundingClientRect();
  const newWidth = ((e.clientX - containerRect.left) / containerRect.width) * 100;
  leftPanelWidth.value = Math.max(20, Math.min(60, newWidth));
};

const handleMouseUp = () => {
  isDragging.value = false;
  document.removeEventListener('mousemove', handleMouseMove);
  document.removeEventListener('mouseup', handleMouseUp);
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
};

const handleMouseDownHorizontal = () => {
  console.log('Horizontal resize handle clicked');
  isDraggingVertical.value = true;
  document.addEventListener('mousemove', handleMouseMoveHorizontal);
  document.addEventListener('mouseup', handleMouseUpHorizontal);
  document.body.style.cursor = 'row-resize';
  document.body.style.userSelect = 'none';

  // 添加调试日志
  console.log('Current panel heights:', rightPanelHeight.graph, rightPanelHeight.query);
};

const handleMouseMoveHorizontal = (e) => {
  if (!isDraggingVertical.value) return;

  const container = document.querySelector('.right-panel');
  if (!container) return;

  const containerRect = container.getBoundingClientRect();
  const newHeight = ((e.clientY - containerRect.top) / containerRect.height) * 100;

  // 修复计算逻辑，确保两个面板的高度总和为100%
  rightPanelHeight.graph = Math.max(10, Math.min(90, newHeight));
  rightPanelHeight.query = 100 - rightPanelHeight.graph;

  // 添加调试日志
  console.log('Vertical resize:', rightPanelHeight.graph, rightPanelHeight.query);
};

const handleMouseUpHorizontal = () => {
  isDraggingVertical.value = false;
  document.removeEventListener('mousemove', handleMouseMoveHorizontal);
  document.removeEventListener('mouseup', handleMouseUpHorizontal);
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
};

</script>

<style lang="less" scoped>
.db-main-container {
  display: flex;
  width: 100%;
}

.ant-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.auto-refresh-control {
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: 6px;

  span {
    color: var(--gray-700);
    font-weight: 500;
    font-size: 14px;
  }

  .ant-switch {
    &.ant-switch-checked {
      background-color: var(--main-color);
    }
  }
}

/* Unified Layout Styles */
.unified-layout {
  display: flex;
  height: calc(100vh - 54px); /* Adjust based on actual header height */
  gap: 0;

  .left-panel,
  .right-panel {
    background-color: #fff;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .left-panel {
    flex-shrink: 0;
    flex-grow: 1;
    background-color: var(--bg-sider);
    padding: 8px;
  }

  .right-panel {
    flex-grow: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* 当两个面板都可见时，确保它们正确分配空间 */
  .right-panel > *:not(.resize-handle-horizontal) {
    flex: 1;
    min-height: 0;
  }

  .resize-handle {
    width: 2px;
    cursor: col-resize;
    background-color: var(--gray-200);
    transition: background-color 0.2s ease;
    position: relative;
    z-index: 10;
    flex-shrink: 0;

    &:hover {
      background-color: var(--main-40);
    }
  }

  .resize-handle-horizontal {
    height: 1px;
    width: 100%;
    cursor: row-resize;
    background-color: var(--gray-200);
    transition: background-color 0.2s ease;
    z-index: 10;
    flex-shrink: 0;

    &:hover {
      background-color: var(--main-40);
    }
  }
}


/* Improve the resize handle visibility */
.resize-handle,
.resize-handle-horizontal {
  transition: all 0.2s ease;
  opacity: 0.6;

  &:hover {
    opacity: 1;
    background-color: var(--main-color);
  }
}

/* Responsive design for smaller screens */
@media (max-width: 768px) {
  .unified-layout {
    flex-direction: column;
  }

  .unified-layout .left-panel {
    border-right: none;
    border-bottom: 1px solid var(--gray-200);
  }

  .unified-layout .resize-handle {
    width: 100%;
    height: 2px;
    cursor: row-resize;
  }
}

/* Table row selection styling */
:deep(.ant-table-tbody > tr.ant-table-row-selected > td) {
  background-color: var(--main-5);
}

:deep(.ant-table-tbody > tr:hover > td) {
  background-color: var(--main-5);
}
</style>

<style lang="less">
:deep(.full-modal) {
  .ant-modal {
    max-width: 100%;
    top: 0;
    padding-bottom: 0;
    margin: 0;
    padding: 0;
  }

  .ant-modal-content {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 200px);
  }

  .ant-modal-body {
    flex: 1;
  }
}



.maximized-graph-header {
  display: flex;
  justify-content: space-between;
  align-items: center;

  h3 {
    margin: 0;
    color: var(--gray-800);
  }
}


.maximized-graph-content {
  height: calc(100vh - 300px);
  border-radius: 6px;
  overflow: hidden;
}


/* 全局样式作为备用方案 */
.ant-popover .query-params-compact {
  width: 220px;
}

.ant-popover .query-params-compact .params-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 80px;
}

.ant-popover .query-params-compact .params-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
}

.ant-popover .query-params-compact .param-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
}

.ant-popover .query-params-compact .param-item label {
  font-weight: 500;
  color: var(--gray-700);
  margin-right: 8px;
}


/* Improve panel transitions */
.panel-section {
  display: flex;
  flex-direction: column;
  border-radius: 4px;
  transition: all 0.3s;
  min-height: 0;

  &.collapsed {
    height: 36px;
    flex: none;
  }

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
      gap: 12px;
    }

    .section-title {
      font-size: 14px;
      font-weight: 500;
      color: var(--gray-700);
      margin: 0;
    }

    .panel-actions {
      display: flex;
      gap: 0px;
    }
  }

  .content {
    flex: 1;
    min-height: 0;
  }
}

.query-section,
.graph-section {
  .panel-section();

  .content {
    padding: 8px;
    flex: 1;
    overflow: hidden;
  }
}
</style>