<template>
  <div class="database-container layout-container">
    <HeaderComponent title="连接数据库" :loading="state.loading">
      <template #actions>
        <a-button type="primary" @click="state.openNewSqlDatabaseModel=true">
          连接数据库
        </a-button>
      </template>
    </HeaderComponent>

    <a-modal :open="state.openNewSqlDatabaseModel" title="连接数据库" @ok="createDatabaseConnection" @cancel="cancelConnectDatabase" class="new-database-modal" width="800px">

      <!-- 知识库类型选择 -->
      <h3>数据库类型<span style="color: var(--error-color)">*</span></h3>
      <div class="kb-type-cards">
        <div
          v-for="(typeInfo, typeKey) in supportedDbTypes"
          :key="typeKey"
          class="kb-type-card"
          :class="{ active: newDatabaseConnection.db_type === typeKey }"
          @click="handleDbTypeChange(typeKey)"
        >
          <div class="card-header">
            <component :is="getDbTypeIcon(typeKey)" class="type-icon" />
            <span class="type-title">{{ getDbTypeLabel(typeKey) }}</span>
          </div>
          <div class="card-description">{{ typeInfo.description }}</div>
          <div class="card-features">
            <span class="feature-tag">{{ getDbTypeFeature(typeKey) }}</span>
          </div>
        </div>
      </div>


      <h3>数据库配置<span style="color: var(--error-color)">*</span></h3>
      <!-- 数据库配置表单 -->
      <a-form :model="newDatabaseConnection" layout="vertical">
        <a-form-item label="主机地址" required>
          <a-input v-model:value="newDatabaseConnection.host" placeholder="例如：127.0.0.1" size="large" />
        </a-form-item>

        <a-form-item label="端口" required>
          <a-input-number v-model:value="newDatabaseConnection.port" :min="1" :max="65535" size="large" style="width: 100%;" />
        </a-form-item>

        <a-form-item label="用户名" required>
          <a-input v-model:value="newDatabaseConnection.user" placeholder="请输入数据库用户名" size="large" />
        </a-form-item>

        <a-form-item label="密码" required>
          <a-input-password v-model:value="newDatabaseConnection.password" placeholder="请输入数据库密码" size="large" />
        </a-form-item>

        <a-form-item label="数据库名称" required>
          <a-input v-model:value="newDatabaseConnection.database" placeholder="请输入要连接的数据库名称" size="large" />
        </a-form-item>

        <a-form-item label="描述" required>
          <a-textarea
            v-model:value="newDatabaseConnection.description"
            placeholder="请输入数据库连接描述（可选）"
            :auto-size="{ minRows: 3, maxRows: 5 }"
          />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button key="back" @click="cancelConnectDatabase">取消</a-button>
        <a-button key="submit" type="primary" :loading="state.creating" @click="createDatabaseConnection">连接</a-button>
      </template>
    </a-modal>

    <!-- 选择数据库表 -->
    <a-modal :open="state.openDatabaseTableModel" title="选择数据库表" @ok="createDatabase" @cancel="cancelDatabaseTableSelect" class="new-database-modal" width="800px">
      <h3>选择数据库表<span style="color: var(--error-color)">*</span></h3>
      <!-- 数据库表多选列表 -->
      <div class="table-cards">
        <a-empty v-if="!state.database.tables || state.database.tables.length === 0" description="暂无数据库表" />
        <a-row :gutter="[16, 16]">
          <a-col
            v-for="table in tableList"
            :key="table.table_name"
            :xs="24"
            :sm="12"
            :md="8"
            :lg="6"
          >
            <a-card
              size="small"
              hoverable
              :class="{ 'table-card-selected': selectedTableIds.includes(table.table_id) }"
              @click="toggleTable(table)"
            >
              <div class="table-card-content">
                <div class="checkbox-container">
                  <a-checkbox
                    :checked="selectedTableIds.includes(table.table_id)"
                    @click.stop
                    @change="(e) => toggleTable(table)"
                  />
                </div>
                <div class="table-info">
                  <div class="table-description">{{ table.table_comment || '暂无描述' }}</div>
                  <div class="table-name">{{ table.table_name }}</div>
                </div>
              </div>
            </a-card>
          </a-col>
        </a-row>
      </div>

      <template #footer>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <a-button danger @click="deleteDatabaseConnection(state.database.db_id)">删除</a-button>
          <div>
            <a-button key="back" @click="cancelDatabaseTableSelect" style="margin-right: 8px;">取消</a-button>
            <a-button key="submit" type="primary" :loading="state.creating" @click="createChooseDatabaseTables">连接</a-button>
          </div>
        </div>
      </template>
    </a-modal>

    <!-- 加载状态 -->
    <div v-if="state.loading" class="loading-container">
      <a-spin size="large" />
      <p>正在加载知识库...</p>
    </div>

    <!-- 空状态显示 -->
    <div v-else-if="!databases || databases.length === 0" class="empty-state">
      <h3 class="empty-title">暂无知识库</h3>
      <p class="empty-description">创建您的第一个知识库，开始管理文档和知识</p>
      <a-button type="primary" size="large" @click="state.openNewSqlDatabaseModel = true">
        <template #icon>
          <PlusOutlined />
        </template>
        创建知识库
      </a-button>
    </div>
    <!-- 数据库连接列表 -->
    <div v-else class="databases">
      <!-- <div class="new-database dbcard" @click="state.openNewSqlDatabaseModel=true">
        <div class="top">
          <div class="icon"><BookPlus /></div>
          <div class="info">
            <h3>连接数据库</h3>
          </div>
        </div>
        <p>连接您需要使用的数据库。</p>
      </div> -->
      <div
        v-for="database in databases"
        :key="database.db_id"
        class="database dbcard"
        @click="navigateToDatabase(database)">
        <!-- @click="navigateToDatabase(database.db_id)"> -->
        <div class="top">
          <div class="icon">
            <component :is="getDbTypeIcon(database.db_type || 'lightrag')" />
          </div>
          <div class="info">
            <h3>{{ database.name }}</h3>
            <p>
              <span>已选择 {{ database.selected_tables ? Object.keys(database.selected_tables).length : 0 }} / {{ database.tables ? Object.keys(database.tables).length : 0 }} 数据库表</span>
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
            :color="getKbTypeColor(database.db_type || 'lightrag')"
            class="kb-type-tag"
            size="small"
          >
            {{ getDbTypeLabel(database.db_type || 'lightrag') }}
          </a-tag>        
        </div>

      </div>
       <!-- button @click="deleteDatabase(database.collection_name)" 删除</button>  --> 

   </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router';
