<template>
<div>
  <HeaderComponent
    :title="database.name || '数据库信息'"
    :loading="state.databaseLoading"
  >
    <template #description>
      <div class="database-info">
        <a-tag color="blue" v-if="database.embed_model">{{ database.embed_model }}</a-tag>
        <a-tag color="green" v-if="database.dimension">{{ database.dimension }}</a-tag>
        <span class="row-count">{{ database.files ? Object.keys(database.files).length : 0 }} 文件 · {{ database.db_id }}</span>
      </div>
    </template>
    <template #actions>
      <a-button type="primary" @click="backToDatabase">
        <LeftOutlined /> 返回
      </a-button>
      <a-button type="primary" @click="showEditModal">
        <EditOutlined />
      </a-button>
    </template>
  </HeaderComponent>
  <!-- <a-alert v-if="configStore.config.embed_model &&database.embed_model != configStore.config.embed_model" message="向量模型不匹配，请重新选择" type="warning" style="margin: 10px 20px;" /> -->

  <!-- 添加编辑对话框 -->
  <a-modal v-model:open="editModalVisible" title="编辑知识库信息">
    <template #footer>
      <a-button danger @click="deleteDatabse" style="margin-right: auto; margin-left: 0;">
        <DeleteOutlined /> 删除数据库
      </a-button>
      <a-button key="back" @click="editModalVisible = false">取消</a-button>
      <a-button key="submit" type="primary" :loading="state.loading" @click="handleEditSubmit">确定</a-button>
    </template>
    <a-form :model="editForm" :rules="rules" ref="editFormRef" layout="vertical">
      <a-form-item label="知识库名称" name="name" required>
        <a-input v-model:value="editForm.name" placeholder="请输入知识库名称" />
      </a-form-item>
      <a-form-item label="知识库描述" name="description">
        <a-textarea v-model:value="editForm.description" placeholder="请输入知识库描述" :rows="4" />
      </a-form-item>
    </a-form>
  </a-modal>

  <!-- 分块参数配置弹窗 -->
  <a-modal v-model:open="chunkConfigModalVisible" title="分块参数配置" width="500px">
    <template #footer>
      <a-button key="back" @click="chunkConfigModalVisible = false">取消</a-button>
      <a-button key="submit" type="primary" @click="handleChunkConfigSubmit">确定</a-button>
    </template>
    <div class="chunk-config-content">
      <div class="params-info">
        <p>调整分块参数可以控制文本的切分方式，影响检索质量和文档加载效率。</p>
      </div>
      <a-form
        :model="tempChunkParams"
        name="chunkConfig"
        autocomplete="off"
        layout="vertical"
      >
        <a-form-item label="Chunk Size" name="chunk_size">
          <a-input-number v-model:value="tempChunkParams.chunk_size" :min="100" :max="10000" style="width: 100%;" />
          <p class="param-description">每个文本片段的最大字符数</p>
        </a-form-item>
        <a-form-item label="Chunk Overlap" name="chunk_overlap">
          <a-input-number v-model:value="tempChunkParams.chunk_overlap" :min="0" :max="1000" style="width: 100%;" />
          <p class="param-description">相邻文本片段间的重叠字符数</p>
        </a-form-item>
      </a-form>
    </div>
  </a-modal>

  <!-- 添加文件弹窗 -->
  <a-modal v-model:open="addFilesModalVisible" title="添加文件" width="800px">
    <template #footer>
      <a-button key="back" @click="addFilesModalVisible = false">取消</a-button>
      <a-button
        key="submit"
        type="primary"
        @click="chunkData"
        :loading="state.chunkLoading"
        :disabled="(uploadMode === 'file' && fileList.length === 0) || (uploadMode === 'url' && !urlList.trim())"
      >
        生成分块
      </a-button>
    </template>
    <div class="add-files-content">
      <div class="upload-header">
        <div class="source-selector">
          <div class="upload-mode-selector" @click="uploadMode = 'file'" :class="{ active: uploadMode === 'file' }">
            <FileOutlined /> 上传文件
          </div>
          <div class="upload-mode-selector" @click="uploadMode = 'url'" :class="{ active: uploadMode === 'url' }">
            <LinkOutlined /> 输入网址
          </div>
        </div>
        <div class="config-controls">
          <a-button type="dashed" @click="showChunkConfigModal">
            <SettingOutlined /> 分块参数 ({{ chunkParams.chunk_size }}/{{ chunkParams.chunk_overlap }})
          </a-button>
        </div>
      </div>

      <div class="ocr-config">
        <a-form layout="horizontal">
          <a-form-item label="使用OCR" name="enable_ocr">
            <a-select v-model:value="chunkParams.enable_ocr" :options="enable_ocr_options" style="width: 200px;" />
            <span class="param-description">启用OCR功能，支持PDF文件的文本提取</span>
          </a-form-item>
        </a-form>
      </div>

      <!-- 文件上传区域 -->
      <div class="upload" v-if="uploadMode === 'file'">
        <a-upload-dragger
          class="upload-dragger"
          v-model:fileList="fileList"
          name="file"
          :multiple="true"
          :disabled="state.chunkLoading"
          :action="'/api/data/upload?db_id=' + databaseId"
          :headers="getAuthHeaders()"
          @change="handleFileUpload"
          @drop="handleDrop"
        >
          <p class="ant-upload-text">点击或者把文件拖拽到这里上传</p>
          <p class="ant-upload-hint">
            目前仅支持上传文本文件，如 .pdf, .txt, .md。且同名文件无法重复添加
          </p>
        </a-upload-dragger>
      </div>

      <!-- URL 输入区域 -->
      <div class="url-input" v-else>
        <a-form layout="vertical">
          <a-form-item label="网页链接 (每行一个URL)">
            <a-textarea
              v-model:value="urlList"
              placeholder="请输入网页链接，每行一个"
              :rows="6"
              :disabled="state.chunkLoading"
            />
          </a-form-item>
        </a-form>
        <p class="url-hint">
          支持添加网页内容，系统会自动抓取网页文本并进行分块。请确保URL格式正确且可以公开访问。
        </p>
      </div>
    </div>
  </a-modal>

  <div class="db-main-container">
    <a-tabs v-model:activeKey="state.curPage" class="atab-container" type="card">

      <a-tab-pane key="files">
        <template #tab><span><ReadOutlined />文件列表</span></template>
        <div class="db-tab-container">
          <div class="actions" style="display: flex; gap: 10px; justify-content: space-between;">
            <div class="left-actions" style="display: flex; gap: 10px; align-items: center;">
              <a-button type="primary" @click="showAddFilesModal" :loading="state.refrashing" :icon="h(PlusOutlined)">添加文件</a-button>
              <a-button @click="handleRefresh" :loading="state.refrashing">刷新</a-button>
            </div>
            <div class="batch-actions" style="display: flex; gap: 10px;" v-if="selectedRowKeys.length > 0">
              <span style="margin-right: 8px;">已选择 {{ selectedRowKeys.length }} 项</span>
              <a-button
                type="primary"
                danger
                @click="handleBatchDelete"
                :loading="state.batchDeleting"
                :disabled="!canBatchDelete"
              >
                批量删除
              </a-button>
            </div>
          </div>

          <a-table
            :columns="columns"
            :data-source="Object.values(database.files || {})"
            row-key="file_id"
            class="my-table"
            size="small"
            bordered
            :pagination="pagination"
            :row-selection="{
              selectedRowKeys: selectedRowKeys,
              onChange: onSelectChange,
              getCheckboxProps: getCheckboxProps
            }">
            <template #bodyCell="{ column, text, record }">
              <a-tooltip v-if="column.key === 'filename'" :title="record.file_id" placement="left">
                <a-button class="main-btn" type="link" @click="openFileDetail(record)">{{ text }}</a-button>
              </a-tooltip>
              <span v-else-if="column.key === 'type'" :class="['span-type', text]">{{ text?.toUpperCase() }}</span>
              <CheckCircleFilled v-else-if="column.key === 'status' && text === 'done'" style="color: #41A317;"/>
              <CloseCircleFilled v-else-if="column.key === 'status' && text === 'failed'" style="color: #FF4D4F ;"/>
              <HourglassFilled v-else-if="column.key === 'status' && text === 'processing'" style="color: #1677FF;"/>
              <ClockCircleFilled v-else-if="column.key === 'status' && text === 'waiting'" style="color: #FFCD43;"/>

              <a-tooltip v-else-if="column.key === 'created_at'" :title="record.status" placement="left">
                <span>{{ formatRelativeTime(Math.round(text*1000)) }}</span>
              </a-tooltip>

              <div v-else-if="column.key === 'action'" style="display: flex; gap: 10px;">
                <a-button class="del-btn" type="link"
                  @click="handleDeleteFile(record.file_id)"
                  :disabled="state.lock || record.status === 'processing' || record.status === 'waiting'"
                  >
                  删除
                </a-button>
              </div>
              <span v-else>{{ text }}</span>
            </template>
          </a-table>
          <a-modal
            v-model:open="state.fileDetailModalVisible"
            class="custom-class"
            :title="selectedFile?.filename || '文件详情'"
            width="1000px"
            @after-open="afterOpenChange"
            :footer="null"
          >
            <template v-if="state.fileDetailLoading">
              <div class="loading-container">
                <a-spin tip="加载中..." />
              </div>
            </template>
            <template v-else>
              <h3>共 {{ selectedFile?.lines?.length || 0 }} 个片段</h3>
              <div class="file-detail-content">
                <p v-for="line in selectedFile?.lines || []" :key="line.id" class="line-text">
                  {{ line.content }}
                </p>
              </div>
            </template>
          </a-modal>
        </div>
      </a-tab-pane>

      <a-tab-pane key="query-test" force-render>
        <template #tab><span><SearchOutlined />检索测试</span></template>
        <div class="query-test-container db-tab-container">
          <div class="query-result-container">
            <div class="query-action">
              <a-textarea
                v-model:value="queryText"
                placeholder="填写需要查询的句子"
                :auto-size="{ minRows: 1, maxRows: 10 }"
              />
              <a-button class="btn-query" @click="onQuery" type="primary">
                <span v-if="!state.searchLoading"><SearchOutlined /> 检索</span>
                <span v-else><LoadingOutlined /></span>
              </a-button>
            </div>

            <!-- 新增示例按钮 -->
            <div class="query-examples-container">
              <div class="examples-title">示例查询：</div>
              <div class="query-examples">
                <a-button v-for="example in queryExamples" :key="example" @click="useQueryExample(example)">
                  {{ example }}
                </a-button>
              </div>
            </div>
            <div class="query-test" v-if="queryResult">
              {{ queryResult }}
            </div>
          </div>
          <div class="sider">
            <div class="sider-top">
              <div class="query-params" v-if="state.curPage == 'query-test'">
                <!-- <h3 class="params-title">查询参数</h3> -->
                <div class="params-group">
                  <div class="params-item">
                    <p>检索模式：</p>
                    <a-select v-model:value="meta.mode" :options="modeOptions" style="width: 120px;" />
                  </div>
                </div>
                <div class="params-group">
                  <div class="params-item">
                    <p>只使用上下文：</p>
                    <a-switch v-model:checked="meta.only_need_context" />
                  </div>
                  <div class="params-item">
                    <p>只使用上下文：</p>
                    <a-switch v-model:checked="meta.only_need_prompt" />
                  </div>
                  <div class="params-item">
                    <p>筛选 TopK：</p>
                    <a-input-number size="small" v-model:value="meta.top_k" :min="1" :max="meta.maxQueryCount" />
                  </div>
                </div>
                <div class="params-group">
                  <div class="params-item">
                    <p>片段最大Token数：</p>
                    <a-input-number size="small" v-model:value="meta.max_token_for_text_unit" :min="1" :max="4000" />
                  </div>
                  <div class="params-item">
                    <p>关系描述最大Token数：</p>
                    <a-input-number size="small" v-model:value="meta.max_token_for_global_context" :min="1" :max="4000" />
                  </div>
                  <div class="params-item">
                    <p>实体描述最大Token数：</p>
                    <a-input-number size="small" v-model:value="meta.max_token_for_local_context" :min="1" :max="4000" />
                  </div>
                </div>
              </div>
            </div>
            <div class="sider-bottom">
            </div>
          </div>
        </div>
      </a-tab-pane>
      <!-- <a-tab-pane key="3" tab="Tab 3">Content of Tab Pane 3</a-tab-pane> -->
       <template #rightExtra>
        <div class="auto-refresh-control">
          <span>自动刷新：</span>
          <a-switch v-model:checked="state.autoRefresh" @change="toggleAutoRefresh" size="small" />
        </div>
      </template>
    </a-tabs>
  </div>
