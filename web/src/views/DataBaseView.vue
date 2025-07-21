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
      <a-select v-model:value="newDatabase.kb_type" @change="handleKbTypeChange" style="width: 100%;" size="large">
        <a-select-option v-for="(typeInfo, typeKey) in supportedKbTypes" :key="typeKey" :value="typeKey">
          <div class="kb-type-option">
            <div class="type-header">
              <component :is="getKbTypeIcon(typeKey)" class="type-icon" />
              <span class="type-title">{{ getKbTypeLabel(typeKey) }}</span>
            </div>
            <div class="type-desc">{{ typeInfo.description }}</div>
          </div>
        </a-select-option>
      </a-select>

      <!-- 类型说明 -->
      <div class="kb-type-guide" v-if="newDatabase.kb_type">
        <a-alert
          :message="getKbTypeDescription(newDatabase.kb_type)"
          :type="getKbTypeAlertType(newDatabase.kb_type)"
          show-icon
          style="margin: 12px 0;"
        />
      </div>

      <h3>知识库名称<span style="color: var(--error-color)">*</span></h3>
      <a-input v-model:value="newDatabase.name" placeholder="新建知识库名称" size="large" />

      <h3>嵌入模型</h3>
      <a-select v-model:value="newDatabase.embed_model_name" :options="embedModelOptions" style="width: 100%;" size="large" />
      <!-- 根据类型显示不同配置 -->
        <div v-if="newDatabase.kb_type === 'chroma' || newDatabase.kb_type === 'milvus'" class="chunk-config">
          <h3>分块配置</h3>
          <div class="chunk-params">
          <div class="param-row">
            <label>分块大小：</label>
            <a-input-number
              v-model:value="newDatabase.chunk_size"
              :min="100"
              :max="5000"
              :step="100"
              style="width: 120px;"
            />
            <span class="param-hint">每个文本片段的最大字符数（100-5000）</span>
          </div>
          <div class="param-row">
            <label>重叠长度：</label>
            <a-input-number
              v-model:value="newDatabase.chunk_overlap"
              :min="0"
              :max="500"
              :step="50"
              style="width: 120px;"
            />
            <span class="param-hint">相邻片段间的重叠字符数（0-500）</span>
          </div>
        </div>
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
    <div class="databases">
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
            <p><span>{{ database.files ? Object.keys(database.files).length : 0 }} 文件</span></p>
          </div>
        </div>
        <a-tooltip :title="database.description || '暂无描述'">
          <p class="description">{{ database.description || '暂无描述' }}</p>
        </a-tooltip>
        <div class="tags">
          <a-tag color="blue" v-if="database.embed_info?.name">{{ database.embed_info.name }}</a-tag>
          <a-tag color="green" v-if="database.embed_info?.dimension">{{ database.embed_info.dimension }}</a-tag>
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
import { ReadFilled, DatabaseOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import { BookPlus, Database, Zap } from 'lucide-vue-next';
import { knowledgeBaseApi } from '@/apis/admin_api';
import HeaderComponent from '@/components/HeaderComponent.vue';

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

const emptyEmbedInfo = {
  name: '',
  description: '',
  embed_model_name: configStore.config?.embed_model,
  kb_type: 'lightrag', // 默认为 LightRAG
  // Vector 知识库特有配置
  chunk_size: 1000,
  chunk_overlap: 200,
}

const newDatabase = reactive({
  ...emptyEmbedInfo,
})

// 支持的知识库类型
const supportedKbTypes = ref({})

// 加载支持的知识库类型
const loadSupportedKbTypes = async () => {
  try {
    const data = await knowledgeBaseApi.getSupportedKbTypes()
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
  knowledgeBaseApi.getDatabases()
    .then(data => {
      console.log(data)
      databases.value = data.databases
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
    lightrag: Database,
    chroma: Zap,
    milvus: ThunderboltOutlined
  }
  return icons[type] || Database
}

const getKbTypeDescription = (type) => {
  const descriptions = {
    lightrag: '🔥 图结构索引 • 智能查询 • 关系挖掘 • 复杂推理',
    chroma: '⚡ 轻量向量 • 快速开发 • 本地部署 • 简单易用',
    milvus: '🚀 生产级 • 高性能 • 分布式 • 企业级部署'
  }
  return descriptions[type] || ''
}

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

// 处理知识库类型改变
const handleKbTypeChange = (type) => {
  console.log('知识库类型改变:', type)
  // 可以在这里根据类型设置默认值
  if (type === 'chroma' || type === 'milvus') {
    newDatabase.chunk_size = 1000
    newDatabase.chunk_overlap = 200
  }
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

  // 向量类型的额外验证（Chroma 和 Milvus）
  if (newDatabase.kb_type === 'chroma' || newDatabase.kb_type === 'milvus') {
    if (!newDatabase.chunk_size || newDatabase.chunk_size < 100) {
      message.error('分块大小不能小于100')
      return
    }
    if (newDatabase.chunk_overlap < 0) {
      message.error('重叠长度不能小于0')
      return
    }
  }

  state.creating = true

  const requestData = {
    database_name: newDatabase.name.trim(),
    description: newDatabase.description?.trim() || '',
    embed_model_name: newDatabase.embed_model_name || configStore.config.embed_model,
    kb_type: newDatabase.kb_type,
  }

  // 添加类型特有的配置
  if (newDatabase.kb_type === 'chroma' || newDatabase.kb_type === 'milvus') {
    requestData.extra_config = {
      chunk_size: newDatabase.chunk_size,
      chunk_overlap: newDatabase.chunk_overlap,
    }
  }

  knowledgeBaseApi.createDatabase(requestData)
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
  .kb-type-option {
    // padding: 4px 0;

    .type-header {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 2px;

      .type-icon {
        width: 16px;
        height: 16px;
        color: var(--main-color);
        flex-shrink: 0;
      }

      .type-title {
        font-weight: 600;
      }
    }

    .type-desc {
      font-size: 12px;
      color: var(--gray-600);
      padding-left: 20px;
    }
  }

  .kb-type-guide {
    margin: 12px 0;
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

.new-database-modal {
  h3 {
    margin-top: 10px;
  }
}
</style>
