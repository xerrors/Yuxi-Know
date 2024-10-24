<template>
<div>
  <HeaderComponent
    :title="database.name || '数据库信息'"
  >
    <template #description>
      <div class="database-info">
        <a-tag color="blue" v-if="database.embed_model">{{ database.embed_model }}</a-tag>
        <a-tag color="green" v-if="database.dimension">{{ database.dimension }}</a-tag>
        <span class="row-count">{{ database.metadata?.row_count }} 行 · {{ database.files?.length || 0 }} 文件</span>
      </div>
    </template>
    <template #actions>
      <a-button type="primary" @click="backToDatabase">
        <LeftOutlined /> 返回
      </a-button>
      <a-button type="primary" danger @click="deleteDatabse">
        <DeleteOutlined /> 删除数据库
      </a-button>
    </template>
  </HeaderComponent>
  <a-alert v-if="database.embed_model != configStore.config.embed_model" message="向量模型不匹配，请重新选择" type="warning" style="margin: 10px 20px;" />
  <div class="db-main-container">
    <a-tabs v-model:activeKey="state.curPage" class="atab-container" type="card">
      <a-tab-pane key="add">
        <template #tab><span><CloudUploadOutlined />添加文件</span></template>
        <div class="db-tab-container">
          <div class="upload">
            <a-upload-dragger
              class="upload-dragger"
              v-model:fileList="fileList"
              name="file"
              :multiple="true"
              :disabled="state.loading"
              action="/api/data/upload"
              @change="handleFileUpload"
              @drop="handleDrop"
            >
              <p class="ant-upload-text">点击或者把文件拖拽到这里上传</p>
              <p class="ant-upload-hint">
                目前仅支持上传文本文件，如 .pdf, .txt, .md。且同名文件无法重复添加
              </p>
            </a-upload-dragger>
          </div>
          <div class="actions">
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
          </div>
          <a-table :columns="columns" :data-source="database.files" row-key="filename" class="my-table">
            <template #bodyCell="{ column, text, record }">
              <template v-if="column.key === 'filename'">
                <a-button class="main-btn" type="link" @click="openFileDetail(record)">{{ text }}</a-button>
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
                  :disabled="state.lock || record.status === 'processing' || record.status === 'waiting' "
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
            :title="selectedFile?.filename || '文件详情'"
            placement="right"
            @after-open-change="afterOpenChange"
          >
            <h2>共 {{ selectedFile?.lines.length }} 个片段</h2>
            <p v-for="line in selectedFile?.lines" :key="line.id">
              <strong>Chunk #{{ line.id }}</strong>   {{ line.text }}
            </p>
          </a-drawer>
        </div>
      </a-tab-pane>
      <a-tab-pane key="query-test" force-render>
        <template #tab><span><SearchOutlined />检索测试</span></template>
        <div class="query-test-container db-tab-container">
          <div class="sider">
            <div class="sider-top">
              <div class="query-params" v-if="state.curPage == 'query-test'">
                <!-- <h3 class="params-title">参数配置</h3> -->
                <div class="params-group">
                  <div class="params-item">
                    <p>检索数量：</p>
                    <a-input-number size="small" v-model:value="meta.maxQueryCount" :min="1" :max="20" />
                  </div>
                  <div class="params-item">
                    <p>过滤低质量：</p>
                    <a-switch v-model:checked="meta.filter" />
                  </div>
                  <div class="params-item">
                    <p>筛选 TopK：</p>
                    <a-input-number size="small" v-model:value="meta.topK" :min="1" :max="meta.maxQueryCount" />
                  </div>
                </div>
                <div class="params-group">
                  <div class="params-item w100" v-if="configStore.config.enable_reranker">
                    <p>重排序阈值：</p>
                    <a-slider v-model:value="meta.rerankThreshold" :min="0" :max="1" :step="0.01" />
                  </div>
                  <div class="params-item w100">
                    <p>距离阈值：</p>
                    <a-slider v-model:value="meta.distanceThreshold" :min="0" :max="1" :step="0.01" />
                  </div>
                </div>
                <div class="params-group">
                  <div class="params-item col">
                    <p>重写查询<small>（修改后需重新检索）</small>：</p>
                    <a-segmented v-model:value="meta.rewriteQuery" :options="rewriteQueryOptions">
                      <template #label="{ payload }">
                        <div>
                          <p style="margin: 4px 0">{{ payload.subTitle }}</p>
                        </div>
                      </template>
                    </a-segmented>
                  </div>
                </div>
              </div>
            </div>
            <div class="sider-bottom">
            </div>
          </div>
          <div class="query-result-container">
            <div class="query-action">
              <a-textarea
                v-model:value="queryText"
                placeholder="填写需要查询的句子"
                :auto-size="{ minRows: 2, maxRows: 10 }"
              />
              <a-button class="btn-query" @click="onQuery" :disabled="queryText.length == 0">
                <span v-if="!state.searchLoading"><SearchOutlined /> 检索</span>
                <span v-else><LoadingOutlined /></span>
              </a-button>
            </div>

            <!-- 新增示例按钮 -->
            <span>示例查询：</span>
            <div class="query-examples">
              <a-button v-for="example in queryExamples" :key="example" @click="useQueryExample(example)">
                {{ example }}
              </a-button>
            </div>
            <div class="query-test" v-if="queryResult">
              <div class="results-overview">
                <div class="results-stats">
                  <span class="stat-item">
                    <strong>总数:</strong> {{ queryResult.all_results.length }}
                  </span>
                  <span class="stat-item">
                    <strong>过滤后:</strong> {{ filteredResults.length }}
                  </span>
                  <span class="stat-item">
                    <strong>TopK:</strong> {{ meta.topK }}
                  </span>
                </div>
                <div class="rewritten-query">
                  <strong>重写后查询:</strong>
                  <span class="query-text">{{ queryResult.rw_query }}</span>
                </div>
              </div>
              <div class="query-result-card" v-for="(result, idx) in (filteredResults)" :key="idx">
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
      </a-tab-pane>
      <!-- <a-tab-pane key="3" tab="Tab 3">Content of Tab Pane 3</a-tab-pane> -->
    </a-tabs>
  </div>
