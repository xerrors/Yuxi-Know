<template>
  <div class="knowledge-base-info-container">
    <ExtensionDetailLayout
      :active-key="activeTab"
      :tabs="visibleTabs"
      @update:active-key="handleActiveTabChange"
      :loading="detailLoading"
      :ready="isCurrentKnowledgeBaseLoaded && supportsDetail"
      empty-description="未找到知识库"
      class="knowledge-detail-layout"
    >
      <template #breadcrumb>
        <nav class="extension-detail-breadcrumb" aria-label="知识库详情导航">
          <button type="button" class="extension-detail-back" @click="backToKnowledgeBase">
            知识库
          </button>
          <ChevronRight :size="15" aria-hidden="true" />
          <span class="extension-detail-current" :title="knowledgeBase.name || kbId">
            {{ knowledgeBase.name || kbId }}
          </span>
        </nav>
      </template>

      <template #actions>
        <div class="extension-detail-actions">
          <a-space :size="8">
            <a-button
              type="text"
              aria-label="复制知识库 ID"
              title="复制知识库 ID"
              class="lucide-icon-btn extension-detail-action"
              @click="copyKnowledgeBaseId"
            >
              <Copy :size="14" />
              <span>复制 ID</span>
            </a-button>
            <a-button
              v-if="canManageKnowledgeBase"
              type="text"
              aria-label="配置知识库"
              title="配置知识库"
              class="lucide-icon-btn extension-detail-action"
              @click="showEditModal"
            >
              <Pencil :size="14" />
              <span>配置</span>
            </a-button>
          </a-space>
        </div>
      </template>

      <template #panel-filetable>
        <div v-if="isMilvus" v-show="activeTab === 'filetable'" class="tab-panel file-panel">
          <div class="file-management-info">
            <div class="file-info-title">
              <div class="file-info-title-row">
                <div
                  v-if="canManageKnowledgeBase"
                  ref="uploadActionMenuRef"
                  class="file-action-dropdown"
                >
                  <button
                    type="button"
                    class="lucide-icon-btn extension-panel-action extension-panel-action-primary"
                    @click="uploadActionMenuOpen = !uploadActionMenuOpen"
                  >
                    <Upload :size="14" />
                    <span>上传</span>
                    <ChevronDown
                      :size="12"
                      class="file-action-chevron"
                      :class="{ 'is-open': uploadActionMenuOpen }"
                    />
                  </button>
                  <Transition name="file-action-menu">
                    <div v-if="uploadActionMenuOpen" class="file-action-menu">
                      <button type="button" class="file-action-menu-item" @click="onUploadAction">
                        <Upload :size="14" />
                        <span>上传文件</span>
                      </button>
                      <button
                        type="button"
                        class="file-action-menu-item"
                        @click="onUploadFolderAction"
                      >
                        <FolderUp :size="14" />
                        <span>上传文件夹</span>
                      </button>
                      <button
                        type="button"
                        class="file-action-menu-item"
                        @click="onCreateFolderAction"
                      >
                        <FolderPlus :size="14" />
                        <span>新建文件夹</span>
                      </button>
                    </div>
                  </Transition>
                </div>
              </div>
            </div>
            <div class="file-panel-status">
              <button
                v-if="canManageKnowledgeBase && pendingParseCount > 0"
                type="button"
                class="lucide-icon-btn extension-panel-action extension-panel-action-secondary file-stat-card file-stat-warning file-stat-summary"
                :disabled="store.state.chunkLoading"
                @click="confirmBatchParse"
              >
                <FileText :size="16" />
                <div class="file-stat-inline">
                  <span class="file-stat-value">{{ pendingParseCount }}</span>
                  <span class="file-stat-label">待解析</span>
                </div>
              </button>
              <button
                v-if="canManageKnowledgeBase && pendingIndexCount > 0"
                type="button"
                class="lucide-icon-btn extension-panel-action extension-panel-action-secondary file-stat-card file-stat-warning file-stat-summary"
                :disabled="store.state.chunkLoading"
                @click="confirmBatchIndex"
              >
                <DatabaseIcon :size="16" />
                <div class="file-stat-inline">
                  <span class="file-stat-value">{{ pendingIndexCount }}</span>
                  <span class="file-stat-label">待入库</span>
                </div>
              </button>
              <div class="file-stat-card file-stat-summary">
                <FileText :size="16" />
                <div class="file-stat-inline">
                  <span class="file-stat-value">{{ fileStats.count }}</span>
                  <span class="file-stat-label">文件</span>
                </div>
              </div>
              <div
                v-if="fileStats.sizeText"
                class="lucide-icon-btn extension-panel-action extension-panel-action-secondary file-stat-card file-stat-summary"
                :title="`文件大小 ${fileStats.sizeText}`"
              >
                <DatabaseIcon :size="16" aria-hidden="true" />
                <div class="file-stat-inline">
                  <span class="file-stat-value">{{ fileStats.sizeText }}</span>
                </div>
              </div>
              <div class="file-stat-card file-stat-summary">
                <DatabaseIcon :size="16" />
                <div class="file-stat-inline">
                  <span class="file-stat-value">{{ fileStats.chunkText }}</span>
                  <span class="file-stat-label">Chunks</span>
                </div>
              </div>
              <div class="file-stat-card file-stat-summary">
                <Hash :size="16" />
                <div class="file-stat-inline">
                  <span class="file-stat-value">{{ fileStats.tokenText }}</span>
                  <span class="file-stat-label">Tokens</span>
                </div>
              </div>
            </div>
          </div>
          <FileTable
            ref="fileTableRef"
            :readonly="!canManageKnowledgeBase"
            @search="fileSearchModalVisible = true"
          />
        </div>
      </template>

      <template #panel-query>
        <div
          v-if="supportsDetail"
          v-show="activeTab === 'query'"
          class="tab-panel query-config-panel"
        >
          <QuerySection ref="querySectionRef" :visible="true" @toggle-visible="() => {}" />
        </div>
      </template>

      <template #panel-graph>
        <div v-if="isMilvus && activeTab === 'graph'" class="tab-panel">
          <KnowledgeGraphSection
            :visible="true"
            :active="activeTab === 'graph'"
            :readonly="!canManageKnowledgeBase"
            @toggle-visible="() => {}"
          />
        </div>
      </template>

      <template #panel-evaluation>
        <div v-if="isMilvus && activeTab === 'evaluation'" class="tab-panel evaluation-panel">
          <KnowledgeEvaluationWorkspace v-if="kbId" :kb-id="kbId" :can-manage="canManageKnowledgeBase" />
        </div>
      </template>
    </ExtensionDetailLayout>

    <FileDetailModal
      v-model:open="store.state.fileDetailModalVisible"
      :kb-id="kbId"
      :file-id="store.fileDetailFileId"
      @closed="store.closeFileDetail"
    />

    <FileUploadModal
      v-model:visible="addFilesModalVisible"
      :folder-tree="folderTree"
      :current-folder-id="currentFolderId"
      :is-folder-mode="isFolderUploadMode"
      :mode="addFilesMode"
      @success="onFileUploadSuccess"
    />

    <FileSearchModal
      v-model:open="fileSearchModalVisible"
      :kb-id="kbId"
      @select="onFileSearchSelect"
    />

    <a-modal
      v-model:open="editModalVisible"
      title="配置知识库"
      width="720px"
      :mask-closable="false"
      wrap-class-name="knowledge-base-edit-modal"
      @after-close="handleEditModalAfterClose"
    >
      <template #footer>
        <a-button key="close" @click="editModalVisible = false">关闭</a-button>
        <a-button key="submit" type="primary" :loading="editSaving" @click="handleEditSubmit">
          保存
        </a-button>
      </template>
      <a-form :model="editForm" :rules="rules" ref="editFormRef" layout="vertical">
        <a-tabs v-model:active-key="editModalTab" class="knowledge-base-edit-tabs">
          <a-tab-pane key="basic" tab="基础信息">
            <div class="knowledge-base-edit-tab-content">
              <a-form-item label="知识库名称" name="name" required>
                <a-input v-model:value="editForm.name" placeholder="请输入知识库名称" />
              </a-form-item>
              <a-form-item label="知识库描述" name="description">
                <AiTextarea
                  v-model="editForm.description"
                  :name="editForm.name"
                  :files="fileList"
                  placeholder="请输入知识库描述"
                  action-placement="header"
                  :rows="4"
                />
              </a-form-item>

              <a-form-item v-if="knowledgeBase?.embedding_model_spec" label="Embedding 模型">
                <div class="readonly-model-field">
                  <span class="readonly-model-value" :title="knowledgeBase.embedding_model_spec">
                    {{ knowledgeBase.embedding_model_spec }}
                  </span>
                  <span class="readonly-model-hint">创建后不可修改</span>
                </div>
              </a-form-item>

              <a-form-item v-if="!isConnector" name="chunk_preset_id">
                <template #label>
                  <span class="chunk-preset-label">
                    分块策略
                    <a-tooltip :title="editPresetDescription">
                      <QuestionCircleOutlined class="chunk-preset-help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="editForm.chunk_preset_id"
                  :options="chunkPresetOptions"
                  :loading="chunkPresetLoading"
                />
              </a-form-item>
              <template v-if="isDifyKb">
                <a-form-item label="Dify API URL" name="dify_api_url">
                  <a-input
                    v-model:value="editForm.dify_api_url"
                    placeholder="例如: https://api.dify.ai/v1"
                  />
                </a-form-item>
                <a-form-item label="Dify Token" name="dify_token">
                  <a-input-password
                    v-model:value="editForm.dify_token"
                    placeholder="请输入 Dify API Token"
                  />
                </a-form-item>
                <a-form-item label="Dataset ID" name="dify_dataset_id">
                  <a-input
                    v-model:value="editForm.dify_dataset_id"
                    placeholder="请输入 Dify dataset_id"
                  />
                </a-form-item>
              </template>

              <template v-if="knowledgeBase.kb_type === 'feishu'">
                <a-form-item label="User Access Token">
                  <a-input-password v-model:value="editForm.feishu_user_token" placeholder="留空保持现有凭证；过期时填入新的用户 Token" />
                </a-form-item>
                <a-form-item label="知识空间 ID">
                  <a-input v-model:value="editForm.feishu_space_id" placeholder="知识库设置 URL 中的数字 ID" />
                </a-form-item>
              </template>
              <template v-if="isNotionKb">
                <a-form-item label="Notion Token" name="notion_token">
                  <a-input-password
                    v-model:value="editForm.notion_token"
                    placeholder="留空则保持现有 Token 或使用环境变量"
                  />
                </a-form-item>
                <a-form-item label="Data Source ID" name="notion_data_source_id">
                  <a-input
                    v-model:value="editForm.notion_data_source_id"
                    placeholder="请输入 Notion data_source_id"
                  />
                </a-form-item>
                <a-form-item label="Notion API Version" name="notion_version">
                  <a-input v-model:value="editForm.notion_version" placeholder="2026-03-11" />
                </a-form-item>
              </template>
            </div>
          </a-tab-pane>

          <a-tab-pane key="permission" tab="权限配置">
            <div class="knowledge-base-edit-tab-content">
              <a-form-item v-if="canEditShareConfig" name="share_config">
                <a-form-item-rest>
                  <ShareConfigForm
                    ref="shareConfigFormRef"
                    v-model="editShareConfig"
                    :auto-select-user-dept="true"
                    :require-read-scope="true"
                  />
                </a-form-item-rest>
              </a-form-item>
              <div v-else-if="knowledgeBase.share_config" class="share-config-readonly">
                <a-tag :color="shareConfigDisplay.color">{{ shareConfigDisplay.label }}</a-tag>
                <span class="access-names">{{ shareConfigDisplay.detail }}</span>
              </div>
            </div>
          </a-tab-pane>

          <a-tab-pane key="retrieval" tab="检索配置" force-render>
            <div class="knowledge-base-edit-tab-content retrieval-config-content">
              <p class="knowledge-base-edit-tab-description">
                调整当前知识库在检索测试和 Agent 使用时采用的参数。
              </p>
              <SearchConfigPanel v-if="editModalVisible" ref="searchConfigPanelRef" :kb-id="kbId" />
            </div>
          </a-tab-pane>
        </a-tabs>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useKnowledgeBaseStore } from '@/modules/knowledge/model/knowledgeBase'
