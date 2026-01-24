<template>
  <div class="database-info-container">
    <FileDetailModal />

    <!-- 检索配置弹窗 -->
    <SearchConfigModal
      v-model="searchConfigModalVisible"
      :database-id="databaseId"
      @save="handleSearchConfigSave"
    />

    <FileUploadModal
      v-model:visible="addFilesModalVisible"
      :folder-tree="folderTree"
      :current-folder-id="currentFolderId"
      :is-folder-mode="isFolderUploadMode"
      @success="onFileUploadSuccess"
    />

    <div class="unified-layout">
      <div class="left-panel" :style="{ width: leftPanelWidth + '%' }">
        <KnowledgeBaseCard />
        <!-- 待处理文件提示条 -->
        <div class="info-panel" v-if="pendingParseCount > 0 || pendingIndexCount > 0">
          <div class="banner-item" v-if="pendingParseCount > 0" @click="confirmBatchParse">
            <FileText :size="14" />
            <span>{{ pendingParseCount }} 个文件待解析，点击解析</span>
          </div>
          <div class="banner-item" v-if="pendingIndexCount > 0" @click="confirmBatchIndex">
            <Database :size="14" />
            <span>{{ pendingIndexCount }} 个文件待入库，点击入库</span>
          </div>
        </div>
        <FileTable
          :right-panel-visible="state.rightPanelVisible"
          @show-add-files-modal="showAddFilesModal"
          @toggle-right-panel="toggleRightPanel"
        />
      </div>

      <div class="resize-handle" ref="resizeHandle"></div>

      <div
        class="right-panel"
        :style="{
          width: 100 - leftPanelWidth + '%',
          display: store.state.rightPanelVisible ? 'flex' : 'none'
        }"
      >
        <a-tabs
          v-model:activeKey="activeTab"
          class="knowledge-tabs"
          :tabBarStyle="{ margin: 0, padding: '0 16px' }"
        >
          <template #rightExtra>
            <a-tooltip title="检索配置" placement="bottom">
              <a-button type="text" class="config-btn" @click="openSearchConfigModal">
                <SettingOutlined />
                <span class="config-text">检索配置</span>
              </a-button>
            </a-tooltip>
          </template>
          <a-tab-pane key="graph" tab="知识图谱" v-if="isGraphSupported">
            <KnowledgeGraphSection
              :visible="true"
              :active="activeTab === 'graph'"
              @toggle-visible="() => {}"
            />
          </a-tab-pane>
          <a-tab-pane key="query" tab="检索测试">
            <QuerySection ref="querySectionRef" :visible="true" @toggle-visible="() => {}" />
          </a-tab-pane>
          <a-tab-pane key="mindmap" tab="知识导图">
            <MindMapSection v-if="databaseId" :database-id="databaseId" ref="mindmapSectionRef" />
          </a-tab-pane>
          <a-tab-pane key="evaluation" tab="RAG评估" :disabled="!isEvaluationSupported">
            <template #tab>
              <span :style="{ color: !isEvaluationSupported ? 'var(--gray-400)' : '' }">
                RAG评估
                <a-tooltip v-if="!isEvaluationSupported" title="仅支持 Milvus 类型的知识库">
                  <Info :size="14" style="margin-left: 4px; vertical-align: middle" />
                </a-tooltip>
              </span>
            </template>
            <RAGEvaluationTab
              v-if="databaseId && isEvaluationSupported"
              :database-id="databaseId"
              @switch-to-benchmarks="activeTab = 'benchmarks'"
            />
          </a-tab-pane>
          <a-tab-pane key="benchmarks" tab="评估基准" :disabled="!isEvaluationSupported">
            <template #tab>
              <span :style="{ color: !isEvaluationSupported ? 'var(--gray-400)' : '' }">
                评估基准
                <a-tooltip v-if="!isEvaluationSupported" title="仅支持 Milvus 类型的知识库">
                  <Info :size="14" style="margin-left: 4px; vertical-align: middle" />
                </a-tooltip>
              </span>
            </template>
            <div class="benchmark-management-container">
              <div class="benchmark-content">
                <EvaluationBenchmarks
                  v-if="databaseId && isEvaluationSupported"
                  :database-id="databaseId"
                  @benchmark-selected="
                    (benchmark) => {
                      // 处理基准选择逻辑
                      activeTab = 'evaluation'
                    }
                  "
                  @refresh="
                    () => {
                      // 刷新逻辑
                    }
                  "
                />
              </div>
            </div>
          </a-tab-pane>
        </a-tabs>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch, onUnmounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useDatabaseStore } from '@/stores/database'
