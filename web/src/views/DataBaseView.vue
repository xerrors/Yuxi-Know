<template>
  <div class="database-container layout-container">
    <PageHeader
      title="知识库"
      :active-key="knowledgeActiveView"
      :tabs="knowledgeViewItems"
      :loading="dbState.listLoading"
      :show-border="true"
      aria-label="知识库视图切换"
    />

    <PageShoulder v-model:search="searchQuery" search-placeholder="搜索知识库...">
      <template #filters>
        <a-select
          v-model:value="typeFilter"
          style="width: 120px"
          placeholder="全部类型"
          allow-clear
        >
          <a-select-option :value="null">全部类型</a-select-option>
          <a-select-option v-for="t in kbTypes" :key="t" :value="t">
            {{ getKbTypeLabel(t) }}
          </a-select-option>
        </a-select>
      </template>
      <template #actions>
        <a-button type="primary" @click="state.openNewDatabaseModel = true">
          <PlusOutlined /> 新建知识库
        </a-button>
      </template>
    </PageShoulder>

    <a-modal
      :open="state.openNewDatabaseModel"
      title="新建知识库"
      :confirm-loading="dbState.creating"
      @ok="handleCreateDatabase"
      @cancel="cancelCreateDatabase"
      class="new-database-modal"
      width="800px"
      destroyOnClose
    >
      <!-- 知识库类型选择 -->
      <h3>知识库类型<span style="color: var(--color-error-500)">*</span></h3>
      <div class="kb-type-cards">
        <div
          v-for="(typeInfo, typeKey) in orderedKbTypes"
          :key="typeKey"
          class="kb-type-card"
          :class="{ active: newDatabase.kb_type === typeKey }"
          :data-type="typeKey"
          @click="handleKbTypeChange(typeKey)"
        >
          <div class="card-header">
            <component :is="getKbTypeIcon(typeKey)" class="type-icon" />
            <span class="type-title">{{ getKbTypeLabel(typeKey) }}</span>
          </div>
          <div class="card-description">{{ typeInfo.description }}</div>
        </div>
      </div>

      <!-- 类型说明 -->
      <!-- <div class="kb-type-guide" v-if="newDatabase.kb_type">
        <a-alert
          :message="getKbTypeDescription(newDatabase.kb_type)"
          :type="getKbTypeAlertType(newDatabase.kb_type)"
          show-icon
          style="margin: 12px 0;"
        />
      </div> -->

      <h3>知识库名称<span style="color: var(--color-error-500)">*</span></h3>
      <a-input v-model:value="newDatabase.name" placeholder="新建知识库名称" size="large" />

      <template v-if="newDatabase.kb_type !== 'dify'">
        <h3>嵌入模型</h3>
        <EmbeddingModelSelector
          v-model:value="newDatabase.embed_model_name"
          style="width: 100%"
          size="large"
          placeholder="请选择嵌入模型"
        />
      </template>

      <div v-if="newDatabase.kb_type !== 'dify'" class="chunk-preset-title-row">
        <h3 style="margin: 0">分块策略</h3>
        <a-tooltip :title="selectedPresetDescription">
          <QuestionCircleOutlined class="chunk-preset-help-icon" />
        </a-tooltip>
      </div>
      <a-select
        v-if="newDatabase.kb_type !== 'dify'"
        v-model:value="newDatabase.chunk_preset_id"
        :options="chunkPresetOptions"
        style="width: 100%"
        size="large"
      />

      <!-- 仅对 LightRAG 提供语言选择和LLM选择 -->
      <div v-if="newDatabase.kb_type === 'lightrag'">
        <h3 style="margin-top: 20px">语言</h3>
        <a-select
          v-model:value="newDatabase.language"
          :options="languageOptions"
          style="width: 100%"
          size="large"
          :dropdown-match-select-width="false"
        />

        <h3 style="margin-top: 20px">语言模型 (LLM)</h3>
        <p style="color: var(--gray-700); font-size: 14px">可以在设置中配置语言模型</p>
        <ModelSelectorComponent
          :model_spec="llmModelSpec"
          placeholder="请选择模型"
          @select-model="handleLLMSelect"
          size="large"
          style="width: 100%; height: 60px"
        />
      </div>

      <div v-if="newDatabase.kb_type === 'dify'">
        <h3 style="margin-top: 20px">Dify API URL</h3>
        <a-input
          v-model:value="newDatabase.dify_api_url"
          placeholder="例如: https://api.dify.ai/v1"
          size="large"
        />

        <h3 style="margin-top: 20px">Dify Token</h3>
        <a-input-password
          v-model:value="newDatabase.dify_token"
          placeholder="请输入 Dify API Token"
          size="large"
        />

        <h3 style="margin-top: 20px">Dataset ID</h3>
        <a-input
          v-model:value="newDatabase.dify_dataset_id"
          placeholder="请输入 Dify dataset_id"
          size="large"
        />
      </div>

      <h3 style="margin-top: 20px">知识库描述</h3>
      <p style="color: var(--gray-700); font-size: 14px">
        在智能体流程中，这里的描述会作为工具的描述。智能体会根据知识库的标题和描述来选择合适的工具。所以这里描述的越详细，智能体越容易选择到合适的工具。
      </p>
      <AiTextarea
        v-model="newDatabase.description"
        :name="newDatabase.name"
        placeholder="新建知识库描述"
        :auto-size="{ minRows: 3, maxRows: 10 }"
      />

      <!-- 隐私设置（暂时隐藏）
      <h3 style="margin-top: 20px">隐私设置</h3>
      <div class="privacy-config">
        <a-switch
          v-model:checked="newDatabase.is_private"
          checked-children="私有"
          un-checked-children="公开"
          size="default"
        />
        <span style="margin-left: 12px">设置为私有知识库</span>
        <a-tooltip
          title="当前未使用此属性。在部分智能体的设计中，可以根据隐私标志来决定启用什么模型和策略。例如，对于私有知识库，可以选择更严格的数据处理和访问控制策略，以保护敏感信息的安全性和隐私性。"
        >
          <InfoCircleOutlined style="margin-left: 8px; color: var(--gray-500); cursor: help" />
        </a-tooltip>
      </div>
      -->

      <!-- 共享配置 -->
      <h3>共享设置</h3>
      <ShareConfigForm v-model="shareConfig" :auto-select-user-dept="true" />
      <template #footer>
        <a-button key="back" @click="cancelCreateDatabase">取消</a-button>
        <a-button
          key="submit"
          type="primary"
          :loading="dbState.creating"
          @click="handleCreateDatabase"
          >创建</a-button
        >
      </template>
    </a-modal>

    <!-- 加载状态 -->
    <div v-if="dbState.listLoading" class="loading-container">
      <a-spin size="large" />
      <p>正在加载知识库...</p>
    </div>

    <!-- 空状态显示 -->
    <div v-else-if="!databases || databases.length === 0" class="empty-state">
      <h3 class="empty-title">暂无知识库</h3>
      <p class="empty-description">创建您的第一个知识库，开始管理文档和知识</p>
      <a-button type="primary" size="large" @click="state.openNewDatabaseModel = true">
        <template #icon>
          <PlusOutlined />
        </template>
        创建知识库
      </a-button>
    </div>

    <!-- 数据库列表 -->
    <ExtensionCardGrid v-else>
      <InfoCard
        v-for="database in filteredDatabases"
        :key="database.db_id"
        :title="database.name"
        :subtitle="cardSubtitle(database)"
        :description="database.description || '暂无描述'"
        :tags="cardTags(database)"
        @click="navigateToDatabase(database.db_id)"
      >
        <template #icon>
          <component :is="getKbTypeIcon(database.kb_type || 'lightrag')" :size="20" />
        </template>
        <template #status>
          <LockOutlined v-if="database.metadata?.is_private" title="私有知识库" />
        </template>
      </InfoCard>
    </ExtensionCardGrid>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { useDatabaseStore } from '@/stores/database'
