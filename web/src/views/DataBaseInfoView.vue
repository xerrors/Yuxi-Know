<template>
<div class="database-info-container">
  <FileDetailModal />

  <FileUploadModal
    v-model:visible="addFilesModalVisible"
  />

  <div class="unified-layout">
    <div class="left-panel" :style="{ width: leftPanelWidth + '%' }">
      <KnowledgeBaseCard />
      <FileTable
        :right-panel-visible="state.rightPanelVisible"
        @show-add-files-modal="showAddFilesModal"
        @toggle-right-panel="toggleRightPanel"
      />
    </div>

    <div class="resize-handle" ref="resizeHandle"></div>

    <div class="right-panel" :style="{ width: (100 - leftPanelWidth) + '%', display: store.state.rightPanelVisible ? 'flex' : 'none' }">
      <a-tabs v-model:activeKey="activeTab" class="knowledge-tabs" :tabBarStyle="{ margin: 0, padding: '0 16px' }">
        <a-tab-pane key="graph" tab="知识图谱" v-if="isGraphSupported">
          <KnowledgeGraphSection
            :visible="true"
            :active="activeTab === 'graph'"
            @toggle-visible="() => {}"
          />
        </a-tab-pane>
        <a-tab-pane key="query" tab="检索测试">
          <QuerySection
            ref="querySectionRef"
            :visible="true"
            @toggle-visible="() => {}"
          />
        </a-tab-pane>
        <a-tab-pane key="mindmap" tab="知识导图">
          <MindMapSection
            v-if="databaseId"
            :database-id="databaseId"
            ref="mindmapSectionRef"
          />
        </a-tab-pane>
        <a-tab-pane key="config" tab="检索配置">
          <SearchConfigTab :database-id="databaseId" />
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</div>
</template>

