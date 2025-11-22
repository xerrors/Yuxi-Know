<template>
  <div class="database-container layout-container">
    <HeaderComponent title="文档知识库" :loading="state.loading">
      <template #actions>
        <a-button type="primary" @click="state.openNewDatabaseModel=true">
          新建知识库
        </a-button>
      </template>
    </HeaderComponent>

    <a-modal :open="state.openNewDatabaseModel" title="新建知识库" @ok="createDatabase" @cancel="cancelCreateDatabase" class="new-database-modal" width="800px">

      <!-- 知识库类型选择 -->
      <h3>知识库类型<span style="color: var(--error-color)">*</span></h3>
      <div class="kb-type-cards">
        <div
          v-for="(typeInfo, typeKey) in supportedKbTypes"
          :key="typeKey"
          class="kb-type-card"
          :class="{ active: newDatabase.kb_type === typeKey }"
          @click="handleKbTypeChange(typeKey)"
        >
          <div class="card-header">
            <component :is="getKbTypeIcon(typeKey)" class="type-icon" />
            <span class="type-title">{{ getKbTypeLabel(typeKey) }}</span>
          </div>
          <div class="card-description">{{ typeInfo.description }}</div>
          <div class="card-features">
            <span class="feature-tag">{{ getKbTypeFeature(typeKey) }}</span>
          </div>
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

      <h3>知识库名称<span style="color: var(--error-color)">*</span></h3>
      <a-input v-model:value="newDatabase.name" placeholder="新建知识库名称" size="large" />

      <h3>嵌入模型</h3>
      <a-select v-model:value="newDatabase.embed_model_name" :options="embedModelOptions" style="width: 100%;" size="large" />

      <!-- 仅对 LightRAG 提供语言选择和LLM选择 -->
      <div v-if="newDatabase.kb_type === 'lightrag'">
        <h3 style="margin-top: 20px;">语言</h3>
        <a-select
          v-model:value="newDatabase.language"
          :options="languageOptions"
          style="width: 100%;"
          size="large"
          :dropdown-match-select-width="false"
        />

        <h3 style="margin-top: 20px;">语言模型 (LLM)</h3>
        <p style="color: var(--gray-700); font-size: 14px;">可以在设置中配置语言模型</p>
        <ModelSelectorComponent
          :model_spec="llmModelSpec"
          placeholder="请选择模型"
          @select-model="handleLLMSelect"
          size="large"
          style="width: 100%; height: 60px;"
        />
      </div>

      <h3 style="margin-top: 20px;">知识库描述</h3>
      <p style="color: var(--gray-700); font-size: 14px;">在智能体流程中，这里的描述会作为工具的描述。智能体会根据知识库的标题和描述来选择合适的工具。所以这里描述的越详细，智能体越容易选择到合适的工具。</p>
      <a-textarea
        v-model:value="newDatabase.description"
        placeholder="新建知识库描述"
        :auto-size="{ minRows: 5, maxRows: 10 }"
      />

      <h3 style="margin-top: 20px;">隐私设置</h3>
      <div class="privacy-config">
        <a-switch
          v-model:checked="newDatabase.is_private"
          checked-children="私有"
          un-checked-children="公开"
          size="default"
        />
        <span style="margin-left: 12px;">设置为私有知识库</span>
        <a-tooltip title="在部分智能体的设计中，可以根据隐私标志来决定启用什么模型和策略。例如，对于私有知识库，可以选择更严格的数据处理和访问控制策略，以保护敏感信息的安全性和隐私性。">
          <InfoCircleOutlined style="margin-left: 8px; color: var(--gray-500); cursor: help;" />
        </a-tooltip>
      </div>

      <div
        v-if="['chroma', 'milvus'].includes(newDatabase.kb_type)"
        class="reranker-config"
      >
        <div class="reranker-row">
          <div class="reranker-title">
            <span>启用重排序</span>
            <a-tooltip title="向量检索后使用交叉编码模型对候选文档重新排序，提升召回质量。">
              <QuestionCircleOutlined class="hint-icon" />
            </a-tooltip>
          </div>
          <a-switch
            v-model:checked="newDatabase.reranker.enabled"
            :disabled="rerankerOptions.length === 0"
          />
        </div>

        <transition name="fade">
          <div v-if="newDatabase.reranker.enabled" class="reranker-form">
            <div class="form-field">
              <label>重排序模型</label>
              <a-select
                v-model:value="newDatabase.reranker.model"
                :options="rerankerOptions"
                placeholder="选择重排序模型"
                :disabled="rerankerOptions.length === 0"
              />
              <p class="field-hint" v-if="rerankerOptions.length === 0">
                暂无可用模型，请在系统配置中添加。
              </p>
            </div>

            <div class="form-grid">
              <div class="form-field">
                <label>召回数量</label>
                <a-input-number
                  v-model:value="newDatabase.reranker.recall_top_k"
                  :min="10"
                  :max="200"
                  :step="5"
                  style="width: 100%;"
                />
                <p class="field-hint">向量检索阶段保留的候选数量</p>
              </div>
              <div class="form-field">
                <label>最终返回数</label>
                <a-input-number
                  v-model:value="newDatabase.reranker.final_top_k"
                  :min="1"
                  :max="100"
                  style="width: 100%;"
                />
                <p class="field-hint">重排序后返回给前端的文档数量</p>
              </div>
            </div>
          </div>
        </transition>
      </div>
      <template #footer>
        <a-button key="back" @click="cancelCreateDatabase">取消</a-button>
        <a-button key="submit" type="primary" :loading="state.creating" @click="createDatabase">创建</a-button>
      </template>
    </a-modal>

    <!-- 加载状态 -->
    <div v-if="state.loading" class="loading-container">
      <a-spin size="large" />
      <p>正在加载知识库...</p>
    </div>

    <!-- 数据库列表 -->
    <div v-else class="databases">
      <div
        v-for="database in databases"
        :key="database.db_id"
        class="database dbcard"
        @click="navigateToDatabase(database.db_id)">
        <!-- 私有知识库锁定图标 -->
        <LockOutlined
          v-if="database.metadata?.is_private"
          class="private-lock-icon"
          title="私有知识库"
        />
        <div class="top">
          <div class="icon">
            <component :is="getKbTypeIcon(database.kb_type || 'lightrag')" />
          </div>
          <div class="info">
            <h3>{{ database.name }}</h3>
            <p>
              <span>{{ database.files ? Object.keys(database.files).length : 0 }} 文件</span>
              <span class="created-time-inline" v-if="database.created_at">
                • {{ formatCreatedTime(database.created_at) }}
              </span>
            </p>
          </div>
        </div>
        <!-- <a-tooltip :title="database.description || '暂无描述'">
          <p class="description">{{ database.description || '暂无描述' }}</p>
        </a-tooltip> -->
        <p class="description">{{ database.description || '暂无描述' }}</p>
        <div class="tags">
          <a-tag color="blue" v-if="database.embed_info?.name">{{ database.embed_info.name }}</a-tag>
          <!-- <a-tag color="green" v-if="database.embed_info?.dimension">{{ database.embed_info.dimension }}</a-tag> -->
          <a-tag
            :color="getKbTypeColor(database.kb_type || 'lightrag')"
            class="kb-type-tag"
            size="small"
          >
            {{ getKbTypeLabel(database.kb_type || 'lightrag') }}
          </a-tag>
          </div>

        <!-- <button @click="deleteDatabase(database.collection_name)">删除</button> -->
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router';
import { useConfigStore } from '@/stores/config';
import { message } from 'ant-design-vue'
import { Database, Zap, FileDigit,  Waypoints, Building2 } from 'lucide-vue-next';
import { LockOutlined, InfoCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue';
import { databaseApi, typeApi } from '@/apis/knowledge_api';
import HeaderComponent from '@/components/HeaderComponent.vue';
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue';
import dayjs, { parseToShanghai } from '@/utils/time';

const route = useRoute()
const router = useRouter()
const databases = ref([])
const configStore = useConfigStore()

const state = reactive({
  loading: false,
  creating: false,
  openNewDatabaseModel: false,
})

const embedModelOptions = computed(() => {
  return Object.keys(configStore.config?.embed_model_names || {}).map(key => ({
    label: `${key} (${configStore.config?.embed_model_names[key]?.dimension})`,
    value: key,
  }))
})

// 语言选项（值使用英文，以保证后端/LightRAG 兼容；标签为中英文方便理解）
const languageOptions = [
  { label: '英语 English', value: 'English' },
  { label: '中文 Chinese', value: 'Chinese' },
  { label: '日语 Japanese', value: 'Japanese' },
  { label: '韩语 Korean', value: 'Korean' },
  { label: '德语 German', value: 'German' },
  { label: '法语 French', value: 'French' },
  { label: '西班牙语 Spanish', value: 'Spanish' },
  { label: '葡萄牙语 Portuguese', value: 'Portuguese' },
  { label: '俄语 Russian', value: 'Russian' },
  { label: '阿拉伯语 Arabic', value: 'Arabic' },
  { label: '印地语 Hindi', value: 'Hindi' },
]

const createEmptyDatabaseForm = () => ({
  name: '',
  description: '',
  embed_model_name: configStore.config?.embed_model,
  kb_type: 'chroma',
  is_private: false,
  storage: '',
  language: 'English',
  llm_info: {
    provider: '',
    model_name: ''
  },
  reranker: {
    enabled: false,
    model: '',
    recall_top_k: 50,
    final_top_k: 10,
  }
})

const newDatabase = reactive(createEmptyDatabaseForm())

const rerankerOptions = computed(() =>
  Object.entries(configStore?.config?.reranker_names || {}).map(([value, info]) => ({
    label: info?.name || value,
    value
  }))
)

const isVectorKb = computed(() => ['chroma', 'milvus'].includes(newDatabase.kb_type))

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
        description: "基于图检索的知识库，支持实体关系构建和复杂查询",
        class_name: "LightRagKB"
      }
    }
  }
}