</div>
</template>

<script setup>
import { onMounted, reactive, ref, watch, toRaw } from 'vue';
import { message, Modal } from 'ant-design-vue';
import { useRoute, useRouter } from 'vue-router';
import { useConfigStore } from '@/stores/config'
import HeaderComponent from '@/components/HeaderComponent.vue';
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
  LoadingOutlined
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
const filteredResults = ref([])
const configStore = useConfigStore()

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
  mode: 'search',
  maxQueryCount: 30,
  filter: true,
  rewriteQuery: 'off',
  rerankThreshold: 0.1,
  distanceThreshold: 0.3,
  topK: 10,
});

const rewriteQueryOptions = ref([
  { value: 'off', payload: { title: 'off', subTitle: '不启用' } },
  { value: 'on', payload: { title: 'on', subTitle: '启用重写' } },
  { value: 'hyde', payload: { title: 'hyde', subTitle: '伪文档生成' } },
])

const filterQueryResults = () => {
  if (!queryResult.value || !queryResult.value.all_results) {
    return;
  }

  let results = toRaw(queryResult.value.all_results);
  console.log("results", results);

  if (meta.filter) {
    results = results.filter(r => r.distance >= meta.distanceThreshold);
    console.log("before", results);
    if (configStore.config.enable_reranker) {
      results = results
        .filter(r => r.rerank_score >= meta.rerankThreshold)
        .sort((a, b) => b.rerank_score - a.rerank_score);
    }
    console.log("after", results);

    results = results.slice(0, meta.topK);
  }

  filteredResults.value = results;
}