import { LockOutlined, PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { typeApi } from '@/apis/knowledge_api'
import PageHeader from '@/components/shared/PageHeader.vue'
import PageShoulder from '@/components/shared/PageShoulder.vue'
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue'
import EmbeddingModelSelector from '@/components/EmbeddingModelSelector.vue'
import ShareConfigForm from '@/components/ShareConfigForm.vue'
import ExtensionCardGrid from '@/components/extensions/ExtensionCardGrid.vue'
import InfoCard from '@/components/shared/InfoCard.vue'
import dayjs, { parseToShanghai } from '@/utils/time'
import AiTextarea from '@/components/AiTextarea.vue'
import { getKbTypeLabel, getKbTypeIcon, getKbTypeColor } from '@/utils/kb_utils'
import { CHUNK_PRESET_OPTIONS, getChunkPresetDescription } from '@/utils/chunk_presets'

const route = useRoute()
const router = useRouter()
const configStore = useConfigStore()
const databaseStore = useDatabaseStore()

// 使用 store 的状态
const { databases, state: dbState } = storeToRefs(databaseStore)

const knowledgeActiveView = 'documents'
const knowledgeViewItems = [
  { key: 'documents', label: '文档知识库', path: '/database' },
  { key: 'graph', label: '知识图谱', path: '/graph' }
]

const kbTypes = ['lightrag', 'milvus', 'dify']
const searchQuery = ref('')
const typeFilter = ref(null)

const filteredDatabases = computed(() => {
  let list = databases.value
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(
      (db) =>
        db.name.toLowerCase().includes(q) ||
        (db.description && db.description.toLowerCase().includes(q))
    )
  }
  if (typeFilter.value) {
    list = list.filter((db) => (db.kb_type || 'lightrag') === typeFilter.value)
  }
  return list
})

