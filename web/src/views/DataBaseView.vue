<template>
  <div class="database-container layout-container" v-if="configStore.config.enable_knowledge_base">
    <HeaderComponent
      title="文档知识库"
      description="知识型数据库，主要是非结构化的文本组成，使用向量检索使用。如果出现问题，可以检查 saves/data/database.json 查看配置。"
    >
      <template #actions>
        <a-button type="primary" @click="newDatabase.open=true">新建知识库</a-button>
      </template>
    </HeaderComponent>

    <a-modal :open="newDatabase.open" title="新建知识库" @ok="createDatabase" @cancel="newDatabase.open=false">
      <h3>知识库名称<span style="color: var(--error-color)">*</span></h3>
      <a-input v-model:value="newDatabase.name" placeholder="新建知识库名称" />
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
        <a-button key="back" @click="newDatabase.open=false">取消</a-button>
        <a-button key="submit" type="primary" :loading="newDatabase.loading" @click="createDatabase">创建</a-button>
      </template>
    </a-modal>
    <div class="databases">
      <div class="new-database dbcard" @click="newDatabase.open=true">
        <div class="top">
          <div class="icon"><PlusOutlined /></div>
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
        <p class="description">{{ database.description || '暂无描述' }}</p>
        <div class="tags">
          <a-tag color="blue" v-if="database.embed_model">{{ database.embed_model }}</a-tag>
          <a-tag color="green" v-if="database.dimension">{{ database.dimension }}</a-tag>
        </div>
        <!-- <button @click="deleteDatabase(database.collection_name)">删除</button> -->
      </div>
    </div>
    <!-- <h2>图数据库 &nbsp; <a-spin v-if="graphloading" :indicator="indicator" /></h2>
    <p>基于 neo4j 构建的图数据库。</p>
    <div :class="{'graphloading': graphloading, 'databases': true}" v-if="graph">
      <div class="dbcard graphbase" @click="navigateToGraph">
        <div class="top">
          <div class="icon"><AppstoreFilled /></div>
          <div class="info">
            <h3>{{ graph?.database_name }}</h3>
            <p>
              <span>{{ graph?.status }}</span> ·
              <span>{{ graph?.entity_count }}实体</span>
            </p>
          </div>
        </div>
        <p class="description">基于 neo4j 构建的图数据库。基于 neo4j 构建的图数据库。基于 neo4j 构建的图数据库。</p>
      </div>
    </div> -->
  </div>
  <div class="database-empty" v-else>
    <a-empty>
      <template #description>
        <span>
          前往 <router-link to="/setting" style="color: var(--main-color); font-weight: bold;">设置</router-link> 页面配置知识库。
        </span>
      </template>
    </a-empty>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch, h } from 'vue'
import { useRouter, useRoute } from 'vue-router';
import { message, Button } from 'ant-design-vue'
import { ReadFilled, PlusOutlined, AppstoreFilled, LoadingOutlined } from '@ant-design/icons-vue'
import { useConfigStore } from '@/stores/config';
import HeaderComponent from '@/components/HeaderComponent.vue';

const route = useRoute()
const router = useRouter()
const databases = ref([])
const graph = ref(null)
const graphloading = ref(false)

const indicator = h(LoadingOutlined, {spin: true});
const configStore = useConfigStore()

const newDatabase = reactive({
  name: '',
  description: '',
  dimension: '',
  loading: false,
})

const loadDatabases = () => {
  // loadGraph()
  fetch('/api/data/', {
    method: "GET",
  })
    .then(response => response.json())
    .then(data => {
      console.log(data)
      databases.value = data.databases
    }
  )
}

const createDatabase = () => {
  newDatabase.loading = true
  console.log(newDatabase)
  if (!newDatabase.name) {
    message.error('数据库名称不能为空')
    newDatabase.loading = false
    return
  }
  fetch('/api/data/', {
    method: "POST",
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      database_name: newDatabase.name,
      description: newDatabase.description,
      dimension: newDatabase.dimension ? parseInt(newDatabase.dimension) : null,
    })
  })
  .then(response => response.json())
  .then(data => {
    console.log(data)
    loadDatabases()
    newDatabase.open = false
    newDatabase.name = ''
    newDatabase.description = '',
    newDatabase.dimension = ''
  })
  .finally(() => {
    newDatabase.loading = false
  })
}

const navigateToDatabase = (databaseId) => {
  router.push({ path: `/database/${databaseId}` });
};

const navigateToGraph = () => {
  router.push({ path: `/database/graph` });
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
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    text-overflow: ellipsis;
    margin-bottom: 10px;
  }
}

// 整个卡片是模糊的
// .graphloading {
//   filter: blur(2px);
// }

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
