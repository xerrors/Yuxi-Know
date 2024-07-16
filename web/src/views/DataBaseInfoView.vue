<template>
  <div style="display: flex;">
  <div class="sider">
    <a-button type="link" @click="backToDatabase"><LeftOutlined />返回知识库</a-button>
    <div class="top">
      <div class="icon"><ReadFilled /></div>
      <div class="info">
        <h3>{{ database.name }}</h3>
        <p><span>{{ database.metaname }}</span> · <span>{{ database.metadata?.row_count }}</span></p>
      </div>
    </div>
    <p class="description">{{ database.description }}</p>
  </div>
  <div class="db-info-container">
    <h2>向知识库中添加文件</h2>
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
          <a-button class="del-btn" type="link" @click="deleteFile(text)" :disabled="state.lock">删除</a-button>
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
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue';
import { message } from 'ant-design-vue';
import { useRoute, useRouter } from 'vue-router';
import {
  ReadFilled,
  LeftOutlined,
  CheckCircleFilled,
  HourglassFilled,
  CloseCircleFilled,
  ClockCircleFilled,
} from '@ant-design/icons-vue'


const route = useRoute();
const router = useRouter();
const databaseId = ref(route.params.database_id);
const database = ref({});

const fileList = ref([]);
const selectedFile = ref(null);

const state = reactive({
  loading: false,
  refrashing: false,
  lock: false,
  drawer: false,
});

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
  const refreshInterval = setInterval(() => {
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
      message.success(data.status)
    })
    .catch(error => {
      console.error(error)
      message.error(error.status)
    })
    .finally(() => {
      getDatabaseInfo()
      clearInterval(refreshInterval)
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
    getDatabaseInfo();
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
  width: 300px;
  height: 100%;
  padding: 20px;
  border-right: 1px solid #E0EAFF;

  button {
    margin-bottom: 20px;
  }
}

.db-info-container {
  padding: 20px;
  flex: 1 1 auto;
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
    padding: 4px 8px;
    border-radius: 2px;
    font-size: small;
    font-weight: bold;
  }

  .pdf {
    background: #f17592;
  }

  .txt {

    background: #31c989;
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

  button.del-btn:hover {
    cursor: pointer;
    color: var(--error-color);
  }
}
</style>
