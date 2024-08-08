<template>
  <div style="display: flex;">
  <div class="sider">
    <div class="sider-top">
      <div class="header-actions">
        <a-button type="text" @click="backToDatabase"><LeftOutlined /></a-button>
        <a-button type="text" danger class="del-db" @click="deleteDatabse"><DeleteOutlined /></a-button>
      </div>
      <div class="top">
        <div class="icon"><ReadFilled /></div>
        <div class="info">
          <h3>{{ database.name }}</h3>
          <p><span>{{ database.metadata?.row_count }}行 · {{  database.files?.length || 0 }}文件</span></p>
        </div>
      </div>
      <p class="description">{{ database.description }}</p>
      <div class="tags">
        <a-tag color="blue" v-if="database.embed_model">Embed: {{ database.embed_model }}</a-tag>
      </div>
      <a-divider/>
      <div class="pagebtns">
        <a-button @click="state.curPage='add'" :class="{ 'active': state.curPage === 'add' }">
          <CloudUploadOutlined />添加文件
        </a-button>
        <a-button @click="state.curPage='query-test'" :class="{ 'active': state.curPage === 'query-test' }">
          <SearchOutlined />检索测试
        </a-button>
      </div>
      <div class="query-params" v-if="state.curPage == 'query-test'">
        <p style="text-align: center; margin: 0;"><strong>参数配置</strong></p>
        <div class="params-item">
          <p>检索数量：</p>
          <a-input-number size="small" v-model:value="meta.queryCount" :min="1" :max="20" />
        </div>
        <div class="params-item">
          <p>过滤低质量：</p>
          <a-switch v-model:checked="meta.filter" />
        </div>
        <div class="params-item">
          <p>重写查询</p>
            <a-segmented v-model:value="meta.rewrite_query" :options="['OFF', 'ON', 'HyDE']" />

        </div>
      </div>
    </div>
    <div class="sider-bottom">
    </div>
  </div>
  <div class="db-info-container" v-if="state.curPage == 'add'">
    <h3>向知识库中添加文件</h3>
    <div class="upload">
      <a-upload-dragger
        class="upload-dragger"
        v-model:fileList="fileList"
        name="file"
        :multiple="true"
        :disabled="state.loading"
        action="/api/database/upload"
        @change="handleFileUpload"
        @drop="handleDrop"
      >
        <p class="ant-upload-text">点击或者把文件拖拽到这里上传</p>
        <p class="ant-upload-hint">
          目前仅支持上传文本文件，如 .pdf, .txt, .md。且同名文件无法重复添加。
        </p>
      </a-upload-dragger>
    </div>
    <a-button
      type="primary"
      @click="addDocumentByFile"
      :loading="state.loading"
      :disabled="fileList.length === 0"
      style="margin: 0px 20px 20px 0;"
    >
      添加到知识库
    </a-button>
    <a-button @click="handleRefresh" :loading="state.refrashing">刷新状态</a-button>
    <a-table :columns="columns" :data-source="database.files" row-key="file_id" class="my-table">
      <template #bodyCell="{ column, text, record }">
        <template v-if="column.key === 'file_id'">
          <a-button class="main-btn" type="link" @click="openFileDetail(record)">{{ text.toUpperCase() }}</a-button>
        </template>
        <template v-else-if="column.key === 'type'"><span :class="text">{{ text.toUpperCase() }}</span></template>
        <template v-else-if="column.key === 'status' && text === 'done'">
          <CheckCircleFilled style="color: #41A317;"/>
        </template>
        <template v-else-if="column.key === 'status' && text === 'failed'">
          <CloseCircleFilled style="color: #FF4D4F ;"/>
        </template>
        <template v-else-if="column.key === 'status' && text === 'processing'">
          <HourglassFilled style="color: #1677FF;"/>
        </template>
        <template v-else-if="column.key === 'status' && text === 'waiting'">
          <ClockCircleFilled style="color: #FFCD43;"/>
        </template>
        <template v-else-if="column.key === 'action'">
          <a-button class="del-btn" type="link"
            @click="deleteFile(text)"
            :disabled="state.lock || record.status == 'processing' || record.status == 'waiting' "
            >删除
          </a-button>
        </template>
        <span v-else-if="column.key === 'created_at'">{{ formatRelativeTime(Math.round(text*1000)) }}</span>
        <span v-else>{{ text }}</span>
      </template>
    </a-table>
    <a-drawer
      width="50%"
      v-model:open="state.drawer"
      class="custom-class"
      :title="selectedFile?.filename"
      placement="right"
      @after-open-change="afterOpenChange"
    >
      <h2>共 {{ selectedFile?.lines.length }} 个片段</h2>
      <p v-for="line in selectedFile?.lines" :key="line.id">
        <strong>Chunk #{{ line.id }}</strong>   {{ line.text }}
      </p>
    </a-drawer>
  </div>
  <div class="db-info-container" v-else-if="state.curPage == 'query-test'">
    <h3>检索测试</h3>
    <div class="query-action">
      <a-textarea
        v-model:value="queryText"
        placeholder="填写需要查询的句子"
        :auto-size="{ minRows: 2, maxRows: 10 }"
      />
      <!-- :loading="state.searchLoading" -->
      <a-button @click="onQuery" :disabled="queryText.length == 0" :loading="state.searchLoading">
        <SearchOutlined v-if="!state.searchLoading"/>检索
      </a-button>
    </div>
    <div class="query-test" v-if="queryResult">
      <div class="query-card" v-for="(result, idx) in (meta.filter ? queryResult.results : queryResult.all_results)" :key="idx">
        <p>
          <strong>#{{ idx + 1 }}&nbsp;&nbsp;&nbsp;</strong>
          <span>{{ result.file.filename }}&nbsp;&nbsp;&nbsp;</span>
          <span><strong>距离</strong>：{{ result.distance.toFixed(4) }}&nbsp;&nbsp;&nbsp;</span>
          <span v-if="result.rerank_score"><strong>重排序</strong>：{{ result.rerank_score.toFixed(4) }}</span>
        </p>
        <p class="query-text">{{ result.entity.text }}</p>
      </div>
    </div>
  </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue';