import { useConfigStore } from '@/stores/config';
import { message } from 'ant-design-vue'
import { BookPlus, Database, Zap, FileDigit,  Waypoints, Building2, TableOfContents } from 'lucide-vue-next';
import { LockOutlined, InfoCircleOutlined, PlusOutlined } from '@ant-design/icons-vue';
import { databaseApi } from '@/apis/sql_database_api';
import HeaderComponent from '@/components/HeaderComponent.vue';
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue';
import dayjs, { parseToShanghai } from '@/utils/time';
import {
  LeftOutlined,
  EditOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue';

const route = useRoute()
const router = useRouter()
const databases = ref([])
const configStore = useConfigStore()

const state = reactive({
  loading: false,
  creating: false,
  openNewSqlDatabaseModel: false,
  openDatabaseTableModel: false,
  database: databases.value[0],
})

// const selectedTableIds = computed(() => {
//   return Object.values(databases.selected_tables || {}).map(table => table.table_id)
// })

// const selectedTableIds = computed({
//   get: () => state.database.selected_tables ? Object.values(state.database.selected_tables).map(table => table.table_id) : [],
//   set: (value) => state.database.selected_tables = value,
// })

const selectedTableIds = ref([]);
const selectedTableIdsBack = ref([]);


const navigateToDatabase = (database) => {
  state.openDatabaseTableModel=true;
  state.database=database;
  selectedTableIds.value = database.selected_tables ? Object.values(database.selected_tables).map(table => table.table_id) : [];
  selectedTableIdsBack.value = database.selected_tables ? Object.values(database.selected_tables).map(table => table.table_id) : [];
}



const tableList = computed(() => {
  return Object.values(state.database.tables || {}).slice().reverse()
})


const emptyDbInfo = {
  name: '',
  description: '',
  db_type: 'mysql', // 默认为 Milvus
  host: '127.0.0.1',
  port: '3306',
  user: 'root',
  password: '',
  database: 'lcmom',
  description: '',
}

const newDatabaseConnection = reactive({
  ...emptyDbInfo,
})


// 支持的知识库类型
const supportedDbTypes = ref({})

// 加载支持的知识库类型
const loadSupportedDbTypes = async () => {
  // try {
  //   const data = await typeApi.getKnowledgeBaseTypes()
  //   supportedDbTypes.value = data.db_types
  //   console.log('支持的知识库类型:', supportedDbTypes.value)
  // } catch (error) {
  //   console.error('加载知识库类型失败:', error)
  //   // 如果加载失败，设置默认类型
  supportedDbTypes.value = {
    mysql: {
      description: "Mysql数据库知识库",
      class_name: "mysql"
    }
  }
  // }
}

const toggleTable = (table) => {
  const table_id = table.table_id;
  selectedTableIds.value = selectedTableIds.value.includes(table_id)
    ? selectedTableIds.value.filter(t => t !== table_id)
    : [...selectedTableIds.value, table_id]
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
  Object.assign(newDatabaseConnection, { ...emptyDbInfo })
}

const cancelConnectDatabase = () => {
  state.openNewSqlDatabaseModel = false
}

const cancelDatabaseTableSelect = () => {
  selectedTableIds.value = selectedTableIdsBack.value
  state.openDatabaseTableModel = false
}


// 知识库类型相关工具方法
const getDbTypeLabel = (type) => {
  const labels = {
    lightrag: 'LightRAG',
    chroma: 'Chroma',
    milvus: 'Milvus',
    mysql: 'MySQL'
  }
  return labels[type] || type
}

const getDbTypeIcon = (type) => {
  const icons = {
    lightrag: Waypoints,
    chroma: FileDigit,
    milvus: Building2,
    mysql: TableOfContents
  }
  return icons[type] || Database
}

const getKbTypeColor = (type) => {
  const colors = {
    lightrag: 'purple',
    chroma: 'orange',
    milvus: 'red'
  }
  return colors[type] || 'blue'
}

const getDbTypeFeature = (type) => {
  const features = {
    lightrag: '图结构索引',
    chroma: '轻量向量',
    milvus: '生产级部署',
    mysql: '关系型数据库'
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
    return '今天连接'
  }
  if (diffInDays === 1) {
    return '昨天连接'
  }
  if (diffInDays < 7) {
    return `${diffInDays} 天前连接`
  }
  if (diffInDays < 30) {
    const weeks = Math.floor(diffInDays / 7)
    return `${weeks} 周前连接`
  }
  if (diffInDays < 365) {
    const months = Math.floor(diffInDays / 30)
    return `${months} 个月前连接`
  }
  const years = Math.floor(diffInDays / 365)
  return `${years} 年前连接`
}

// 处理数据库类型改变
const handleDbTypeChange = (type) => {
  console.log('数据库类型改变:', type)
  resetNewDatabase()
  newDatabaseConnection.db_type = type
}


const createDatabaseConnection = () => {
  if (!newDatabaseConnection.database?.trim()) {
    message.error('数据库名称不能为空')
    return
  }
  if (!newDatabaseConnection.db_type) {
    message.error('请选择知识库类型')
    return
  }

  state.creating = true
  
  const requestData = {
    database_name: newDatabaseConnection.database.trim(),
    description: newDatabaseConnection.description?.trim() || '',
    db_type: newDatabaseConnection.db_type.trim(),
  }
  requestData.connection_info = {
    host: newDatabaseConnection.host.trim(),
    port: parseInt(newDatabaseConnection.port.trim(), 10),
    user: newDatabaseConnection.user.trim(),
    password: newDatabaseConnection.password.trim(),
    database: newDatabaseConnection.database.trim()
  }

  databaseApi.createDatabase(requestData)
    .then(data => {
      console.log('连接成功:', data)
      if (data.status === 'failed') {
        message.error(data.message || '连接失败')
        return
      }
      loadDatabases()
      resetNewDatabase()
      message.success('连接成功')
    })
    .catch(error => {
      console.error('连接数据库失败:', error)
      message.error(error.message || '连接失败')
    })
    .finally(() => {
      state.creating = false
      state.openNewSqlDatabaseModel = false
    })
}

const deleteDatabaseConnection = (db_id) => {
  // 弹出确认框
  const confirmed = window.confirm('确定要删除该数据库连接吗？此操作不可恢复。')
  if (!confirmed) return

  console.log('删除数据库连接:', db_id)

  databaseApi.deleteConnection(db_id)
    .then(data => {
      console.log('删除成功:', data)
      if (data.status === 'failed') {
        message.error(data.message || '删除失败')
        return
      }
      loadDatabases()
      resetNewDatabase()
      message.success('删除成功')
    })
    .catch(error => {
      console.error('删除数据库失败:', error)
      message.error('删除数据库失败')
    })
    .finally(() => {
      state.creating = false
      state.openDatabaseTableModel= false
    })
}

const createChooseDatabaseTables = () => {

  state.creating = true

  const requestData = selectedTableIds.value
  // {
  //   database_name: newDatabaseConnection.name.trim(),
  //   description: newDatabaseConnection.description?.trim() || '',
  //   embed_model_name: newDatabaseConnection.embed_model_name || configStore.config.embed_model,
  //   db_type: newDatabaseConnection.db_type
  // }

  const db_id = state.database.db_id
  databaseApi.createChooseDatabaseTables(db_id, requestData)
    .then(data => {
      console.log('数据库表连接成功:', data)
      loadDatabases()
      resetNewDatabase()
      message.success('数据库表连接成功')
    })
    .catch(error => {
      console.error('数据库表连接失败:', error)
      message.error(error.message || '连接失败')
    })
    .finally(() => {
      state.creating = false
      state.openNewSqlDatabaseModel = false
      state.openDatabaseTableModel = false
    })
}

const createDatabase = () => {
  if (!newDatabaseConnection.name?.trim()) {
    message.error('数据库名称不能为空')
    return
  }

  if (!newDatabaseConnection.db_type) {
    message.error('请选择知识库类型')
    return
  }

  state.creating = true

  const requestData = {
    database_name: newDatabaseConnection.name.trim(),
    description: newDatabaseConnection.description?.trim() || '',
    embed_model_name: newDatabaseConnection.embed_model_name || configStore.config.embed_model,
    db_type: newDatabaseConnection.db_type
  }

  // 添加类型特有的配置
  if (newDatabaseConnection.db_type === 'chroma' || newDatabaseConnection.db_type === 'milvus') {
    requestData.additional_params.storage = newDatabaseConnection.storage || 'DemoA'
  }

  if (newDatabaseConnection.db_type === 'lightrag') {
    requestData.additional_params.language = newDatabaseConnection.language || 'English'
    // 添加LLM信息到请求数据
    if (newDatabaseConnection.llm_info.provider && newDatabaseConnection.llm_info.model_name) {
      requestData.llm_info = {
        provider: newDatabaseConnection.llm_info.provider,
        model_name: newDatabaseConnection.llm_info.model_name
      }
    }
  }

  databaseApi.createDatabase(requestData)
    .then(data => {
      console.log('连接成功:', data)
      loadDatabases()
      resetNewDatabase()
      message.success('连接成功')
    })
    .catch(error => {
      console.error('连接数据库失败:', error)
      message.error(error.message || '连接失败')
    })
    .finally(() => {
      state.creating = false
      state.openNewSqlDatabaseModel = false
    })
}

// const navigateToDatabase = (databaseId) => {
//   router.push({ path: `/database/${databaseId}` });
// };

watch(() => route.path, (newPath, oldPath) => {
  if (newPath === '/database') {
    loadDatabases();
  }
});

onMounted(() => {
  loadSupportedDbTypes()
  loadDatabases()
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

      &:last-child {
        margin-bottom: 0;
      }

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

          &:last-child {
            margin-top: 0;
          }
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
        .type-icon { color: var(--main-color); }
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

// .database, .graphbase {
//   background-color: white;
//   box-shadow: 0px 1px 2px 0px rgba(16,24,40,.06),0px 1px 3px 0px rgba(16,24,40,.1);
//   border: 2px solid white;
//   transition: box-shadow 0.2s ease-in-out;

//   &:hover {
//     box-shadow: 0px 4px 6px -2px rgba(16,24,40,.03),0px 12px 16px -4px rgba(16,24,40,.08);
//   }
// }

.database, .graphbase {
  background: linear-gradient(145deg, var(--gray-0) 0%, var(--gray-10) 100%);
  box-shadow: 0px 1px 2px 0px var(--shadow-2);
  border: 1px solid var(--gray-100);
  transition: none;
  position: relative;
}

.dbcard, .database {
  width: 100%;
  padding: 16px;
  border-radius: 16px;
  height: 156px;
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
      border: 1px solid var(--gray-150);
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
    line-clamp: 1;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    text-overflow: ellipsis;
    margin-bottom: 12px;
    font-size: 13px;
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

.table-cards {
  .table-card-content {
    display: flex;
    align-items: center;
    gap: 12px;
    height: 100%;
    min-height: 60px;

    .checkbox-container {
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .table-info {
      flex: 1;
      display: flex;
      flex-direction: column;
      justify-content: center;
      min-height: 40px;
      white-space: normal;
      overflow-wrap: break-word;
      word-break: break-word;

      .table-name {
        font-size: 12px;
        color: var(--gray-600);
        line-height: 1.4;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;

        // font-weight: 500;
        // color: var(--gray-800);
        // font-size: 14px;
        // line-height: 1.3;
        // margin-bottom: 4px;
      }

      .table-description {
        font-weight: 500;
        color: var(--gray-800);
        font-size: 14px;
        line-height: 1.3;
        margin-bottom: 4px;
        // font-size: 12px;
        // color: var(--gray-600);
        // line-height: 1.4;
        // display: -webkit-box;
        // -webkit-line-clamp: 2;
        // -webkit-box-orient: vertical;
        // overflow: hidden;
        // text-overflow: ellipsis;
      }
    }
  }

  .ant-card-body {
    padding: 12px !important;
  }
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
</style>
