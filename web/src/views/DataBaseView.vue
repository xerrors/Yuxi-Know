<template>
  <div class="database-container">
    <h2>文档知识库</h2>
    <p>知识型数据库，主要是非结构化的文本组成，使用向量检索使用。</p>
    <a-modal :open="newDatabase.open" title="新建数据库" @ok="createDatabase">
      <h3>数据库名称<span style="color: red">*</span></h3>
      <a-input v-model:value="newDatabase.name" placeholder="新建数据库名称" />
      <h3 style="margin-top: 20px;">数据库描述</h3>
      <a-textarea
        v-model:value="newDatabase.description"
        placeholder="新建数据库描述"
        :auto-size="{ minRows: 2, maxRows: 5 }"
      />
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
            <h3>新建数据库</h3>
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
            <p><span>{{ database.metaname }}</span> · <span>{{ database.metadata.row_count }}</span></p>
          </div>
        </div>
        <p class="description">{{ database.description }}</p>
        <!-- <button @click="deleteDatabase(database.collection_name)">删除</button> -->
      </div>
    </div>
    <h2>图数据库</h2>
    <p>基于 neo4j 构建的图数据库。</p>
    <div :class="{'graphloading': graphloading}">
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
        <!-- <button @click="deleteDatabase(database.collection_name)">删除</button> -->
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router';
import { message, Button } from 'ant-design-vue'
import { ReadFilled, PlusOutlined, AppstoreFilled } from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()
const databases = ref([])
const graph = ref(null)
const graphloading = ref(false)

const newDatabase = reactive({
  name: '',
  description: '',
  loading: false,
})

const loadDatabases = () => {
  loadGraph()
  fetch('/api/database/', {
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
  fetch('/api/database/', {
    method: "POST",
    body: JSON.stringify({
      database_name: newDatabase.name,
      description: newDatabase.description,
      db_type: "knowledge"
    })
  })
  .then(response => response.json())
  .then(data => {
    console.log(data)
    loadDatabases()
    newDatabase.open = false
    newDatabase.name = ''
    newDatabase.description = ''
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

const loadGraph = () => {
  graphloading.value = true
  fetch('/api/database/graph', {
    method: "GET",
  })
    .then(response => response.json())
    .then(data => {
      console.log(data)
      graph.value = data.graph
      graphloading.value = false
    })
    .catch(error => {
      console.error(error)
      message.error(error.message)
      graphloading.value = false
    })
}

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
.database-container {
  padding: 10px 30px;
  background-color: #FCFEFF;

  h2 {
    margin: 20px 0 10px 0;
  }
}
.database-actions, .document-actions {
  margin-bottom: 20px;
}
.databases {
  display: flex;
  flex-wrap: wrap;
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
  padding: 10px;
  border-radius: 12px;
  width: 380px;
  height: 150px;
  padding: 20px;
  cursor: pointer;
  flex: 1 1 380px;
  max-width: 380px;

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
    }

    .info {
      h3, p {
        margin: 0;
      }

      p {
        color: var(--c-text-light-1);
        font-size: small;
      }
    }
  }

  .description {
    color: var(--c-text-light-1);
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    text-overflow: ellipsis;
  }
}

// 整个卡片是模糊的
.graphloading {
  filter: blur(2px);
}

</style>