import { useBackgroundJobsStore } from '@/modules/background-jobs/model/jobs'
import {
  BarChart3,
  ChevronDown,
  ChevronRight,
  Copy,
  Database as DatabaseIcon,
  FileText,
  FolderPlus,
  FolderUp,
  Hash,
  Network,
  Pencil,
  Search,
  Upload,
  CircleHelp as QuestionCircleOutlined
} from '@lucide/vue'
import { message } from 'ant-design-vue'
import ExtensionDetailLayout from '@/shared/ui/ExtensionDetailLayout.vue'
import FileTable from '@/modules/knowledge/ui/FileTable.vue'
import FileDetailModal from '@/modules/knowledge/ui/FileDetailModal.vue'
import FileUploadModal from '@/modules/knowledge/ui/FileUploadModal.vue'
import FileSearchModal from '@/modules/knowledge/ui/FileSearchModal.vue'
import QuerySection from '@/modules/knowledge/ui/QuerySection.vue'
import SearchConfigPanel from '@/modules/knowledge/ui/SearchConfigPanel.vue'
import AiTextarea from '@/modules/agents/ui/AiTextarea.vue'
import ShareConfigForm from '@/modules/agents/ui/ShareConfigForm.vue'
import { departmentApi } from '@/apis/department_api'
import { authApi } from '@/apis/auth_api'
import { useChunkPresetOptions } from '@/modules/knowledge/model/useChunkPresetOptions'
import { DEFAULT_CHUNK_PRESET_ID } from '@/modules/knowledge/model/chunkUtils'
import { kbUtils } from '@/modules/knowledge/model/kb_utils'
import { createAsyncPanel } from '@/shared/lib/asyncPanel'