import { useTaskerStore } from '@/stores/tasker'
import { Info, FileText, Database } from 'lucide-vue-next'
import { SettingOutlined } from '@ant-design/icons-vue'
import { Modal } from 'ant-design-vue'
import KnowledgeBaseCard from '@/components/KnowledgeBaseCard.vue'
import FileTable from '@/components/FileTable.vue'
import FileDetailModal from '@/components/FileDetailModal.vue'
import FileUploadModal from '@/components/FileUploadModal.vue'
import KnowledgeGraphSection from '@/components/KnowledgeGraphSection.vue'
import QuerySection from '@/components/QuerySection.vue'
import MindMapSection from '@/components/MindMapSection.vue'
import RAGEvaluationTab from '@/components/RAGEvaluationTab.vue'
import EvaluationBenchmarks from '@/components/EvaluationBenchmarks.vue'
import SearchConfigModal from '@/components/SearchConfigModal.vue'

const route = useRoute()
const store = useDatabaseStore()
const taskerStore = useTaskerStore()

const databaseId = computed(() => store.databaseId)
const database = computed(() => store.database)
const state = computed(() => store.state)
// 计算属性：是否支持知识图谱
const isGraphSupported = computed(() => {
  const kbType = database.value.kb_type?.toLowerCase()
  return kbType === 'lightrag'
})

// 计算属性：是否支持评估功能
const isEvaluationSupported = computed(() => {
  const kbType = database.value.kb_type?.toLowerCase()
  return kbType === 'milvus'
})

// 计算待解析文件数量（status: 'uploaded'）
const pendingParseCount = computed(() => {
  const files = store.database.files || {}
  return Object.values(files).filter((f) => !f.is_folder && f.status === 'uploaded').length
})

// 计算待入库文件数量（status: 'parsed' 或 'error_indexing'）
const pendingIndexCount = computed(() => {
  const files = store.database.files || {}
  const isLightRAG = database.value?.kb_type?.toLowerCase() === 'lightrag'
  return Object.values(files).filter((f) => {
    if (f.is_folder) return false
    if (isLightRAG) {
      return f.status === 'parsed'
    }
    return f.status === 'parsed' || f.status === 'error_indexing'
  }).length
})

// 确认批量解析
const confirmBatchParse = () => {
  const fileIds = Object.values(store.database.files || {})
    .filter((f) => f.status === 'uploaded')
    .map((f) => f.file_id)

  if (fileIds.length === 0) {
    return
  }

  Modal.confirm({
    title: '批量解析',
    content: `确定要解析 ${fileIds.length} 个文件吗？`,
    onOk: () => store.parseFiles(fileIds)
  })
}

// 确认批量入库
const confirmBatchIndex = () => {
  const isLightRAG = database.value?.kb_type?.toLowerCase() === 'lightrag'
  const fileIds = Object.values(store.database.files || {})
    .filter((f) => {
      if (f.is_folder) return false
      if (isLightRAG) return f.status === 'parsed'
      return f.status === 'parsed' || f.status === 'error_indexing'
    })
    .map((f) => f.file_id)

  if (fileIds.length === 0) {
    return
  }

  if (isLightRAG) {
    Modal.confirm({
      title: '批量入库',
      content: `确定要入库 ${fileIds.length} 个文件吗？`,
      onOk: () => store.indexFiles(fileIds)
    })
    return
  }

  // 非 LightRAG：触发 FileTable 的入库流程
  // 暂时简单处理，直接调用 store.indexFiles
  Modal.confirm({
    title: '批量入库',
    content: `确定要入库 ${fileIds.length} 个文件吗？`,
    onOk: () => store.indexFiles(fileIds)
  })
}

// Tab 切换逻辑 - 智能默认
const activeTab = ref('query')

// 思维导图引用
const mindmapSectionRef = ref(null)

// 查询区域引用
const querySectionRef = ref(null)

const resetGraphStats = () => {
  store.graphStats = {
    total_nodes: 0,
    total_edges: 0,
    displayed_nodes: 0,
    displayed_edges: 0,
    is_truncated: false
  }
}

// LightRAG 默认展示知识图谱
watch(
  () => [databaseId.value, isGraphSupported.value, isEvaluationSupported.value],
  ([newDbId, supported, evaluationSupported], oldValue = []) => {
    const [oldDbId, previouslySupported, previouslyEvaluationSupported] = oldValue

    if (!newDbId) {
      return
    }

    if (newDbId && newDbId !== oldDbId) {
      resetGraphStats()
    } else if (!supported && previouslySupported) {
      resetGraphStats()
    }

    if (
      supported &&
      (newDbId !== oldDbId || previouslySupported === false || previouslySupported === undefined)
    ) {
      activeTab.value = 'graph'
      return
    }

    if (!supported && activeTab.value === 'graph') {
      activeTab.value = 'query'
    }

    // 如果知识库类型不支持评估功能且当前在评估相关 tab，切换到查询 tab
    if (
      !isEvaluationSupported.value &&
      (activeTab.value === 'evaluation' || activeTab.value === 'benchmarks')
    ) {
      activeTab.value = 'query'
    }
  },
  { immediate: true }
)