// 重排序模型信息现在直接从 configStore.config.reranker_names 获取，无需单独加载

const loadDatabases = () => {
  state.loading = true
  // loadGraph()
  databaseApi.getDatabases()
    .then(data => {
      console.log(data)
      // 按照创建时间排序，最新的在前面
      databases.value = data.databases.sort((a, b) => {
        const timeA = parseToShanghai(a.created_at)
        const timeB = parseToShanghai(b.created_at)
        if (!timeA && !timeB) return 0
        if (!timeA) return 1
        if (!timeB) return -1
        return timeB.valueOf() - timeA.valueOf() // 降序排列，最新的在前面
      })
      state.loading = false
    })
    .catch(error => {
      console.error('加载数据库列表失败:', error);
      if (error.message.includes('权限')) {
        message.error('需要管理员权限访问知识库')
      }
      state.loading = false
    })
}

const resetNewDatabase = () => {
  Object.assign(newDatabase, createEmptyDatabaseForm())
}

const cancelCreateDatabase = () => {
  state.openNewDatabaseModel = false
}

// 知识库类型相关工具方法
const getKbTypeLabel = (type) => {
  const labels = {
    lightrag: 'LightRAG',
    chroma: 'Chroma',
    milvus: 'Milvus'
  }
  return labels[type] || type
}