</div>
</template>

<script setup>
import { onMounted, reactive, ref, watch, toRaw, onUnmounted, computed } from 'vue';
import { message, Modal } from 'ant-design-vue';
import { useRoute, useRouter } from 'vue-router';
import { useConfigStore } from '@/stores/config'
import { useUserStore } from '@/stores/user'
import { knowledgeBaseApi } from '@/apis/admin_api'
import HeaderComponent from '@/components/HeaderComponent.vue';
import {
  ReadOutlined,
  LeftOutlined,
  CheckCircleFilled,
  HourglassFilled,
  CloseCircleFilled,
  ClockCircleFilled,
  DeleteOutlined,
  CloudUploadOutlined,
  SearchOutlined,
  LoadingOutlined,
  FileOutlined,
  LinkOutlined,
  EditOutlined,
  PlusOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { h } from 'vue';


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
  databaseLoading: false,
  adding: false,
  refrashing: false,
  searchLoading: false,
  lock: false,
  fileDetailModalVisible: false,
  fileDetailLoading: false,
  refreshInterval: null,
  curPage: "files",
  batchDeleting: false,
  chunkLoading: false,
  autoRefresh: false,
  loading: false,
});

const meta = reactive({
  mode: 'mix',
  only_need_context: true,
  only_need_prompt: false,
  top_k: 10,
  max_token_for_text_unit: 4000,
  max_token_for_global_context: 4000,
  max_token_for_local_context: 4000,
});