const state = reactive({
  openNewDatabaseModel: false
})

// 共享配置状态（用于提交数据）
const shareConfig = ref({
  is_shared: true,
  accessible_department_ids: []
})

// 语言选项（值使用英文，以保证后端/LightRAG 兼容；标签为中英文方便理解）
const languageOptions = [
  { label: '中文 Chinese', value: 'Chinese' },
  { label: '英语 English', value: 'English' },
  { label: '日语 Japanese', value: 'Japanese' },
  { label: '韩语 Korean', value: 'Korean' },
  { label: '德语 German', value: 'German' },
  { label: '法语 French', value: 'French' },
  { label: '西班牙语 Spanish', value: 'Spanish' },
  { label: '葡萄牙语 Portuguese', value: 'Portuguese' },
  { label: '俄语 Russian', value: 'Russian' },
  { label: '阿拉伯语 Arabic', value: 'Arabic' },
  { label: '印地语 Hindi', value: 'Hindi' }
]

const chunkPresetOptions = CHUNK_PRESET_OPTIONS.map(({ label, value }) => ({ label, value }))

const createEmptyDatabaseForm = () => ({
  name: '',
  description: '',
  embed_model_name: configStore.config?.embed_model,
  kb_type: 'milvus',
  is_private: false,
  storage: '',
  chunk_preset_id: 'general',
  language: 'Chinese',
  llm_info: {
    provider: '',
    model_name: ''
  },
  dify_api_url: '',
  dify_token: '',
  dify_dataset_id: ''
})

const newDatabase = reactive(createEmptyDatabaseForm())

const selectedPresetDescription = computed(() =>
  getChunkPresetDescription(newDatabase.chunk_preset_id)
)

const llmModelSpec = computed(() => {
  const provider = newDatabase.llm_info?.provider || ''
  const modelName = newDatabase.llm_info?.model_name || ''
  if (provider && modelName) {
    return `${provider}/${modelName}`
  }
  return ''
})

// 支持的知识库类型
const supportedKbTypes = ref({})

// 有序的知识库类型
const orderedKbTypes = computed(() => supportedKbTypes.value)

// 加载支持的知识库类型
const loadSupportedKbTypes = async () => {
  try {
    const data = await typeApi.getKnowledgeBaseTypes()
    supportedKbTypes.value = data.kb_types
    console.log('支持的知识库类型:', supportedKbTypes.value)
  } catch (error) {
    console.error('加载知识库类型失败:', error)
    // 如果加载失败，设置默认类型
    supportedKbTypes.value = {
      lightrag: {
        description: '基于图检索的知识库，支持实体关系构建和复杂查询',
        class_name: 'LightRagKB'
      }
    }
  }
}

// 重排序模型信息现在直接从 configStore.config.reranker_names 获取，无需单独加载