const getKbTypeIcon = (type) => {
  const icons = {
    lightrag: Waypoints,
    chroma: FileDigit,
    milvus: Building2
  }
  return icons[type] || Database
}

// const getKbTypeDescription = (type) => {
//   const descriptions = {
//     lightrag: '🔥 图结构索引 • 智能查询 • 关系挖掘 • 复杂推理',
//     chroma: '⚡ 轻量向量 • 快速开发 • 本地部署 • 简单易用',
//     milvus: '🚀 生产级 • 高性能 • 分布式 • 企业级部署'
//   }
//   return descriptions[type] || ''
// }

const getKbTypeAlertType = (type) => {
  const types = {
    lightrag: 'info',
    chroma: 'success',
    milvus: 'warning'
  }
  return types[type] || 'info'
}

const getKbTypeColor = (type) => {
  const colors = {
    lightrag: 'purple',
    chroma: 'orange',
    milvus: 'red'
  }
  return colors[type] || 'blue'
}

const getKbTypeFeature = (type) => {
  const features = {
    lightrag: '图结构索引',
    chroma: '轻量向量',
    milvus: '生产级部署'
  }
  return features[type] || ''
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
  if (!['chroma', 'milvus'].includes(type)) {
    newDatabase.reranker.enabled = false
  }
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

const createDatabase = () => {
  if (!newDatabase.name?.trim()) {
    message.error('数据库名称不能为空')
    return
  }

  if (!newDatabase.kb_type) {
    message.error('请选择知识库类型')
    return
  }

  state.creating = true

  const requestData = {
    database_name: newDatabase.name.trim(),
    description: newDatabase.description?.trim() || '',
    embed_model_name: newDatabase.embed_model_name || configStore.config.embed_model,
    kb_type: newDatabase.kb_type,
    additional_params: {
      is_private: newDatabase.is_private || false
    }
  }

  // 添加类型特有的配置
  if (newDatabase.kb_type === 'chroma' || newDatabase.kb_type === 'milvus') {
    if (newDatabase.storage) {
      requestData.additional_params.storage = newDatabase.storage
    }

    if (newDatabase.reranker.enabled) {
      if (!newDatabase.reranker.model) {
        message.error('请选择重排序模型')
        state.creating = false
        return
      }
      requestData.additional_params.reranker_config = {
        enabled: true,
        model: newDatabase.reranker.model,
        recall_top_k: Number(newDatabase.reranker.recall_top_k) || 50,
        final_top_k: Number(newDatabase.reranker.final_top_k) || 10,
      }
    }
  }

  if (newDatabase.kb_type === 'lightrag') {
    requestData.additional_params.language = newDatabase.language || 'English'
    // 添加LLM信息到请求数据
    if (newDatabase.llm_info.provider && newDatabase.llm_info.model_name) {
      requestData.llm_info = {
        provider: newDatabase.llm_info.provider,
        model_name: newDatabase.llm_info.model_name
      }
    }
  }

  databaseApi.createDatabase(requestData)
    .then(data => {
      console.log('创建成功:', data)
      loadDatabases()
      resetNewDatabase()
      message.success('创建成功')
    })
    .catch(error => {
      console.error('创建数据库失败:', error)
      message.error(error.message || '创建失败')
    })
    .finally(() => {
      state.creating = false
      state.openNewDatabaseModel = false
    })
}

const navigateToDatabase = (databaseId) => {
  router.push({ path: `/database/${databaseId}` });
};

watch(() => newDatabase.reranker.enabled, (enabled) => {
  if (
    enabled &&
    !newDatabase.reranker.model &&
    rerankerOptions.value.length > 0
  ) {
    newDatabase.reranker.model = rerankerOptions.value[0].value
  }
})

watch(rerankerOptions, (options) => {
  if (!newDatabase.reranker.enabled || options.length === 0) {
    return
  }
  const exists = options.some(option => option.value === newDatabase.reranker.model)
  if (!exists) {
    newDatabase.reranker.model = options[0].value
  }
})

watch(isVectorKb, (isVector) => {
  if (!isVector) {
    newDatabase.reranker.enabled = false
  }
})

watch(
  () => newDatabase.reranker.final_top_k,
  (value) => {
    if (!newDatabase.reranker.enabled) return
    if (value > newDatabase.reranker.recall_top_k) {
      newDatabase.reranker.recall_top_k = value
    }
  }
)

watch(() => route.path, (newPath, oldPath) => {
  if (newPath === '/database') {
    loadDatabases();
  }
});

onMounted(() => {
  loadSupportedKbTypes()
  loadDatabases()
  // 重排序模型信息现在直接从 configStore 获取，无需单独加载
})

</script>

<style lang="less" scoped>
.new-database-modal {
  .kb-type-guide {
    margin: 12px 0;
  }

  .privacy-config {
    display: flex;
    align-items: center;
    margin-bottom: 12px;
  }

  .reranker-config {
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: 16px;
    margin-top: 16px;
    background: var(--gray-25);

    .reranker-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;

      .reranker-title {
        display: flex;
        align-items: center;
        gap: 6px;
        font-weight: 500;
        color: var(--gray-800);
      }

      .hint-icon {
        color: var(--gray-500);
        cursor: help;
      }
    }

    .reranker-form {
      display: flex;
      flex-direction: column;
      gap: 16px;

      .form-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;

        @media (max-width: 768px) {
          grid-template-columns: 1fr;
        }
      }

      .form-field {
        label {
          display: block;
          font-size: 14px;
          margin-bottom: 8px;
          color: var(--gray-700);
        }

        .field-hint {
          margin-top: 6px;
          font-size: 12px;
          color: var(--gray-500);
        }
      }
    }
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
      padding: 20px;
      cursor: pointer;
      transition: all 0.3s ease;
      background: var(--gray-0);
      position: relative;
      overflow: hidden;

      &:hover {
        border-color: var(--main-color);
      }

      // 为不同知识库类型设置不同的悬停颜色
      &:nth-child(1):hover {
        border-color: var(--chart-secondary-light);
      }

      &:nth-child(2):hover {
        border-color: var(--chart-warning-light);
      }

      &:nth-child(3):hover {
        border-color: var(--chart-error-light);
      }

      &.active {
        border-color: var(--main-color);
        background: rgba(24, 144, 255, 0.05);

        .type-icon {
          color: var(--main-color);
        }

        .feature-tag {
          background: rgba(24, 144, 255, 0.1);
          color: var(--main-color);
        }
      }

      // 为不同知识库类型设置不同的主题色
      &:nth-child(1) {
        &.active {
          border-color: var(--chart-secondary-light);
          background: rgba(114, 46, 209, 0.05);

          .type-icon {
            color: var(--chart-secondary);
          }

          .feature-tag {
            background: rgba(114, 46, 209, 0.1);
            color: var(--chart-secondary);
          }
        }
      }

      &:nth-child(2) {
        &.active {
          border-color: var(--chart-warning-light);
          background: rgba(250, 140, 22, 0.05);

          .type-icon {
            color: var(--chart-warning);
          }

          .feature-tag {
            background: rgba(250, 140, 22, 0.1);
            color: var(--chart-warning);
          }
        }
      }

      &:nth-child(3) {
        &.active {
          border-color: var(--chart-error-light);
          background: rgba(245, 34, 45, 0.05);

          .type-icon {
            color: var(--chart-error);
          }

          .feature-tag {
            background: rgba(245, 34, 45, 0.1);
            color: var(--chart-error);
          }
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
        margin-bottom: 12px;
        // min-height: 40px;
      }

      .card-features {
        .feature-tag {
          display: inline-block;
          padding: 4px 8px;
          background: rgba(24, 144, 255, 0.08);
          color: var(--main-color);
          border-radius: 6px;
          font-size: 12px;
          font-weight: 500;
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
  .databases {
    .database {
      .top {
        .info {
          h3 {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;

            .kb-type-tag {
              margin-left: auto;
            }
          }
        }
      }
    }
  }
}
.database-actions, .document-actions {
  margin-bottom: 20px;
}
.databases {
  padding: 20px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.database, .graphbase {
  background: linear-gradient(145deg, var(--gray-0) 0%, var(--gray-10) 100%);
  box-shadow: 0px 1px 2px 0px var(--shadow-2);
  border: 1px solid var(--gray-100);
  transition: none;
  position: relative;
}

.dbcard, .database {
  width: 100%;
  padding: 24px;
  border-radius: 16px;
  height: 180px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  position: relative; // 为绝对定位的锁定图标提供参考
  overflow: hidden;

  .private-lock-icon {
    position: absolute;
    top: 20px;
    right: 20px;
    color: var(--gray-600);
    background: linear-gradient(135deg, var(--gray-0) 0%, var(--gray-100) 100%);
    font-size: 12px;
    border-radius: 8px;
    padding: 6px;
    z-index: 2;
    box-shadow: 0px 2px 4px var(--shadow-2);
    border: 1px solid var(--gray-100);
  }


  .top {
    display: flex;
    align-items: center;
    height: 54px;
    margin-bottom: 14px;

    .icon {
      width: 54px;
      height: 54px;
      font-size: 26px;
      margin-right: 14px;
      display: flex;
      justify-content: center;
      align-items: center;
      background: var(--main-30);
      border-radius: 12px;
      border: 1px solid var(--gray-200);
      color: var(--main-color);
      position: relative;
    }

    .info {
      h3, p {
        margin: 0;
        color: var(--gray-10000);
      }

      h3 {
        font-size: 17px;
        font-weight: 600;
        letter-spacing: -0.02em;
        line-height: 1.4;
      }

      p {
        color: var(--gray-700);
        font-size: 13px;
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 4px;
        font-weight: 400;

        .created-time-inline {
          color: var(--gray-500);
          font-size: 11px;
          font-weight: 400;
          background: var(--gray-50);
          padding: 2px 6px;
          border-radius: 4px;
        }
      }
    }
  }

  .description {
    color: var(--gray-600);
    overflow: hidden;
    display: -webkit-box;
    line-clamp: 2;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    text-overflow: ellipsis;
    margin-bottom: 12px;
    font-size: 13px;
    line-height: 1.5;
    font-weight: 400;
    flex: 1;
  }


}

.database-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  flex-direction: column;
  color: var(--gray-900);
}

.database-container {
  padding: 0;
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