const KnowledgeGraphSection = createAsyncPanel(
  () => import('@/modules/knowledge/ui/KnowledgeGraphSection.vue')
)
const KnowledgeEvaluationWorkspace = createAsyncPanel(
  () => import('@/modules/knowledge/ui/KnowledgeEvaluationWorkspace.vue')
)

const route = useRoute()
const router = useRouter()
const store = useKnowledgeBaseStore()
const jobsStore = useBackgroundJobsStore()
const {
  chunkPresetSelectOptions: chunkPresetOptions,
  chunkPresetLoading,
  loadChunkPresetOptions,
  getChunkPresetDescription
} = useChunkPresetOptions()

const kbId = computed(() => store.kbId)
const knowledgeBase = computed(() => store.knowledgeBase)
const canManageKnowledgeBase = computed(() => knowledgeBase.value?.can_manage === true)
const isCurrentKnowledgeBaseLoaded = computed(() => knowledgeBase.value?.kb_id === kbId.value)
const kbType = computed(() =>
  isCurrentKnowledgeBaseLoaded.value ? knowledgeBase.value.kb_type?.toLowerCase() || 'milvus' : ''
)
const supportsDetail = computed(() => kbUtils.supportsKnowledgeBaseDetail(knowledgeBase.value))
const isMilvus = computed(() => kbType.value === 'milvus')
const isDifyKb = computed(() => kbType.value === 'dify')
const isNotionKb = computed(() => kbType.value === 'notion')
const isConnector = computed(
  () => isCurrentKnowledgeBaseLoaded.value && kbUtils.isReadOnlyKnowledgeBase(knowledgeBase.value)
)
const tabs = computed(() => {
  if (isMilvus.value) {
    return [
      { key: 'filetable', label: '文件管理', icon: FileText },
      { key: 'query', label: '检索测试', icon: Search, forceRender: true },
      { key: 'graph', label: '知识图谱', icon: Network },
      { key: 'evaluation', label: '评估', icon: BarChart3 }
    ]
  }

  return [{ key: 'query', label: '检索测试', icon: Search, forceRender: true }]
})