const resetNewDatabase = () => {
  Object.assign(newDatabase, createEmptyDatabaseForm())
  // 重置共享配置
  shareConfig.value = {
    is_shared: true,
    accessible_department_ids: []
  }
}

const cancelCreateDatabase = () => {
  state.openNewDatabaseModel = false
  resetNewDatabase()
}

// 格式化创建时间
const formatCreatedTime = (createdAt) => {
  if (!createdAt) return ''
  const parsed = parseToShanghai(createdAt)
  if (!parsed) return ''

  const today = dayjs().startOf('day')
  const createdDay = parsed.startOf('day')
  const diffInDays = today.diff(createdDay, 'day')

  if (diffInDays === 0) {
    return '今天创建'
  }
  if (diffInDays === 1) {
    return '昨天创建'
  }
  if (diffInDays < 7) {
    return `${diffInDays} 天前创建`
  }
  if (diffInDays < 30) {
    const weeks = Math.floor(diffInDays / 7)
    return `${weeks} 周前创建`
  }
  if (diffInDays < 365) {
    const months = Math.floor(diffInDays / 30)
    return `${months} 个月前创建`
  }
  const years = Math.floor(diffInDays / 365)
  return `${years} 年前创建`
}

// 处理知识库类型改变
const handleKbTypeChange = (type) => {
  console.log('知识库类型改变:', type)
  resetNewDatabase()
  newDatabase.kb_type = type
}

// 处理LLM选择
const handleLLMSelect = (spec) => {
  console.log('LLM选择:', spec)
  if (typeof spec !== 'string' || !spec) return

  const index = spec.indexOf('/')
  const provider = index !== -1 ? spec.slice(0, index) : ''
  const modelName = index !== -1 ? spec.slice(index + 1) : ''

  newDatabase.llm_info.provider = provider
  newDatabase.llm_info.model_name = modelName
}

// 构建请求数据（只负责表单数据转换）
const buildRequestData = () => {
  const requestData = {
    database_name: newDatabase.name.trim(),
    description: newDatabase.description?.trim() || '',
    kb_type: newDatabase.kb_type,
    additional_params: {}
  }

  if (newDatabase.kb_type !== 'dify') {
    requestData.embed_model_name = newDatabase.embed_model_name || configStore.config.embed_model
    requestData.additional_params.is_private = newDatabase.is_private || false
    requestData.additional_params.chunk_preset_id = newDatabase.chunk_preset_id || 'general'
  }

  // 添加共享配置
  requestData.share_config = {
    is_shared: shareConfig.value.is_shared,
    accessible_departments: shareConfig.value.is_shared
      ? []
      : shareConfig.value.accessible_department_ids || []
  }

  // 根据类型添加特定配置
  if (['milvus'].includes(newDatabase.kb_type)) {
    if (newDatabase.storage) {
      requestData.additional_params.storage = newDatabase.storage
    }
  }

  if (newDatabase.kb_type === 'lightrag') {
    requestData.additional_params.language = newDatabase.language || 'English'
    if (newDatabase.llm_info.provider && newDatabase.llm_info.model_name) {
      requestData.llm_info = {
        provider: newDatabase.llm_info.provider,
        model_name: newDatabase.llm_info.model_name
      }
    }
  }

  if (newDatabase.kb_type === 'dify') {
    requestData.additional_params.dify_api_url = (newDatabase.dify_api_url || '').trim()
    requestData.additional_params.dify_token = (newDatabase.dify_token || '').trim()
    requestData.additional_params.dify_dataset_id = (newDatabase.dify_dataset_id || '').trim()
  }

  return requestData
}

// 创建按钮处理
const handleCreateDatabase = async () => {
  if (newDatabase.kb_type === 'dify') {
    if (
      !newDatabase.dify_api_url?.trim() ||
      !newDatabase.dify_token?.trim() ||
      !newDatabase.dify_dataset_id?.trim()
    ) {
      message.error('请完整填写 Dify API URL、Token 和 Dataset ID')
      return
    }
    if (!newDatabase.dify_api_url.trim().endsWith('/v1')) {
      message.error('Dify API URL 必须以 /v1 结尾')
      return
    }
  }

  const requestData = buildRequestData()
  try {
    await databaseStore.createDatabase(requestData)
    resetNewDatabase()
    state.openNewDatabaseModel = false
  } catch {
    // 错误已在 store 中处理
  }
}