import { message, Modal } from 'ant-design-vue';
import { useRoute, useRouter } from 'vue-router';
import {
  ReadFilled,
  LeftOutlined,
  CheckCircleFilled,
  HourglassFilled,
  CloseCircleFilled,
  ClockCircleFilled,
  DeleteOutlined,
  CloudUploadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'


const route = useRoute();
const router = useRouter();
const databaseId = ref(route.params.database_id);
const database = ref({});

const fileList = ref([]);
const selectedFile = ref(null);

// 查询测试
const queryText = ref('');
const queryResult = ref(null)

const state = reactive({
  loading: false,
  refrashing: false,
  searchLoading: false,
  lock: false,
  drawer: false,
  refreshInterval: null,
  curPage: "add",
});

const meta = reactive({
  queryCount: 10,
  filter: false,
  rewrite_query: 'OFF',
});

const onQuery = () => {
  console.log(queryText.value)
  state.searchLoading = true
  if (!queryText.value.trim()) {
    message.error('请输入查询内容')
    state.searchLoading = false
    return
  }
  meta.db_name = database.value.metaname
  fetch('/api/database/query-test', {
    method: "POST",
    body: JSON.stringify({
      query: queryText.value.trim(),
      meta: meta
    }),
  })
  .then(response => response.json())
  .then(data => {
    console.log(data)
    queryResult.value = data
  })
  .catch(error => {
    console.error(error)
    message.error(error.message)
  })
  .finally(() => {
    state.searchLoading = false
  })
}

const handleFileUpload = (event) => {
  console.log(event)
  console.log(fileList.value)
}

const handleDrop = (event) => {
  console.log(event)
  console.log(fileList.value)
}

const afterOpenChange = (visible) => {
  if (!visible) {
    selectedFile.value = null
  }
}

const backToDatabase = () => {
  router.push('/database')
}

const handleRefresh = () => {
  state.refrashing = true
  getDatabaseInfo().then(() => {
    state.refrashing = false
    console.log(database.value)
  })
}

const deleteDatabse = () => {

  Modal.confirm({
    title: '删除数据库',
    content: '确定要删除该数据库吗？',
    okText: '确认',
    cancelText: '取消',
    onOk: () => {
      state.lock = true
      fetch('/api/database/', {
        method: "DELETE",
        body: JSON.stringify({
          db_id: databaseId.value
        }),
      })
      .then(response => response.json())
      .then(data => {
        console.log(data)
        message.success(data.message)
        router.push('/database')
      })
      .catch(error => {
        console.error(error)
        message.error(error.message)
      })
      .finally(() => {
        state.lock = false
      })
    },
    onCancel: () => {
      console.log('Cancel');
    },
  });
}

const openFileDetail = (record) => {
  state.lock = true
  fetch(`/api/database/document?db_id=${databaseId.value}&file_id=${record.file_id}`, {
    method: "GET",
  })
    .then(response => response.json())
    .then(data => {
      console.log(data)
      state.lock = false
      selectedFile.value = record
      selectedFile.value.lines = data.lines
      state.drawer = true
    })
    .catch(error => {
      console.error(error)
      message.error(error.message)
    })
}

const formatRelativeTime = (timestamp) => {
    const now = Date.now();
    const secondsPast = (now - timestamp) / 1000;
    if (secondsPast < 60) {
        return Math.round(secondsPast) + ' 秒前';
    } else if (secondsPast < 3600) {
        return Math.round(secondsPast / 60) + ' 分钟前';
    } else if (secondsPast < 86400) {
        return Math.round(secondsPast / 3600) + ' 小时前';
    } else {
        const date = new Date(timestamp);
        const year = date.getFullYear();
        const month = date.getMonth() + 1;
        const day = date.getDate();
        return `${year} 年 ${month} 月 ${day} 日`;
    }
}


const getDatabaseInfo = () => {
  const db_id = databaseId.value
  state.lock = true
  return new Promise((resolve, reject) => {
    fetch(`/api/database/info?db_id=${db_id}`, {
      method: "GET",
    })
      .then(response => response.json())
      .then(data => {
        database.value = data
        resolve(data)
      })
      .catch(error => {
        console.error(error)
        message.error(error.message)
        reject(error)
      })
      .finally(() => {
        state.lock = false
      })
  })
}


const deleteFile = (fileId) => {
  console.log(fileId)
  state.lock = true
  fetch('/api/database/document', {
    method: "DELETE",
    body: JSON.stringify({
      db_id: databaseId.value,
      file_id: fileId
    }),
  })
    .then(response => response.json())
    .then(data => {
      console.log(data)
      message.success(data.message)
      getDatabaseInfo()
    })
    .catch(error => {
      console.error(error)
      message.error(error.message)
    })
}

const addDocumentByFile = () => {
  console.log(fileList.value)
  const files = fileList.value.filter(file => file.status === 'done').map(file => file.response.file_path)
  console.log(files)

  state.loading = true
  state.lock = true
  state.refreshInterval = setInterval(() => {
    getDatabaseInfo();
  }, 1000);
  fetch('/api/database/add_by_file', {
    method: "POST",
    body: JSON.stringify({
      db_id: databaseId.value,
      files: files
    }),
  })
    .then(response => response.json())
    .then(data => {
      console.log(data)
      fileList.value = []
      if (data.status === 'failed') {
        message.error(data.message)
      } else {
        message.success(data.message)
      }
    })
    .catch(error => {
      console.error(error)
      message.error(error.message)
    })
    .finally(() => {
      getDatabaseInfo()
      clearInterval(state.refreshInterval)
      state.loading = false
    })
}

const columns = [
  {
    title: '文件ID',
    dataIndex: 'file_id',
    key: 'file_id',
  },
  {
    title: '文件名',
    dataIndex: 'filename',
    key: 'filename',
  },
  {
    title: '上传时间',
    dataIndex: 'created_at',
    key: 'created_at',
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
  },
  {
    title: '类型',
    dataIndex: 'type',
    key: 'type',
  },
  {
    title: '操作',
    key: 'action',
    dataIndex: 'file_id',
  }
];

watch(() => route.params.database_id, (newId) => {
    databaseId.value = newId;
    console.log(newId)
    clearInterval(state.refreshInterval)
    getDatabaseInfo()
  }
);

onMounted(() => {
  getDatabaseInfo();
  // const refreshInterval = setInterval(() => {
  //   getDatabaseInfo();
  // }, 10000);
})

</script>

<style lang="less" scoped>
.sider {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  width: 275px;
  height: 100%;
  padding: 0;
  border-right: 1px solid #E0EAFF;
  flex: 0 0 275px;

  .sider-top {

    & > * {
      padding: 0 20px;
    }
    .header-actions {
      display: flex;
      justify-content: space-between;
      margin-bottom: 20px;
      padding-top: 10px;
      padding-bottom: 10px;
      background-color: var(--main-light-5);
      border-bottom: 1px solid #E0EAFF;

      button {
        height: auto;
        font-size: 16px;
        color: var(--c-text-light-1);
      }
    }
  }

  .pagebtns {
    display: flex;
    flex-direction: column;
    gap: 16px;

    button {
      padding: 10px 16px;
      height: auto;
      border-radius: 8px;
      border: none;
      background: var(--main-light-4);
    }

    .active {
      font-weight: bold;
      color: var(--main-color);
      background: var(--main-light-2);
    }
  }

  .query-params {
    display: flex;
    flex-direction: column;
    padding: 20px;
    border-radius: 8px;
    margin: 20px 0;
    box-sizing: border-box;
    gap: 12px;

    .params-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;

      p {
        margin: 0;
      }
    }
    .params-item.col {
      flex-direction: column;
    }

  }
}