const visibleTabs = computed(() =>
  canManageKnowledgeBase.value
    ? tabs.value
    : tabs.value.filter((tab) => ['filetable', 'query', 'graph'].includes(tab.key))
)
const activeTab = ref('filetable')

watch(
  () => [kbId.value, route.query.section, visibleTabs.value, isCurrentKnowledgeBaseLoaded.value],
  ([newKbId, requestedTab, availableTabs, loaded]) => {
    if (!newKbId) return
    const fallbackTab = availableTabs[0]?.key || 'query'
    activeTab.value = availableTabs.some((tab) => tab.key === requestedTab)
      ? requestedTab
      : fallbackTab

    if (loaded && requestedTab && requestedTab !== activeTab.value) {
      router.replace({ query: { ...route.query, section: activeTab.value } })
    }
  },
  { immediate: true }
)

const handleActiveTabChange = (tab) => {
  if (!visibleTabs.value.some((item) => item.key === tab)) return
  activeTab.value = tab
  if (route.query.section !== tab) {
    router.replace({ query: { ...route.query, section: tab } })
  }
}

const pendingParseCount = computed(() => {
  return Number(store.knowledgeBase.stats?.pending_parse_count || 0)
})

const formatStatNumber = (value) => {
  const number = Number(value ?? 0)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : '0'
}

const formatCompactFileSize = (bytes) => {
  const number = Number(bytes)
  if (!Number.isFinite(number) || number <= 0) return ''

  const units = ['b', 'kb', 'mb', 'gb', 'tb', 'pb']
  let unitIndex = 0
  let value = number
  while (value >= 1000 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }

  const decimals = value >= 100 ? 0 : value >= 10 ? 1 : 2
  return `${Number(value.toFixed(decimals))}${units[unitIndex]}`
}

const formatTokenStatNumber = (value) => {
  const number = Number(value ?? 0)
  if (!Number.isFinite(number)) return '0'
  const absNumber = Math.abs(number)
  if (absNumber > 1024 * 1000) return `${(number / 1_000_000).toFixed(1)} m`
  if (absNumber >= 1000) return `${Math.round(number / 1000).toLocaleString('zh-CN')} k`
  return number.toLocaleString('zh-CN')
}

const fileStats = computed(() => {
  const stats = store.knowledgeBase.stats || {}
  const statsFileCount = Number(stats.file_count)
  const totalSize = Number(stats.total_size || 0)

  return {
    count: Number.isFinite(statsFileCount) ? statsFileCount : 0,
    sizeText: totalSize > 0 ? formatCompactFileSize(totalSize) : '',
    chunkText: formatStatNumber(stats.chunk_count),
    tokenText: formatTokenStatNumber(stats.token_count)
  }
})

