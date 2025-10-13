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
          :model_name="newDatabase.llm_info.model_name || '请选择模型'"
          :model_provider="newDatabase.llm_info.provider || ''"
          @select-model="handleLLMSelect"
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
      <div class="new-database dbcard" @click="state.openNewDatabaseModel=true">
        <div class="top">
          <div class="icon"><BookPlus /></div>
          <div class="info">
            <h3>新建知识库</h3>
          </div>
        </div>
        <p>导入您自己的文本数据或通过Webhook实时写入数据以增强 LLM 的上下文。</p>
      </div>
      <div
        v-for="database in databases"
        :key="database.db_id"
        class="database dbcard"
        @click="navigateToDatabase(database.db_id)">
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
import { BookPlus, Database, Zap, FileDigit,  Waypoints, Building2 } from 'lucide-vue-next';
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

const emptyEmbedInfo = {
  name: '',
  description: '',
  embed_model_name: configStore.config?.embed_model,
  kb_type: 'chroma', // 默认为 Milvus
  // Vector 知识库特有配置
  storage: '', // 存储方式配置
  // LightRAG 特有配置
  language: 'English',
  llm_info: {
    provider: '',
    model_name: ''
  },
}

const newDatabase = reactive({
  ...emptyEmbedInfo,
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
  Object.assign(newDatabase, { ...emptyEmbedInfo })
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
}

// 处理LLM选择
const handleLLMSelect = (selection) => {
  console.log('LLM选择:', selection)
  newDatabase.llm_info.provider = selection.provider
  newDatabase.llm_info.model_name = selection.name
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
    additional_params: {}
  }

  // 添加类型特有的配置
  if (newDatabase.kb_type === 'chroma' || newDatabase.kb_type === 'milvus') {
    requestData.additional_params.storage = newDatabase.storage || 'DemoA'
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

watch(() => route.path, (newPath, oldPath) => {
  if (newPath === '/database') {
    loadDatabases();
  }
});

onMounted(() => {
  loadSupportedKbTypes()
  loadDatabases()
})

</script>

<style lang="less" scoped>
.new-database-modal {
  .kb-type-guide {
    margin: 12px 0;
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
      border: 2px solid #f0f0f0;
      border-radius: 12px;
      padding: 20px;
      cursor: pointer;
      transition: all 0.3s ease;
      background: white;
      position: relative;
      overflow: hidden;

      &:hover {
        border-color: var(--main-color);
        transform: translateY(-1px);
      }

      // 为不同知识库类型设置不同的悬停颜色
      &:nth-child(1):hover {
        border-color: #d3adf7;
      }

      &:nth-child(2):hover {
        border-color: #ffd591;
      }

      &:nth-child(3):hover {
        border-color: #ffadd2;
      }

      &.active {
        border-color: var(--main-color);
        background: #f8faff;

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
          border-color: #d3adf7;
          background: #f9f0ff;

          .type-icon {
            color: #722ed1;
          }

          .feature-tag {
            background: rgba(114, 46, 209, 0.1);
            color: #722ed1;
          }
        }
      }

      &:nth-child(2) {
        &.active {
          border-color: #ffd591;
          background: #fff7e6;

          .type-icon {
            color: #fa8c16;
          }

          .feature-tag {
            background: rgba(250, 140, 22, 0.1);
            color: #fa8c16;
          }
        }
      }

      &:nth-child(3) {
        &.active {
          border-color: #ffadd2;
          background: #fff1f0;

          .type-icon {
            color: #f5222d;
          }

          .feature-tag {
            background: rgba(245, 34, 45, 0.1);
            color: #f5222d;
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
        min-height: 40px;
      }

      .card-features {
        .feature-tag {
          display: inline-block;
          padding: 4px 8px;
          background: rgba(24, 144, 255, 0.1);
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
    background-color: #fafafa;
    border-radius: 6px;
    border: 1px solid #f0f0f0;

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

  .new-database {
    background-color: #F0F3F4;
  }
}

.database, .graphbase {
  background-color: white;
  box-shadow: 0px 1px 2px 0px rgba(16,24,40,.06),0px 1px 3px 0px rgba(16,24,40,.1);
  border: 2px solid white;
  transition: box-shadow 0.2s ease-in-out;

  &:hover {
    box-shadow: 0px 4px 6px -2px rgba(16,24,40,.03),0px 12px 16px -4px rgba(16,24,40,.08);
  }
}

.dbcard, .database {
  width: 100%;
  padding: 10px;
  border-radius: 12px;
  height: 160px;
  padding: 20px;
  cursor: pointer;
  display: flex;
  flex-direction: column;

  .top {
    display: flex;
    align-items: center;
    height: 50px;
    margin-bottom: 10px;

    .icon {
      width: 50px;
      height: 50px;
      font-size: 28px;
      margin-right: 10px;
      display: flex;
      justify-content: center;
      align-items: center;
      background-color: #F5F8FF;
      border-radius: 8px;
      border: 1px solid #E0EAFF;
      color: var(--main-color);
    }

    .info {
      h3, p {
        margin: 0;
        color: black;
      }

      h3 {
        font-size: 16px;
        font-weight: bold;
      }

      p {
        color: var(--gray-900);
        font-size: small;
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;

        .created-time-inline {
          color: var(--gray-500);
          font-size: 12px;
        }
      }
    }
  }

  .description {
    color: var(--gray-900);
    overflow: hidden;
    display: -webkit-box;
    line-clamp: 1;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    text-overflow: ellipsis;
    margin-bottom: 10px;
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