.db-info-container {
  padding: 20px;
  flex: 1 1 auto;
  overflow: scroll;

  .query-action {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;

    textarea {
      padding: 12px 16px;
      border: 1px solid var(--main-light-2);
    }

    button {
      height: auto;
      width: 120px;
      box-shadow: none;
      border: none;
      font-weight: bold;
      background: var(--main-light-2);
      color: var(--main-color);

      &:disabled {
        cursor: not-allowed;
        background: var(--main-light-4);
        color: var(--c-black-light-3);
      }
    }
  }

  .query-test {
    display: flex;
    flex-direction: column;
    margin-bottom: 20px;
    border-radius: 8px;
    gap: 16px;

    .query-card {
      padding: 20px 16px;
      border-radius: 8px;
      background: var(--main-light-5);
      border: 1px solid var(--main-light-3);
    }

    .query-text {
      font-size: 14px;
      margin-bottom: 0;
      color: var(--c-text-light-1);
    }
  }
}

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

.upload {
  margin-bottom: 20px;

  .upload-dragger {
    margin: 0px;
  }
}

.my-table button.ant-btn-link {
    padding: 0;
}

.my-table {
  .pdf, .txt, .md {
    color: white;
    padding: 2px 4px;
    border-radius: 4px;
    font-size: small;
    font-weight: bold;
  }

  .pdf {
    background: #005F77;
  }

  .txt {

    background: #068033;
  }

  button.main-btn {
    font-weight: bold;
    font-size: 14px;
    &:hover {
      cursor: pointer;
      color: var(--main-color);
      font-weight: bold;
    }
  }

  button.del-btn {
    cursor: pointer;

    &:hover {
      color: var(--error-color);
    }
    &:disabled {
      cursor: not-allowed;
    }
  }

}
</style>