const pendingIndexCount = computed(() => {
  return Number(store.knowledgeBase.stats?.pending_index_count || 0)
})

const confirmBatchParse = () => {
  const count = pendingParseCount.value
  if (count <= 0) {
    message.info('没有待解析文档')
    return
  }

  const opened = fileTableRef.value?.startPendingParse?.(count)
  if (!opened) {
    message.error('文件列表尚未加载完成，请稍后再试')
  }
}

const confirmBatchIndex = () => {
  const count = pendingIndexCount.value
  if (count <= 0) {
    message.info('没有待入库文档')
    return
  }

  const opened = fileTableRef.value?.startPendingIndex?.(count)
  if (!opened) {
    message.error('文件列表尚未加载完成，请稍后再试')
  }
}

const querySectionRef = ref(null)
const searchConfigPanelRef = ref(null)

const addFilesModalVisible = ref(false)
const fileSearchModalVisible = ref(false)

const onFileSearchSelect = (file) => {
  if (file?.file_id) {
    store.openFileDetail(file.file_id)
  }
}
const currentFolderId = ref(null)
const isFolderUploadMode = ref(false)
const addFilesMode = ref('file')
const isInitialLoad = ref(true)
const detailLoading = ref(true)
const fileTableRef = ref(null)

const showAddFilesModal = (options = {}) => {
  const { isFolder = false, mode = 'file' } = options
  isFolderUploadMode.value = isFolder
  addFilesMode.value = mode
  addFilesModalVisible.value = true
  currentFolderId.value =
    fileTableRef.value?.getCurrentFolderId?.() || store.fileBrowser.parentId || null
}

const showCreateFolderModal = () => {
  fileTableRef.value?.showCreateFolderModal()
}

const uploadActionMenuRef = ref(null)
const uploadActionMenuOpen = ref(false)

const onUploadAction = () => {
  uploadActionMenuOpen.value = false
  showAddFilesModal()
}

const onUploadFolderAction = () => {
  uploadActionMenuOpen.value = false
  showAddFilesModal({ isFolder: true, mode: 'folder' })
}

const onCreateFolderAction = () => {
  uploadActionMenuOpen.value = false
  showCreateFolderModal()
}

const onUploadMenuOutsideClick = (event) => {
  if (uploadActionMenuRef.value && !uploadActionMenuRef.value.contains(event.target)) {
    uploadActionMenuOpen.value = false
  }
}

const folderTree = computed(() => {
  const roots = []
  let currentLevel = roots
  for (const item of (store.folderBreadcrumbs || [])
    .slice(1)
    .filter((node) => !node.is_virtual_folder)) {
    const node = {
      file_id: item.file_id,
      filename: item.filename,
      is_folder: true,
      children: []
    }
    currentLevel.push(node)
    currentLevel = node.children
  }
  return roots
})

const onFileUploadSuccess = () => {
  jobsStore.loadJobs()
}

const resetFileSelectionState = () => {
  store.selectedRowKeys = []
  store.closeFileDetail()
  store.resetFileBrowser()
}

watch(
  () => route.params.kbId,
  async (nextKbId) => {
    isInitialLoad.value = true
    detailLoading.value = true
    store.kbId = nextKbId
    resetFileSelectionState()
    store.stopAutoRefresh()
    try {
      await store.getKnowledgeBaseInfo(nextKbId, false)
      if (store.knowledgeBase?.kb_id === nextKbId && !kbUtils.supportsKnowledgeBaseDetail(store.knowledgeBase)) {
        if (route.query.action === 'edit' && canManageKnowledgeBase.value) {
          showEditModal()
          return
        }
        await router.replace({ path: '/extensions', query: { tab: 'knowledge' } })
        return
      }
      store.startAutoRefresh()
    } finally {
      detailLoading.value = false
    }
  },
  { immediate: true }
)

const previousFileCount = ref(0)

watch(
  () => knowledgeBase.value?.stats?.file_count,
  (newFileCountValue) => {
    const newFileCount = Number(newFileCountValue || 0)
    const oldFileCount = previousFileCount.value

    if (isInitialLoad.value) {
      previousFileCount.value = newFileCount
      isInitialLoad.value = false
      return
    }

    if (newFileCount !== oldFileCount) {
      if (newFileCount > 0 && canManageKnowledgeBase.value) {
        setTimeout(async () => {
          if (querySectionRef.value) {
            if (knowledgeBase.value.additional_params?.auto_generate_questions) {
              await querySectionRef.value.generateSampleQuestions(true)
            }
          } else {
            setTimeout(async () => {
              if (
                querySectionRef.value &&
                knowledgeBase.value.additional_params?.auto_generate_questions
              ) {
                await querySectionRef.value.generateSampleQuestions(true)
              }
            }, 2000)
          }
        }, 3000)
      } else {
        setTimeout(() => {
          querySectionRef.value?.clearQuestions()
        }, 1000)
      }
    }

    previousFileCount.value = newFileCount
  },
  { deep: false }
)