const enable_ocr_options = ref([
  { value: 'disable', payload: { title: '不启用' } },
  { value: 'onnx_rapid_ocr', payload: { title: 'ONNX with RapidOCR' } },
  { value: 'mineru_ocr', payload: { title: 'MinerU OCR' } },
  { value: 'paddlex_ocr', payload: { title: 'Paddlex OCR' } },
])

const modeOptions = ref([
  { value: 'local', payload: { title: 'local', subTitle: '上下文相关信息' } },
  { value: 'global', payload: { title: 'global', subTitle: '全局知识' } },
  { value: 'hybrid', payload: { title: 'hybrid', subTitle: '本地和全局混合' } },
  { value: 'naive', payload: { title: 'naive', subTitle: '基本搜索' } },
  { value: 'mix', payload: { title: 'mix', subTitle: '知识图谱和向量检索混合' } },
  { value: 'bypass', payload: { title: 'bypass', subTitle: '绕过检索' } },
])

const pagination = ref({
  pageSize: 15,
  current: 1,
  total: computed(() => database.value?.files?.length || 0),
  showSizeChanger: true,
  onChange: (page, pageSize) => pagination.value.current = page,
  showTotal: (total, range) => `共 ${total} 条`,
  onShowSizeChange: (current, pageSize) => pagination.value.pageSize = pageSize,
})