// 切换右侧面板显示/隐藏
const toggleRightPanel = () => {
  store.state.rightPanelVisible = !store.state.rightPanelVisible
}

// 拖拽调整大小（仅水平方向）
const leftPanelWidth = ref(50)
const isDragging = ref(false)
const resizeHandle = ref(null)

// 检索配置弹窗
const searchConfigModalVisible = ref(false)

const handleSearchConfigSave = () => {
  store.getDatabaseInfo()
}

// 打开检索配置弹窗
const openSearchConfigModal = () => {
  searchConfigModalVisible.value = true
}

// 添加文件弹窗
const addFilesModalVisible = ref(false)
const currentFolderId = ref(null)
const isFolderUploadMode = ref(false)

// 标记是否是初次加载
const isInitialLoad = ref(true)

// 显示添加文件弹窗
const showAddFilesModal = (options = {}) => {
  const { isFolder = false } = options
  isFolderUploadMode.value = isFolder
  addFilesModalVisible.value = true
  currentFolderId.value = null // 重置
}

// 传递给 FileUploadModal 的文件夹树
const folderTree = computed(() => {
  // 复用 FileTable 中构建文件树的逻辑，或者从 store 中获取
  // 简单起见，这里假设 store.database.files 是扁平列表，我们在 FileTable 中已经有了构建好的树
  // 但 FileTable 是子组件，最好将树的构建逻辑放到 store 或 composable 中，或者在这里重新构建
  // 既然 FileTable 中已经实现了 buildFileTree，我们可以考虑将其提取出来
  // 为了快速实现，我们这里简单实现一个仅用于选择的树构建
  const files = store.database.files || {}
  const fileList = Object.values(files)

  // 构建树的简化版逻辑 (只关心文件夹)
  const nodeMap = new Map()
  const roots = []

  // 1. 初始化节点
  fileList.forEach((file) => {
    if (file.is_folder) {
      const item = { ...file, title: file.filename, value: file.file_id, children: [] }
      nodeMap.set(file.file_id, item)
    }
  })

  // 2. 构建层级
  fileList.forEach((file) => {
    if (file.is_folder && file.parent_id && nodeMap.has(file.parent_id)) {
      const parent = nodeMap.get(file.parent_id)
      const child = nodeMap.get(file.file_id)
      if (parent && child) {
        parent.children.push(child)
      }
    } else if (file.is_folder && !file.parent_id) {
      // 只有显式根文件夹才放入 roots
      // 对于隐式路径生成的文件夹，目前简化处理暂不支持在上传时选择（因为它们没有物理ID）
      // 除非我们复用 FileTable 的复杂逻辑。
      // 如果用户只用新建文件夹功能创建文件夹，那么逻辑是够用的。
      if (nodeMap.has(file.file_id)) {
        roots.push(nodeMap.get(file.file_id))
      }
    }
  })

  return roots
})

// 文件上传成功回调
const onFileUploadSuccess = () => {
  taskerStore.loadTasks()
}

// 重置文件选中状态
const resetFileSelectionState = () => {
  store.selectedRowKeys = []
  store.selectedFile = null
  store.state.fileDetailModalVisible = false
}

watch(
  () => route.params.database_id,
  async (newId, oldId) => {
    // 切换知识库时，标记为初次加载
    isInitialLoad.value = true

    store.databaseId = newId
    resetFileSelectionState()
    resetGraphStats()
    store.stopAutoRefresh()
    await store.getDatabaseInfo(newId, false) // Explicitly load query params on initial load
    store.startAutoRefresh()
  },
  { immediate: true }
)

// 监听文件列表变化，自动更新思维导图和生成示例问题
const previousFileCount = ref(0)