const backToKnowledgeBase = () => {
  router.push({ path: '/extensions', query: { tab: 'knowledge' } })
}

const copyKnowledgeBaseId = async () => {
  if (!knowledgeBase.value.kb_id) {
    message.warning('知识库ID为空')
    return
  }

  try {
    await navigator.clipboard.writeText(knowledgeBase.value.kb_id)
    message.success('知识库ID已复制到剪贴板')
  } catch {
    const textArea = document.createElement('textarea')
    textArea.value = knowledgeBase.value.kb_id
    document.body.appendChild(textArea)
    textArea.select()
    document.execCommand('copy')
    document.body.removeChild(textArea)
    message.success('知识库ID已复制到剪贴板')
  }
}

const departments = ref([])
const users = ref([])
const editModalVisible = ref(false)
const editModalTab = ref('basic')
const editSaving = ref(false)
const editFormRef = ref(null)
const shareConfigFormRef = ref(null)
const editShareConfig = ref({
  version: 2,
  read_scope: { access_level: 'global', department_ids: [], user_uids: [] },
  manage_scope: null
})
const editForm = reactive({
  name: '',
  description: '',
  chunk_preset_id: DEFAULT_CHUNK_PRESET_ID,
  dify_api_url: '',
  dify_token: '',
  dify_dataset_id: '',
  feishu_user_token: '',
  feishu_space_id: '',
  notion_token: '',
  notion_data_source_id: '',
  notion_version: '2026-03-11'
})

const rules = {
  name: [{ required: true, message: '请输入知识库名称' }]
}

const editPresetDescription = computed(() => getChunkPresetDescription(editForm.chunk_preset_id))
const fileList = computed(() => {
  return (store.documentFiles || []).map((f) => f.filename).filter(Boolean)
})

const canEditShareConfig = computed(() => canManageKnowledgeBase.value)

const shareConfigDisplay = computed(() => {
  const shareConfig = knowledgeBase.value?.share_config || {}
  const readScope = shareConfig.version === 2 ? shareConfig.read_scope : shareConfig
  const manageScope = shareConfig.manage_scope
  const describeScope = (scope) => {
    if (!scope) return '无'
    if (scope.access_level === 'global') return '全局'
    if (scope.access_level === 'department') {
      const names =
        (scope.department_ids || []).map((id) => getDepartmentName(id)).join('、') || '无'
      return `${scope.department_ids?.length || 0} 个部门：${names}`
    }
    const names = (scope.user_uids || []).map((uid) => getUserName(uid)).join('、') || '无'
    return `${scope.user_uids?.length || 0} 个用户：${names}`
  }
  if (manageScope) {
    return {
      color: 'blue',
      label: '分级共享',
      detail: `读取：${describeScope(readScope)}；管理：${describeScope(manageScope)}`
    }
  }
  return {
    color: 'green',
    label: readScope?.access_level === 'global' ? '全局只读' : '共享只读',
    detail: `读取：${describeScope(readScope)}`
  }
})

const getDepartmentName = (id) => {
  const dept = departments.value.find((item) => Number(item.id) === Number(id))
  return dept?.name || `部门${id}`
}

const getUserName = (uid) => {
  const user = users.value.find((item) => item.uid === uid)
  return user?.username || uid
}

const loadDepartments = async () => {
  try {
    const res = await departmentApi.getDepartments()
    departments.value = res || []
  } catch {
    departments.value = []
  }
}

const loadUsers = async () => {
  try {
    users.value = await authApi.getUserAccessOptions()
  } catch {
    users.value = []
  }
}

const handleEditModalAfterClose = () => {
  if (!supportsDetail.value) backToKnowledgeBase()
}

const showEditModal = () => {
  editModalTab.value = 'basic'
  editForm.name = knowledgeBase.value.name || ''
  editForm.description = knowledgeBase.value.description || ''
  editForm.chunk_preset_id =
    knowledgeBase.value.additional_params?.chunk_preset_id || DEFAULT_CHUNK_PRESET_ID
  editForm.dify_api_url = knowledgeBase.value.additional_params?.dify_api_url || ''
  editForm.dify_token = knowledgeBase.value.additional_params?.dify_token || ''
  editForm.dify_dataset_id = knowledgeBase.value.additional_params?.dify_dataset_id || ''
  editForm.feishu_user_token = ''
  editForm.feishu_space_id = knowledgeBase.value.additional_params?.feishu_space_id || ''
  editForm.notion_token = ''
  editForm.notion_data_source_id = knowledgeBase.value.additional_params?.notion_data_source_id || ''
  editForm.notion_version = knowledgeBase.value.additional_params?.notion_version || '2026-03-11'
  editShareConfig.value = knowledgeBase.value.share_config || {
    version: 2,
    read_scope: { access_level: 'global', department_ids: [], user_uids: [] },
    manage_scope: null
  }
  editModalVisible.value = true
}