<script setup>
import { onMounted, reactive, ref, watch, onUnmounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { useDatabaseStore } from '@/stores/database';
import KnowledgeBaseCard from '@/components/KnowledgeBaseCard.vue';
import FileTable from '@/components/FileTable.vue';
import FileDetailModal from '@/components/FileDetailModal.vue';
import FileUploadModal from '@/components/FileUploadModal.vue';
import KnowledgeGraphSection from '@/components/KnowledgeGraphSection.vue';
import QuerySection from '@/components/QuerySection.vue';
import SearchConfigTab from '@/components/SearchConfigTab.vue';
import MindMapSection from '@/components/MindMapSection.vue';

const route = useRoute();
const store = useDatabaseStore();

const databaseId = computed(() => store.databaseId);
const database = computed(() => store.database);
const state = computed(() => store.state);
// 计算属性：是否支持知识图谱
const isGraphSupported = computed(() => {
  const kbType = database.value.kb_type?.toLowerCase();
  return kbType === 'lightrag';
});

// Tab 切换逻辑 - 智能默认
const activeTab = ref('query');

// 思维导图引用
const mindmapSectionRef = ref(null);

// 查询区域引用
const querySectionRef = ref(null);


const resetGraphStats = () => {
  store.graphStats = {
    total_nodes: 0,
    total_edges: 0,
    displayed_nodes: 0,
    displayed_edges: 0,
    is_truncated: false
  };
};


// LightRAG 默认展示知识图谱
watch(
  () => [databaseId.value, isGraphSupported.value],
  ([newDbId, supported], oldValue = []) => {
    const [oldDbId, previouslySupported] = oldValue;

    if (!newDbId) {
      return;
    }

    if (newDbId && newDbId !== oldDbId) {
      resetGraphStats();
    } else if (!supported && previouslySupported) {
      resetGraphStats();
    }

    if (supported && (newDbId !== oldDbId || previouslySupported === false || previouslySupported === undefined)) {
      activeTab.value = 'graph';
      return;
    }

    if (!supported && activeTab.value === 'graph') {
      activeTab.value = 'query';
    }
  },
  { immediate: true }
);

// 切换右侧面板显示/隐藏
const toggleRightPanel = () => {
  store.state.rightPanelVisible = !store.state.rightPanelVisible;
};

// 拖拽调整大小（仅水平方向）
const leftPanelWidth = ref(50);
const isDragging = ref(false);
const resizeHandle = ref(null);

// 添加文件弹窗
const addFilesModalVisible = ref(false);

// 标记是否是初次加载
const isInitialLoad = ref(true);

// 显示添加文件弹窗
const showAddFilesModal = () => {
  addFilesModalVisible.value = true;
};

// 重置文件选中状态
const resetFileSelectionState = () => {
  store.selectedRowKeys = [];
  store.selectedFile = null;
  store.state.fileDetailModalVisible = false;
};

watch(() => route.params.database_id, async (newId, oldId) => {
    // 切换知识库时，标记为初次加载
    isInitialLoad.value = true;
    
    store.databaseId = newId;
    resetFileSelectionState();
    resetGraphStats();
    store.stopAutoRefresh();
    await store.getDatabaseInfo(newId, false); // Explicitly load query params on initial load
    store.startAutoRefresh();
  },
  { immediate: true }
);

// 监听文件列表变化，自动更新思维导图和生成示例问题
const previousFileCount = ref(0);

watch(
  () => database.value?.files,
  (newFiles, oldFiles) => {
    if (!newFiles) return;
    
    const newFileCount = Object.keys(newFiles).length;
    const oldFileCount = previousFileCount.value;
    
    // 首次加载时，只更新计数，不触发任何操作
    if (isInitialLoad.value) {
      previousFileCount.value = newFileCount;
      isInitialLoad.value = false;
      return;
    }
    
    // 如果文件数量发生变化（增加或减少），都重新生成问题和思维导图
    if (newFileCount !== oldFileCount) {
      const changeType = newFileCount > oldFileCount ? '增加' : '减少';
      console.log(`文件数量从 ${oldFileCount} ${changeType}到 ${newFileCount}，准备重新生成问题和思维导图`);
      
      // 只要有文件，就重新生成思维导图（无论增加还是减少）
      if (newFileCount > 0) {
        setTimeout(() => {
          if (mindmapSectionRef.value) {
            if (oldFileCount === 0) {
              // 首次添加文件，生成思维导图
              console.log('首次添加文件，生成思维导图');
              mindmapSectionRef.value.generateMindmap();
            } else {
              // 文件数量变化（增加或减少），重新生成思维导图
              console.log(`文件数量变化，重新生成思维导图`);
              mindmapSectionRef.value.refreshMindmap();
            }
          }
        }, 2000); // 等待2秒让后端处理完成
      } else {
        // 如果文件数量变为0，清空思维导图（如果需要的话）
        console.log('文件数量为0，思维导图将自动清空');
      }
      
      // 只要有文件，就重新生成问题（无论之前是否有问题）
      if (newFileCount > 0) {
        setTimeout(async () => {
          console.log('文件数量变化，检查是否需要生成问题，querySectionRef:', querySectionRef.value);
          if (querySectionRef.value) {
            console.log('开始重新生成问题...');
            await querySectionRef.value.generateSampleQuestions(true);
          } else {
            console.warn('querySectionRef 未准备好，稍后重试');
            // 如果组件还没准备好，再等一会儿
            setTimeout(async () => {
              if (querySectionRef.value) {
                console.log('延迟后开始生成问题...');
                await querySectionRef.value.generateSampleQuestions(true);
              }
            }, 2000);
          }
        }, 3000); // 等待3秒让后端处理完成
      } else {
        // 如果文件数量变为0，清空问题列表
        console.log('文件数量为0，清空问题列表');
        setTimeout(() => {
          if (querySectionRef.value) {
            // 清空问题列表
            querySectionRef.value.clearQuestions();
          }
        }, 1000);
      }
    }
    
    previousFileCount.value = newFileCount;
  },
  { deep: true }
);

// 组件挂载时启动示例轮播
onMounted(() => {
  store.databaseId = route.params.database_id;
  resetFileSelectionState();
  store.getDatabaseInfo();
  store.startAutoRefresh();

  // 添加拖拽事件监听（仅水平方向）
  if (resizeHandle.value) {
    resizeHandle.value.addEventListener('mousedown', handleMouseDown);
  }
});

// 组件卸载时停止示例轮播
onUnmounted(() => {
  store.stopAutoRefresh();
  if (resizeHandle.value) {
    resizeHandle.value.removeEventListener('mousedown', handleMouseDown);
  }
  document.removeEventListener('mousemove', handleMouseMove);
  document.removeEventListener('mouseup', handleMouseUp);
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
  leftPanelWidth.value = Math.max(20, Math.min(80, newWidth));
};

const handleMouseUp = () => {
  isDragging.value = false;
  document.removeEventListener('mousemove', handleMouseMove);
  document.removeEventListener('mouseup', handleMouseUp);
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
  height: 100vh;
  gap: 0;

  .left-panel,
  .right-panel {
    background-color: var(--bg-primary);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 8px;
  }

  .left-panel {
    display: flex;
    flex-shrink: 0;
    flex-grow: 1;
    background-color: var(--gray-0);
    padding-right: 0;
    // max-height: calc(100% - 16px);
  }

  .right-panel {
    flex-grow: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    padding-left: 0;
  }

  .resize-handle {
    width: 4px;
    cursor: col-resize;
    background-color: var(--gray-200);
    position: relative;
    z-index: 10;
    flex-shrink: 0;
    height: 30px;
    top: 40%;
    margin: 0 2px;
    border-radius: 4px;
  }
}

/* Tab 样式 */
.knowledge-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--gray-200);
  border-radius: 12px;

  :deep(.ant-tabs-content) {
    flex: 1;
    height: 100%;
    overflow: hidden;
  }

  :deep(.ant-tabs-tabpane) {
    height: 100%;
    overflow: hidden;
  }

  :deep(.ant-tabs-nav) {
    margin-bottom: 0;
    // background-color: #fff;
    border-bottom: 1px solid var(--gray-200);
  }
}

/* Simplify resize handle */
.resize-handle {
  opacity: 0.8;
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
    border-bottom: 1px solid var(--border-light);
    background-color: var(--bg-secondary);

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