const onQuery = () => {
  if (database.value.embed_model != configStore.config.embed_model) {
    message.error('向量模型不匹配，请重新选择')
    return
  }

  console.log(queryText.value)
  state.searchLoading = true
  if (!queryText.value.trim()) {
    message.error('请输入查询内容')
    state.searchLoading = false
    return
  }
  meta.db_name = database.value.metaname
  fetch('/api/data/query-test', {
    method: "POST",
    headers: {
      "Content-Type": "application/json"  // 添加 Content-Type 头
    },
    body: JSON.stringify({
      query: queryText.value.trim(),
      meta: meta
    }),
  })
  .then(response => response.json())
  .then(data => {
    console.log(data)
    queryResult.value = data
    filterQueryResults()
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
      fetch(`/api/data/?db_id=${databaseId.value}`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json"
        },
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
  fetch(`/api/data/document?db_id=${databaseId.value}&file_id=${record.file_id}`, {
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
  if (!db_id) {
    return
  }
  state.lock = true
  return new Promise((resolve, reject) => {
    fetch(`/api/data/info?db_id=${db_id}`, {
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
  fetch('/api/data/document', {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json"  // 添加 Content-Type 头
    },
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
  fetch('/api/data/add-by-file', {
    method: "POST",
    headers: {
      "Content-Type": "application/json"  // 添加 Content-Type 头
    },
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
  // { title: '文件ID', dataIndex: 'file_id', key: 'file_id' },
  { title: '文件名', dataIndex: 'filename', key: 'filename' },
  { title: '上传时间', dataIndex: 'created_at', key: 'created_at' },
  { title: '状态', dataIndex: 'status', key: 'status' },
  { title: '类型', dataIndex: 'type', key: 'type' },
  { title: '操作', key: 'action', dataIndex: 'file_id' }
];

watch(() => route.params.database_id, (newId) => {
    databaseId.value = newId;
    console.log(newId)
    clearInterval(state.refreshInterval)
    getDatabaseInfo()
  }
);

// 检测到 meta 变化时重新查询
watch(() => meta, () => {
  filterQueryResults()
}, { deep: true })

// 添加示例查询
const queryExamples = ref([
  '食品添加剂的安全性如何?',
  '如何识别和预防食物中毒?',
  '转基因食品对人体健康有什么影响?',
  '如何正确储存和处理生鲜食品?'
]);

// 使用示例查询的方法
const useQueryExample = (example) => {
  queryText.value = example;
  onQuery();
};

onMounted(() => {
  getDatabaseInfo();
  // const refreshInterval = setInterval(() => {
  //   getDatabaseInfo();
  // }, 10000);
})



</script>

<style lang="less" scoped>
.database-info {
  margin: 8px 0 0;
}

.db-main-container {
  display: flex;
  width: 100%;
}

.db-tab-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.query-test-container {
  display: flex;
  flex-direction: row;
  gap: 20px;

  .sider {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    width: 325px;
    height: 100%;
    padding: 0;
    flex: 0 0 325px;

    .sider-top {
      .query-params {
        display: flex;
        flex-direction: column;
        box-sizing: border-box;
        font-size: 15px;
        gap: 12px;
        // background-color: var(--main-light-6);
        // padding: 16px;
        // box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        // border: 1px solid var(--main-light-3);
        // border-radius: 8px;
        padding-top: 12px;
        padding-right: 16px;
        border-right: 1px solid var(--main-light-3);

        .params-title {
          margin-top: 0;
          margin-bottom: 16px;
          color: var(--main-color);
          font-size: 18px;
          text-align: center;
        }

        .params-group {
          margin-bottom: 16px;
          padding-bottom: 16px;
          border-bottom: 1px solid var(--main-light-3);

          &:last-child {
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
          }
        }

        .params-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 12px;

          &:last-child {
            margin-bottom: 0;
          }

          p {
            margin: 0;
            font-size: 16px;
            color: var(--gray-900);
          }

          &.col {
            align-items: flex-start;
            flex-direction: column;
            width: 100%;
            height: auto;
          }

          &.w100,
          &.col {
            & > * {
              width: 100%;
            }
          }
        }

        .ant-slider {
          margin: 6px 0px;
        }
      }
    }
  }

  .query-result-container {
    flex: 1;
    padding-bottom: 20px;
  }

  .query-action {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;

    textarea {
      padding: 12px 16px;
      border: 1px solid var(--main-light-2);
    }

    button.btn-query {
      height: auto;
      width: 100px;
      box-shadow: none;
      border: none;
      font-weight: bold;
      background: var(--main-light-3);
      color: var(--main-color);

      &:disabled {
        cursor: not-allowed;
        background: var(--main-light-4);
        color: var(--gray-700);
      }
    }
  }

  .query-examples {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 10px 0;

    .ant-btn {
      font-size: 14px;
      padding: 4px 12px;
      height: auto;
      background-color: var(--gray-200);
      border: none;
      color: var(--gray-800);

      &:hover {
        background-color: var(--gray-300);
      }
    }
  }

  .query-test {
    display: flex;
    flex-direction: column;
    border-radius: 12px;
    gap: 20px;

    .results-overview {
      background-color: #fff;
      border-radius: 8px;
      padding: 16px;
      border: 1px solid var(--main-light-3);

      .results-stats {
        display: flex;
        justify-content: flex-start;

        .stat-item {
          border-radius: 4px;
          font-size: 14px;
          margin-right: 24px;
          padding: 4px 8px;
          strong {
            color: var(--main-color);
            margin-right: 4px;
          }
        }
      }

      .rewritten-query {
        border-radius: 4px;
        font-size: 14px;
        padding: 4px 8px;
        strong {
          color: var(--main-color);
          margin-right: 8px;
        }

        .query-text {
          font-style: italic;
          color: var(--gray-900);
        }
      }
    }

    .query-result-card {
      padding: 20px;
      border-radius: 8px;
      background: #fff;
      border: 1px solid var(--main-light-3);
      transition: box-shadow 0.3s ease;

      &:hover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
      }

      p {
        margin-bottom: 8px;
        line-height: 1.6;
        color: var(--gray-900);

        &:last-child {
          margin-bottom: 0;
        }
      }

      strong {
        color: var(--main-color);
      }

      .query-text {
        font-size: 15px;
        margin-top: 12px;
        padding-top: 12px;
        border-top: 1px solid var(--main-light-3);
      }
    }
  }
}

.upload {
  .upload-dragger {
    margin: 0px;
  }
}

.my-table {
  button.ant-btn-link {
    padding: 0;
  }

  .pdf, .txt, .md {
    color: white;
    padding: 2px 4px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: bold;
    opacity: 0.8;
    user-select: none;
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

<style lang="less">
.atab-container {
  padding: 0;
  width: 100%;
  max-height: 100%;
  overflow: auto;

  div.ant-tabs-nav {
    background: var(--main-light-5);
    padding: 8px 20px;
    padding-bottom: 0;
  }

  .ant-tabs-content-holder {
    padding: 0 20px;
  }
}

.params-item.col .ant-segmented {
  width: 100%;

  div.ant-segmented-group {
    display: flex;
    justify-content: space-around;
  }
}

</style>

<style lang="less">
.db-main-container {
  .atab-container {
    padding: 0;
    width: 100%;
    max-height: 100%;
    overflow: auto;

    div.ant-tabs-nav {
      background: var(--main-light-5);
      padding: 8px 20px;
      padding-bottom: 0;
    }

    .ant-tabs-content-holder {
      padding: 0 20px;
    }
  }

  .params-item.col .ant-segmented {
    width: 100%;
    font-size: smaller;
    div.ant-segmented-group {
      display: flex;
      justify-content: space-around;
    }
    label.ant-segmented-item {
      flex: 1;
      text-align: center;
      div.ant-segmented-item-label > div > p {
        font-size: small;
      }
    }
  }
}


</style>