watch(
  () => [route.query.action, detailLoading.value, isCurrentKnowledgeBaseLoaded.value],
  ([action, loading, loaded]) => {
    if (action !== 'edit' || loading || !loaded || !canManageKnowledgeBase.value) return
    showEditModal()
    router.replace({ path: route.path, query: { ...route.query, action: undefined } })
  },
  { immediate: true }
)

const handleEditSubmit = async () => {
  editSaving.value = true
  try {
    await editFormRef.value.validate()

    if (shareConfigFormRef.value) {
      const validation = shareConfigFormRef.value.validate()
      if (!validation.valid) {
        editModalTab.value = 'permission'
        message.warning(validation.message)
        return
      }
    }

    const updateData = {
      name: editForm.name,
      description: editForm.description,
      additional_params: {},
      share_config: editShareConfig.value
    }

    if (isDifyKb.value) {
      if (
        !editForm.dify_api_url?.trim() ||
        !editForm.dify_token?.trim() ||
        !editForm.dify_dataset_id?.trim()
      ) {
        editModalTab.value = 'basic'
        message.error('请完整填写 Dify API URL、Token 和 Dataset ID')
        return
      }
      if (!editForm.dify_api_url.trim().endsWith('/v1')) {
        editModalTab.value = 'basic'
        message.error('Dify API URL 必须以 /v1 结尾')
        return
      }
      updateData.additional_params = {
        dify_api_url: editForm.dify_api_url.trim(),
        dify_token: editForm.dify_token.trim(),
        dify_dataset_id: editForm.dify_dataset_id.trim()
      }
    } else if (knowledgeBase.value.kb_type === 'feishu') {
      if (!/^[0-9]+$/.test(editForm.feishu_space_id.trim())) {
        editModalTab.value = 'basic'
        message.error('请填写数字知识空间 ID')
        return
      }
      updateData.additional_params = { feishu_space_id: editForm.feishu_space_id.trim() }
      if (editForm.feishu_user_token.trim()) {
        updateData.additional_params.feishu_user_token = editForm.feishu_user_token.trim()
      }
    } else if (isNotionKb.value) {
      if (!editForm.notion_data_source_id?.trim()) {
        editModalTab.value = 'basic'
        message.error('请填写 Notion Data Source ID')
        return
      }
      updateData.additional_params = {
        notion_data_source_id: editForm.notion_data_source_id.trim(),
        notion_version: editForm.notion_version?.trim() || '2026-03-11'
      }
      if (editForm.notion_token?.trim()) {
        updateData.additional_params.notion_token = editForm.notion_token.trim()
      }
    } else {
      updateData.additional_params = {
        chunk_preset_id: editForm.chunk_preset_id || DEFAULT_CHUNK_PRESET_ID
      }
    }

    if (searchConfigPanelRef.value?.hasChanges?.()) {
      const searchConfigSaved = await searchConfigPanelRef.value.save({ notify: false })
      if (searchConfigSaved === false) {
        editModalTab.value = 'retrieval'
        return
      }
    }

    await store.updateKnowledgeBaseInfo(updateData)
  } catch (err) {
    editModalTab.value = 'basic'
    console.error('表单验证失败:', err)
  } finally {
    editSaving.value = false
  }
}

onMounted(() => {
  loadChunkPresetOptions()
  loadDepartments()
  loadUsers()
  document.addEventListener('click', onUploadMenuOutsideClick)
})

onUnmounted(() => {
  store.stopAutoRefresh()
  document.removeEventListener('click', onUploadMenuOutsideClick)
})
</script>

<style lang="less" scoped>

.knowledge-base-info-container,
.knowledge-detail-layout {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.tab-panel {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 16px var(--page-padding);
}

.file-panel {
  gap: 8px;
}

.query-config-panel {
  overflow: hidden;

  :deep(.query-section) {
    flex: 1;
    min-width: 0;
  }
}

.evaluation-panel {
  padding: 0;
}

.file-panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  padding: 10px 12px;
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 8px;
}

.file-panel-summary {
  display: flex;
  align-items: baseline;
  min-width: 0;
  gap: 8px;
}

.file-panel-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--gray-900);
  white-space: nowrap;
}

.file-panel-count {
  font-size: 12px;
  color: var(--gray-500);
  white-space: nowrap;
}