watch(
  () => database.value?.files,
  (newFiles, oldFiles) => {
    if (!newFiles) return

    const newFileCount = Object.keys(newFiles).length
    const oldFileCount = previousFileCount.value

    // 首次加载时，只更新计数，不触发任何操作
    if (isInitialLoad.value) {
      previousFileCount.value = newFileCount
      isInitialLoad.value = false
      return
    }

    // 如果文件数量发生变化（增加或减少），只重新生成问题，不自动生成思维导图
    if (newFileCount !== oldFileCount) {
      const changeType = newFileCount > oldFileCount ? '增加' : '减少'
      console.log(`文件数量从 ${oldFileCount} ${changeType}到 ${newFileCount}，准备重新生成问题`)

      // 只要有文件，就重新生成问题（无论之前是否有问题）
      if (newFileCount > 0) {
        setTimeout(async () => {
          console.log('文件数量变化，检查是否需要生成问题，querySectionRef:', querySectionRef.value)
          if (querySectionRef.value) {
            // 检查是否开启了自动生成问题
            if (database.value.additional_params?.auto_generate_questions) {
              console.log('开始重新生成问题...')
              await querySectionRef.value.generateSampleQuestions(true)
            } else {
              console.log('自动生成问题已关闭，跳过生成')
            }
          } else {
            console.warn('querySectionRef 未准备好，稍后重试')
            // 如果组件还没准备好，再等一会儿
            setTimeout(async () => {
              if (querySectionRef.value) {
                if (database.value.additional_params?.auto_generate_questions) {
                  console.log('延迟后开始生成问题...')
                  await querySectionRef.value.generateSampleQuestions(true)
                } else {
                  console.log('自动生成问题已关闭，跳过生成')
                }
              }
            }, 2000)
          }
        }, 3000) // 等待3秒让后端处理完成
      } else {
        // 如果文件数量变为0，清空问题列表
        console.log('文件数量为0，清空问题列表')
        setTimeout(() => {
          if (querySectionRef.value) {
            // 清空问题列表
            querySectionRef.value.clearQuestions()
          }
        }, 1000)
      }
    }

    previousFileCount.value = newFileCount
  },
  { deep: true }
)

// 组件挂载时启动示例轮播
onMounted(() => {
  store.databaseId = route.params.database_id
  resetFileSelectionState()
  store.getDatabaseInfo()
  store.startAutoRefresh()

  // 添加拖拽事件监听（仅水平方向）
  if (resizeHandle.value) {
    resizeHandle.value.addEventListener('mousedown', handleMouseDown)
  }
})

// 组件卸载时停止示例轮播
onUnmounted(() => {
  store.stopAutoRefresh()
  if (resizeHandle.value) {
    resizeHandle.value.removeEventListener('mousedown', handleMouseDown)
  }
  document.removeEventListener('mousemove', handleMouseMove)
  document.removeEventListener('mouseup', handleMouseUp)
})

// 拖拽调整大小功能
const handleMouseDown = () => {
  isDragging.value = true
  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

const handleMouseMove = (e) => {
  if (!isDragging.value) return

  const container = document.querySelector('.unified-layout')
  if (!container) return

  const containerRect = container.getBoundingClientRect()
  const newWidth = ((e.clientX - containerRect.left) / containerRect.width) * 100
  leftPanelWidth.value = Math.max(20, Math.min(80, newWidth))
}

const handleMouseUp = () => {
  isDragging.value = false
  document.removeEventListener('mousemove', handleMouseMove)
  document.removeEventListener('mouseup', handleMouseUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}
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
  background-color: var(--gray-0);
  gap: 0;

  .left-panel,
  .right-panel {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 8px;
  }

  .left-panel {
    display: flex;
    flex-shrink: 0;
    flex-grow: 1;
    padding-right: 0;
    flex-direction: column;
    // max-height: calc(100% - 16px);
  }

  .info-panel {
    background: var(--gray-10);
    border-radius: 12px;
    border: 1px solid var(--gray-200);
    display: flex;
    gap: 12px;
    padding: 8px 12px;
    margin-bottom: 8px;
    flex-shrink: 0;

    .banner-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 8px;
      background: var(--color-warning-50);
      border-radius: 4px;
      font-size: 13px;
      color: var(--color-warning-700);
      cursor: pointer;
      transition: all 0.2s;

      &:hover {
        background: var(--color-warning-100);
      }

      svg {
        color: var(--color-warning-700);
      }
    }
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
  background: var(--gray-10);
  overflow: hidden;

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
    // background-color: var(--gray-0);
    border-bottom: 1px solid var(--gray-200);
  }

  :deep(.ant-tabs-extra-content) {
    display: flex;
    align-items: center;
    height: 100%;
  }
}

.config-btn {
  color: var(--gray-600);
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 8px;
  height: 32px;
  border-radius: 6px;
  transition: all 0.2s;

  &:hover {
    color: var(--main-color);
    background-color: var(--gray-100);
  }

  .config-text {
    font-size: 13px;
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
    border-bottom: 1px solid var(--gray-150);
    background-color: var(--gray-25);

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

// 基准管理样式
.benchmark-management-container {
  height: 100%;
  background: var(--gray-0);
  display: flex;
  flex-direction: column;
}

.benchmark-content {
  flex: 1;
  overflow: hidden;
  min-height: 0;
  padding: 12px 16px;
}
</style>