const filterQueryResults = () => {
  if (!queryResult.value || !queryResult.value.all_results) {
    return;
  }

  let results = toRaw(queryResult.value.all_results);
  console.log("results", results);

  if (meta.filter) {
    results = results.filter(r => r.distance >= meta.distanceThreshold);
    console.log("before", results);

    // 根据排序方式决定排序逻辑
    if (configStore.config.enable_reranker) {
      // 先过滤掉低于阈值的结果
      results = results.filter(r => r.rerank_score >= meta.rerankThreshold);

      // 根据选择的排序方式进行排序
      if (meta.sortBy === 'rerank_score') {
        results = results.sort((a, b) => b.rerank_score - a.rerank_score);
      } else {
        // 按距离排序 (数值越大表示越相似)
        results = results.sort((a, b) => b.distance - a.distance);
      }
    } else {
      // 没有启用重排序时，默认按距离排序
      results = results.sort((a, b) => b.distance - a.distance);
    }

    console.log("after", results);

    results = results.slice(0, meta.topK);
  }

  filteredResults.value = results;
}

const onQuery = () => {
  // if (database.value.embed_model != configStore.config.embed_model) {
  //   message.error('向量模型不匹配，请重新选择')
  //   return
  // }

  console.log(queryText.value)
  state.searchLoading = true
  if (!queryText.value.trim()) {
    message.error('请输入查询内容')
    state.searchLoading = false
    return
  }
  meta.db_id = database.value.db_id

  try {
    knowledgeBaseApi.queryTest({
      query: queryText.value.trim(),
      meta: meta
    })
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
  } catch (error) {
    console.error(error)
    message.error(error.message)
    state.searchLoading = false
  }
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
      knowledgeBaseApi.deleteDatabase(databaseId.value)
        .then(data => {
          console.log(data)
          message.success(data.message || '删除成功')
          router.push('/database')
        })
        .catch(error => {
          console.error(error)
          message.error(error.message || '删除失败')
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
  // 先打开弹窗
  if (record.status !== 'done') {
    message.error('文件未处理完成，请稍后再试');
    return;
  }
  state.fileDetailModalVisible = true;
  selectedFile.value = {
    ...record,
    lines: []
  };

  // 设置加载状态
  state.fileDetailLoading = true;
  state.lock = true;

  try {
    knowledgeBaseApi.getDocumentDetail(databaseId.value, record.file_id)
      .then(data => {
        console.log(data);
        if (data.status == "failed") {
          message.error(data.message);
          state.fileDetailModalVisible = false;
          return;
        }
        selectedFile.value = {
          ...record,
          lines: data.lines || []
        };
      })
      .catch(error => {
        console.error(error);
        message.error(error.message);
        state.fileDetailModalVisible = false;
      })
      .finally(() => {
        state.fileDetailLoading = false;
        state.lock = false;
      });
  } catch (error) {
    console.error(error);
    message.error('获取文件详情失败!!!!');
    state.fileDetailLoading = false;
    state.lock = false;
    state.fileDetailModalVisible = false;
  }
}

const formatRelativeTime = (timestamp, offset = 0) => {
    // 如果调整为东八区时间（UTC+8），则offset为8，否则为0
    const timezoneOffset = offset * 60 * 60 * 1000; // 东八区偏移量（毫秒）
    const adjustedTimestamp = timestamp + timezoneOffset;

    const now = Date.now();
    const secondsPast = (now - adjustedTimestamp) / 1000;

    if (secondsPast < 60) {
        return Math.round(secondsPast) + ' 秒前';
    } else if (secondsPast < 3600) {
        return Math.round(secondsPast / 60) + ' 分钟前';
    } else if (secondsPast < 86400) {
        return Math.round(secondsPast / 3600) + ' 小时前';
    } else {
        const date = new Date(adjustedTimestamp);
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
  state.databaseLoading = true
  return new Promise((resolve, reject) => {
    knowledgeBaseApi.getDatabaseInfo(db_id)
      .then(data => {
        database.value = data
        resolve(data)
      })
      .catch(error => {
        console.error(error)
        message.error(error.message || '获取数据库信息失败')
        reject(error)
      })
      .finally(() => {
        state.lock = false
        state.databaseLoading = false
      })
  })
}

const deleteFile = (fileId) => {
  state.lock = true
  console.debug("deleteFile", databaseId.value, fileId)
  knowledgeBaseApi.deleteFile(databaseId.value, fileId)
    .then(data => {
      console.log(data)
      message.success(data.message || '删除成功')
      getDatabaseInfo()
    })
    .catch(error => {
      console.error(error)
      message.error(error.message || '删除失败')
    })
    .finally(() => {
      state.lock = false
    })
}


const handleDeleteFile = (fileId) => {
  console.log(fileId)
  //删除提示
  Modal.confirm({
    title: '删除文件',
    content: '确定要删除该文件吗？',
    okText: '确认',
    cancelText: '取消',
    onOk: () => deleteFile(fileId),
    onCancel: () => {
      console.log('Cancel');
    },
  });
}


// 批量删除处理函数
const handleBatchDelete = () => {
  if (!canBatchDelete.value) {
    message.info('没有可删除的文件');
    return;
  }

  const files = database.value.files || {};
  const fileCount = selectedRowKeys.value.length;

  Modal.confirm({
    title: '批量删除文件',
    content: `确定要删除选中的 ${fileCount} 个文件吗？`,
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      state.batchDeleting = true;
      try {
        const promises = selectedRowKeys.value
          .filter(fileId => {
            const file = files[fileId];
            return !(file.status === 'processing' || file.status === 'waiting');
          })
          .map(fileId =>
            deleteFile(fileId)
          );

        const results = await Promise.allSettled(promises);

        const succeeded = results.filter(r => r.status === 'fulfilled').length;
        const failed = results.filter(r => r.status === 'rejected').length;

        if (succeeded > 0) {
          message.success(`成功删除 ${succeeded} 个文件`);
        }
        if (failed > 0) {
          message.error(`${failed} 个文件删除失败`);
        }

        selectedRowKeys.value = []; // 清空选择
        getDatabaseInfo(); // 刷新列表状态
      } catch (error) {
        console.error('批量删除出错:', error);
        message.error('批量删除过程中发生错误');
      } finally {
        state.batchDeleting = false;
      }
    },
  });
};

const chunkParams = ref({
  chunk_size: 1000,
  chunk_overlap: 200,
  enable_ocr: 'disable',
})

// "生成分块" - 新的统一方法
const addFiles = (items, contentType = 'file') => {
  if (items.length === 0) {
    message.error(contentType === 'file' ? '请先上传文件' : '请输入有效的网页链接');
    return;
  }

  state.chunkLoading = true;

  // 设置内容类型
  const params = {
    ...chunkParams.value,
    content_type: contentType
  };

  knowledgeBaseApi.addFiles({
    db_id: databaseId.value,
    items: items,
    params: params
  })
  .then(data => {
    console.log('处理结果:', data);
    if (data.status === 'success') {
      const itemType = contentType === 'file' ? '文件' : 'URL';
      message.success(data.message || `${itemType}已提交处理，请稍后在列表刷新查看状态`);

      // 清空输入
      if (contentType === 'file') {
        fileList.value = [];
      } else {
        urlList.value = '';
      }

      addFilesModalVisible.value = false;
      getDatabaseInfo();
    } else {
      message.error(data.message || '处理失败');
    }
  })
  .catch(error => {
    console.error(error);
    message.error(error.message || '处理请求失败');
  })
  .finally(() => {
    state.chunkLoading = false;
  });
};

// "生成分块" - 修改后的逻辑（文件）
const handleFiles = () => {
  console.log(fileList.value);
  const files = fileList.value.filter(file => file.status === 'done').map(file => file.response.file_path);
  console.log(files);
  addFiles(files, 'file');
}

// "生成分块" - 修改后的逻辑（URL）
const handleUrls = () => {
  const urls = urlList.value.split('\n')
    .map(url => url.trim())
    .filter(url => url.length > 0 && (url.startsWith('http://') || url.startsWith('https://')));

  if (urls.length === 0) {
    message.error('请输入有效的网页链接（必须以http://或https://开头）');
    return;
  }

  addFiles(urls, 'url');
};

const columns = [
  // { title: '文件ID', dataIndex: 'file_id', key: 'file_id' },
  { title: '文件名', dataIndex: 'filename', key: 'filename', ellipsis: true },
  { title: '上传时间', dataIndex: 'created_at', key: 'created_at', width: 150 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 80 },
  { title: '类型', dataIndex: 'type', key: 'type', width: 80 },
  { title: '操作', key: 'action', dataIndex: 'file_id', width: 150 }
];

watch(() => route.params.database_id, (newId) => {
    databaseId.value = newId;
    console.log(newId)
    stopAutoRefresh();
    getDatabaseInfo().then(() => {
      startAutoRefresh();
    });
  }
);

// 检测到 meta 变化时重新查询
watch(() => meta, () => {
  filterQueryResults()
}, { deep: true })

// 添加更多示例查询
const queryExamples = ref([
  '孕妇应该避免吃哪些水果？',
  '荔枝应该怎么清洗？'
]);

// 使用示例查询的方法
const useQueryExample = (example) => {
  queryText.value = example;
  onQuery();
};

onMounted(() => {
  getDatabaseInfo();
  startAutoRefresh();
})

// 添加 onUnmounted 钩子，在组件卸载时清除定时器
onUnmounted(() => {
  stopAutoRefresh();
})

const uploadMode = ref('file');
const urlList = ref('');

const chunkData = () => {
  if (uploadMode.value === 'file') {
    handleFiles();
  } else if (uploadMode.value === 'url') {
    handleUrls();
  }
}

const getAuthHeaders = () => {
  const userStore = useUserStore();
  return userStore.getAuthHeaders();
};

// 编辑知识库表单
const editModalVisible = ref(false);
const editFormRef = ref(null);
const editForm = reactive({
  name: '',
  description: ''
});

const rules = {
  name: [{ required: true, message: '请输入知识库名称' }]
};

// 分块参数配置弹窗
const chunkConfigModalVisible = ref(false);
const tempChunkParams = ref({
  chunk_size: 1000,
  chunk_overlap: 200,
});

// 添加文件弹窗
const addFilesModalVisible = ref(false);

// 显示编辑对话框
const showEditModal = () => {
  editForm.name = database.value.name || '';
  editForm.description = database.value.description || '';
  editModalVisible.value = true;
};

// 提交编辑表单
const handleEditSubmit = () => {
  editFormRef.value.validate().then(() => {
    updateDatabaseInfo();
  }).catch(err => {
    console.error('表单验证失败:', err);
  });
};

// 更新知识库信息
const updateDatabaseInfo = async () => {
  try {
    state.lock = true;
    const response = await knowledgeBaseApi.updateDatabaseInfo(databaseId.value, {
      name: editForm.name,
      description: editForm.description
    });

    message.success('知识库信息更新成功');
    editModalVisible.value = false;
    await getDatabaseInfo(); // 刷新数据
  } catch (error) {
    console.error(error);
    message.error(error.message || '更新失败');
  } finally {
    state.lock = false;
  }
};

// 显示分块参数配置弹窗
const showChunkConfigModal = () => {
  tempChunkParams.value = {
    chunk_size: chunkParams.value.chunk_size,
    chunk_overlap: chunkParams.value.chunk_overlap,
  };
  chunkConfigModalVisible.value = true;
};

// 处理分块参数配置提交
const handleChunkConfigSubmit = () => {
  chunkParams.value.chunk_size = tempChunkParams.value.chunk_size;
  chunkParams.value.chunk_overlap = tempChunkParams.value.chunk_overlap;
  chunkConfigModalVisible.value = false;
  message.success('分块参数配置已更新');
};

// 显示添加文件弹窗
const showAddFilesModal = () => {
  addFilesModalVisible.value = true;
};





// 选中的行
const selectedRowKeys = ref([]);

// 行选择改变处理
const onSelectChange = (keys) => {
  selectedRowKeys.value = keys;
};

// 获取复选框属性
const getCheckboxProps = (record) => ({
  disabled: state.lock || record.status === 'processing' || record.status === 'waiting',
});



// 计算是否可以批量删除
const canBatchDelete = computed(() => {
  const files = database.value.files || {};
  return selectedRowKeys.value.some(key => {
    const file = files[key];
    return !(state.lock || file.status === 'processing' || file.status === 'waiting');
  });
});



// 开始自动刷新
const startAutoRefresh = () => {
  if (state.autoRefresh && !state.refreshInterval) {
    state.refreshInterval = setInterval(() => {
      getDatabaseInfo();
    }, 1000);
  }
};

// 停止自动刷新
const stopAutoRefresh = () => {
  if (state.refreshInterval) {
    clearInterval(state.refreshInterval);
    state.refreshInterval = null;
  }
};

// 切换自动刷新状态
const toggleAutoRefresh = (checked) => {
  if (checked) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
};


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
        padding-top: 12px;
        padding-right: 16px;
        border: 1px solid var(--main-light-3);
        background-color: var(--main-light-6);
        border-radius: 8px;
        padding: 16px;
        margin-right: 8px;

        .params-title {
          margin-top: 0;
          margin-bottom: 16px;
          color: var(--main-color);
          font-size: 18px;
          text-align: center;
          font-weight: bold;
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
      height: 48px;
      padding: 12px 16px;
      border: 2px solid var(--main-300);
      border-radius: 8px;
      box-shadow: 1px 1px 1px 1px var(--main-light-3);

      &:focus {
        border-color: var(--main-color);
        outline: none;
      }
    }

    button.btn-query {
      height: 48px;
      width: 100px;
    }
  }

  .query-examples-container {
    margin-bottom: 20px;
    padding: 12px;
    background: var(--main-light-6);
    border-radius: 8px;
    border: 1px solid var(--main-light-3);

    .examples-title {
      font-weight: bold;
      margin-bottom: 10px;
      color: var(--main-color);
    }

    .query-examples {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 10px 0 0;

      .ant-btn {
        font-size: 14px;
        padding: 4px 12px;
        height: auto;
        background-color: var(--gray-200);
        border: none;
        color: var(--gray-800);

        &:hover {
          color: var(--main-color);
        }
      }
    }
  }

  .query-test {
    display: flex;
    flex-direction: column;
    border-radius: 12px;
    word-break: break-all;
    word-break: break-word; /* 非标准，但某些浏览器支持 */
    overflow-wrap: break-word; /* 标准写法 */
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



.my-table {
  button.ant-btn-link {
    padding: 0;
  }

  .span-type {
    color: white;
    padding: 2px 4px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: bold;
    opacity: 0.8;
    user-select: none;
    background: #005F77;
  }

  .pdf {
    background: #005F77;
  }

  .txt {
    background: #068033;
  }

  .docx, .doc {
    background: #2C59B7;
  }

  .md {
    background: #020817;
  }



  button.main-btn {
    font-weight: bold;
    font-size: 14px;
    color: var(--gray-800);
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

.file-detail-content {
  max-height: 60vh;
  overflow-y: auto;
  // padding: 0 10px;
}

.custom-class .line-text {
  padding: 10px;
  border-radius: 4px;
  margin: 8px 0;
  background-color: var(--gray-100);

  &:hover {
    background-color: var(--main-light-4);
  }
}

.add-files-content {
  .upload-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    gap: 20px;

    .source-selector {
      display: flex;
      gap: 10px;

      .upload-mode-selector {
        cursor: pointer;
        padding: 4px 16px;
        border-radius: 8px;
        background-color: var(--main-light-4);
        border: 1px solid var(--main-light-3);
        transition: all 0.2s ease;
        &.active {
          color: var(--main-color);
          background-color: var(--main-10);
          border-color: var(--main-color);
        }
      }
    }

    .config-controls {
      .ant-btn {
        border-color: var(--main-light-3);
        color: var(--gray-700);
        &:hover {
          border-color: var(--main-color);
          color: var(--main-color);
        }
      }
    }
  }

  .ocr-config {
    margin-bottom: 16px;
    padding: 12px 16px;
    background-color: var(--main-light-6);
    border-radius: 8px;
    border: 1px solid var(--main-light-3);

    .ant-form-item {
      margin-bottom: 0;

      .ant-form-item-label {
        color: var(--gray-800);
        font-weight: 500;
      }
    }

    .param-description {
      color: var(--gray-600);
      font-size: 12px;
      margin-left: 12px;
    }
  }

  .upload {
    margin-bottom: 20px;
    .upload-dragger {
      margin: 0px;
      min-height: 200px;
    }
  }

  .url-input {
    margin-bottom: 20px;

    .ant-textarea {
      border-color: var(--main-light-3);
      background-color: #fff;
      font-family: monospace;
      resize: vertical;
    }

    .ant-textarea:hover,
    .ant-textarea:focus {
      border-color: var(--main-color);
    }

    .url-hint {
      font-size: 13px;
      color: var(--gray-600);
      margin-top: 5px;
      line-height: 1.5;
    }
  }
}

.chunk-config-content {
  .params-info {
    background-color: var(--main-light-4);
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 16px;

    p {
      margin: 0;
      font-size: 13px;
      line-height: 1.5;
      color: var(--gray-700);
    }
  }

  .ant-form-item {
    margin-bottom: 16px;

    .ant-form-item-label {
      padding-bottom: 6px;

      label {
        color: var(--gray-800);
        font-weight: 500;
        font-size: 15px;
      }
    }
  }

  .ant-input-number {
    border-radius: 6px;

    &:hover, &:focus {
      border-color: var(--main-color);
    }
  }

  .param-description {
    color: var(--gray-600);
    font-size: 12px;
    margin-top: 4px;
    margin-bottom: 0;
  }
}

.chunk-preview {
  margin-top: 20px;

  .preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;

    h3 {
      margin: 0;
      color: var(--main-color);
      font-size: 18px;
    }
  }

  .result-cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(600px, 1fr));
    gap: 12px;
    margin-top: 10px;
  }

  .chunk {
    background-color: var(--main-light-5);
    border: 1px solid var(--main-light-3);
    border-radius: 8px;
    padding: 16px;
    word-wrap: break-word;
    word-break: break-all;
    transition: all 0.2s ease;

    &:hover {
      background-color: var(--main-light-4);
      border-color: var(--main-light-2);
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
    }

    p {
      margin: 0;
      line-height: 1.6;

      strong {
        color: var(--main-color);
        margin-right: 6px;
      }
    }
  }
}

.url-input {
  margin-bottom: 20px;
}



.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}

.ant-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.auto-refresh-control {
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: 6px;

  span {
    color: var(--gray-700);
    font-weight: 500;
    font-size: 14px;
  }

  .ant-switch {
    &.ant-switch-checked {
      background-color: var(--main-color);
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