.file-management-info {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  flex-shrink: 0;
}

.file-info-title {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 180px;
}

.file-info-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.file-action-dropdown {
  position: relative;

  .extension-panel-action {
    min-height: 32px;
    font-size: 14px;
  }
}

.file-action-chevron {
  transition: transform 0.15s ease;

  &.is-open {
    transform: rotate(180deg);
  }
}

.file-action-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 20;
  min-width: 130px;
  padding: 4px;
  background: var(--gray-0);
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.file-action-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--gray-700);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition:
    background 0.12s ease,
    color 0.12s ease;

  &:hover {
    background: var(--gray-100);
    color: var(--gray-900);
  }

  &:active {
    transform: scale(0.97);
  }
}

.file-action-menu-enter-active {
  transition:
    opacity 0.16s ease,
    transform 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}

.file-action-menu-leave-active {
  transition:
    opacity 0.12s ease,
    transform 0.16s ease;
}

.file-action-menu-enter-from,
.file-action-menu-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.96);
}

.file-panel-desc {
  font-size: 12px;
  color: var(--gray-500);
}

.file-panel-status {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.file-stat-card {
  min-width: 60px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 6px;
  background: var(--gray-0);
  border: 1px solid var(--gray-200);
  box-shadow: none;
  color: var(--gray-700);
  font-family: inherit;
  font-size: 12px;
  font-weight: 400;
  line-height: 1;
  appearance: none;
  text-align: center;
  cursor: default;
  justify-content: center;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease;

  div {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }

  svg {
    flex: 0 0 auto;
  }

  .file-stat-value,
  .file-stat-label {
    white-space: nowrap;
  }

  .file-stat-value {
    font-size: 13px;
    font-weight: 400;
    line-height: 1.2;
    color: var(--gray-900);
  }

  .file-stat-label {
    font-size: 10px;
    font-weight: 400;
    color: var(--gray-500);
  }

  &:hover:not(:disabled),
  &:focus-visible:not(:disabled) {
    border-color: var(--gray-300);
    background: var(--gray-0);
    color: var(--gray-900);
    outline: none;
  }
}

.file-stat-summary {
  min-width: 87px;
  min-height: 30px;

  .file-stat-inline {
    flex-direction: row;
    align-items: baseline;
    gap: 4px;
  }
}

.file-stat-warning {
  cursor: pointer;
  color: var(--color-warning-700);
  border-color: var(--color-warning-100);
  background: var(--color-warning-50);

  .file-stat-value {
    color: var(--color-warning-900);
  }

  &:hover:not(:disabled),
  &:focus-visible:not(:disabled) {
    border-color: var(--color-warning-500);
    background: var(--color-warning-50);
    color: var(--color-warning-900);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
}

.knowledge-base-edit-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 20px;
}

.knowledge-base-edit-tab-content {
  min-height: 360px;
}

.knowledge-base-edit-tab-description {
  margin: 0 0 16px;
  color: var(--gray-500);
  font-size: 13px;
  line-height: 1.5;
}

.retrieval-config-content {
  min-width: 0;
  padding: 0;
  overflow-x: hidden;
}

:global(.knowledge-base-edit-modal .ant-modal-body) {
  max-height: min(680px, 70vh);
  overflow-y: auto;
}

.share-config-readonly {
  display: flex;
  align-items: center;
  gap: 8px;

  .access-names {
    font-size: 13px;
    color: var(--gray-600);
  }
}

.chunk-preset-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.readonly-model-field {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  box-sizing: border-box;
  padding: 7px 11px;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  background: var(--gray-25);
}

.readonly-model-value {
  min-width: 0;
  overflow: hidden;
  color: var(--gray-800);
  font-family: var(--mono-font, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.readonly-model-hint {
  flex: 0 0 auto;
  color: var(--gray-500);
  font-size: 12px;
  white-space: nowrap;
}

.chunk-preset-help-icon {
  color: var(--gray-500);
  cursor: help;
  font-size: 14px;
}

.form-item-help-text {
  margin-left: 8px;
  color: var(--gray-500);
  font-size: 12px;
}

@media (max-width: 1024px) {
  .knowledge-base-edit-tab-content {
    min-height: 320px;
  }
}

@media (max-width: 767px) {
  .extension-detail-actions :deep(.extension-detail-action span) {
    display: none;
  }

  .retrieval-config-content :deep(.ant-col) {
    max-width: 100%;
    flex: 0 0 100%;
  }

  .file-panel-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>

<style lang="less">
@media (max-width: 767px) {
  .app-layout:has(.knowledge-base-info-container) {
    min-width: 0;
  }
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

.graph-section {
  border: 1px solid var(--gray-100);
  border-radius: 12px;
}
</style>