const cardSubtitle = (database) => {
  const parts = [`${database.row_count || 0} 文件`]
  if (database.created_at) {
    parts.push(formatCreatedTime(database.created_at))
  }
  return parts.join(' · ')
}

const cardTags = (database) => {
  const tags = [
    {
      name: getKbTypeLabel(database.kb_type || 'lightrag'),
      color: getKbTypeColor(database.kb_type || 'lightrag')
    }
  ]
  if (database.embed_info?.name) {
    tags.push({
      name: database.embed_info.name.split('/').slice(-1)[0],
      color: 'blue'
    })
  }
  return tags
}

const navigateToDatabase = (databaseId) => {
  router.push({ path: `/database/${databaseId}` })
}

watch(
  () => route.path,
  (newPath) => {
    if (newPath === '/database') {
      databaseStore.loadDatabases()
    }
  }
)

onMounted(() => {
  loadSupportedKbTypes()
  databaseStore.loadDatabases()
})
</script>

<style lang="less" scoped>
.new-database-modal {
  .chunk-preset-title-row {
    margin-top: 20px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .chunk-preset-help-icon {
    color: var(--gray-500);
    cursor: help;
    font-size: 14px;
  }

  .kb-type-guide {
    margin: 12px 0;
  }

  .privacy-config {
    display: flex;
    align-items: center;
    margin-bottom: 12px;
  }

  .kb-type-cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin: 16px 0;

    @media (max-width: 768px) {
      grid-template-columns: 1fr;
      gap: 12px;
    }

    .kb-type-card {
      border: 2px solid var(--gray-150);
      border-radius: 12px;
      padding: 16px;
      cursor: pointer;
      transition: all 0.3s ease;
      background: var(--gray-0);
      position: relative;
      overflow: hidden;

      &:hover {
        border-color: var(--main-color);
      }

      &.active {
        border-color: var(--main-color);
        background: var(--main-10);
        .type-icon {
          color: var(--main-color);
        }
      }

      .card-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 12px;

        .type-icon {
          width: 24px;
          height: 24px;
          color: var(--main-color);
          flex-shrink: 0;
        }

        .type-title {
          font-size: 16px;
          font-weight: 600;
          color: var(--gray-800);
        }
      }

      .card-description {
        font-size: 13px;
        color: var(--gray-600);
        line-height: 1.5;
        margin-bottom: 0;
        // min-height: 40px;
      }

      .deprecated-badge {
        background: var(--color-error-100);
        color: var(--color-error-600);
        font-size: 10px;
        font-weight: 600;
        padding: 2px 6px;
        border-radius: 4px;
        margin-left: auto;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        cursor: help;
        transition: all 0.2s ease;

        &:hover {
          background: var(--color-error-200);
          color: var(--color-error-700);
        }
      }
    }
  }

  .chunk-config {
    margin-top: 16px;
    padding: 12px 16px;
    background-color: var(--gray-25);
    border-radius: 6px;
    border: 1px solid var(--gray-150);

    h3 {
      margin-top: 0;
      margin-bottom: 12px;
      color: var(--gray-800);
    }

    .chunk-params {
      display: flex;
      flex-direction: column;
      gap: 12px;

      .param-row {
        display: flex;
        align-items: center;
        gap: 12px;

        label {
          min-width: 80px;
          font-weight: 500;
          color: var(--gray-700);
        }

        .param-hint {
          font-size: 12px;
          color: var(--gray-500);
          margin-left: 8px;
        }
      }
    }
  }
}

.database-container {
  padding: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 20px;
  text-align: center;

  .empty-title {
    font-size: 20px;
    font-weight: 600;
    color: var(--gray-900);
    margin: 0 0 12px 0;
    letter-spacing: -0.02em;
  }

  .empty-description {
    font-size: 14px;
    color: var(--gray-600);
    margin: 0 0 32px 0;
    line-height: 1.5;
    max-width: 320px;
  }

  .ant-btn {
    height: 44px;
    padding: 0 24px;
    font-size: 15px;
    font-weight: 500;
  }
}

.loading-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 300px;
  gap: 16px;
}

.new-database-modal {
  h3 {
    margin-top: 10px;
  }
}
</style>
