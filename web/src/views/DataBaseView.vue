<template>
  <div class="database-container layout-container">
    <HeaderComponent title="文档知识库" :loading="state.loading">
      <template #actions>
        <a-button type="primary" @click="state.openNewDatabaseModel=true">
          新建知识库
        </a-button>
      </template>
    </HeaderComponent>

    <a-modal :open="state.openNewDatabaseModel" title="新建知识库" @ok="createDatabase" @cancel="cancelCreateDatabase">
      <h3>知识库名称<span style="color: var(--error-color)">*</span></h3>
      <a-input v-model:value="newDatabase.name" placeholder="新建知识库名称" />
      <h3>嵌入模型</h3>
      <a-select v-model:value="newDatabase.embed_model_name" :options="embedModelOptions" />
      <h3 style="margin-top: 20px;">知识库描述</h3>
      <p style="color: var(--gray-700); font-size: 14px;">在智能体流程中，这里的描述会作为工具的描述。智能体会根据知识库的标题和描述来选择合适的工具。所以这里描述的越详细，智能体越容易选择到合适的工具。</p>
      <a-textarea
        v-model:value="newDatabase.description"
        placeholder="新建知识库描述"
        :auto-size="{ minRows: 5, maxRows: 10 }"
      />
      <!-- <h3 style="margin-top: 20px;">向量维度</h3>
      <p>必须与向量模型 {{ configStore.config.embed_model }} 一致</p>
      <a-input v-model:value="newDatabase.dimension" placeholder="向量维度 (e.g. 768, 1024)" /> -->
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
          <div class="icon"><ReadFilled /></div>
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
import { ReadFilled } from '@ant-design/icons-vue'
import { BookPlus } from 'lucide-vue-next';
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
  return Object.keys(configStore.config?.embed_model_info || {}).map(key => ({
    label: configStore.config?.embed_model_info[key]?.name || key,
    value: key,
  }))
})

const emptyEmbedInfo = {
  name: '',
  description: '',
  embed_model_name: '',
}

const newDatabase = reactive({
  ...emptyEmbedInfo,
})

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

const createDatabase = () => {
  if (!newDatabase.name?.trim()) {
    message.error('数据库名称不能为空')
    return
  }

  state.creating = true

  const requestData = {
    database_name: newDatabase.name.trim(),
    description: newDatabase.description?.trim() || '',
    embed_model_name: newDatabase.embed_model_name || configStore.config.embed_model,
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
  loadDatabases()
})

</script>

<style lang="less" scoped>
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
</style>
