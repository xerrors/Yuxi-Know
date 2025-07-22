<template>
<div>
  <HeaderComponent
    :title="database.name || '数据库信息'"
    :loading="state.databaseLoading"
  >
    <template #left>
      <a-button type="text" @click="backToDatabase">
        <LeftOutlined />
      </a-button>
    </template>
    <template #actions>
      <a-button type="text" @click="showEditModal">
        <EditOutlined />
      </a-button>
    </template>
  </HeaderComponent>

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
            <div class="ocr-controls">
              <a-select
                v-model:value="chunkParams.enable_ocr"
                :options="enable_ocr_options"
                style="width: 220px; margin-right: 12px;"
                :disabled="state.ocrHealthChecking"
              />
              <a-button
                size="small"
                type="dashed"
                @click="checkOcrHealth"
                :loading="state.ocrHealthChecking"
                :icon="h(CheckCircleOutlined)"
              >
                检查OCR服务
              </a-button>
            </div>
            <div class="param-description">
              <div v-if="chunkParams.enable_ocr !== 'disable'" class="ocr-status-info">
                <span v-if="getSelectedOcrStatus() && getSelectedOcrStatus() !== 'healthy'" class="ocr-warning">
                  ⚠️ {{ getSelectedOcrMessage() }}
                </span>
                <span v-else-if="getSelectedOcrStatus() === 'healthy'" class="ocr-healthy">
                  ✅ OCR服务运行正常
                </span>
              </div>
            </div>
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
          :action="'/api/knowledge/files/upload?db_id=' + databaseId"
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
          <!-- 数据库信息 -->
          <div class="database-info">
            <a-tag
              :color="getKbTypeColor(database.kb_type || 'lightrag')"
              class="kb-type-tag"
            >
              <component :is="getKbTypeIcon(database.kb_type || 'lightrag')" class="type-icon icon-16" />
              {{ getKbTypeLabel(database.kb_type || 'lightrag') }}
            </a-tag>
            <a-tag color="blue" v-if="database.embed_model">{{ database.embed_model }}</a-tag>
            <a-tag color="green" v-if="database.dimension">{{ database.dimension }}</a-tag>
            <span class="row-count">{{ database.files ? Object.keys(database.files).length : 0 }} 文件 · {{ database.db_id }}</span>
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
                <h3 class="params-title">
                  查询参数
                  <a-tag :color="getKbTypeColor(database.kb_type || 'lightrag')" size="small" style="margin-left: 8px;">
                    {{ getKbTypeLabel(database.kb_type || 'lightrag') }}
                  </a-tag>
                </h3>

                <!-- 加载状态 -->
                <div v-if="state.queryParamsLoading" class="params-loading">
                  <a-spin size="small" /> 加载参数中...
                </div>

                <!-- 动态参数 -->
                <div v-else class="params-group" v-for="param in queryParams" :key="param.key">
                  <div class="params-item">
                    <p>{{ param.label }}：</p>

                    <!-- 下拉选择器 -->
                    <a-select
                      v-if="param.type === 'select'"
                      v-model:value="meta[param.key]"
                      style="width: 120px;"
                    >
                      <a-select-option
                        v-for="option in param.options"
                        :key="option.value"
                        :value="option.value"
                      >
                        {{ option.label }}
                      </a-select-option>
                    </a-select>

                    <!-- 布尔开关 -->
                    <a-switch
                      v-else-if="param.type === 'boolean'"
                      v-model:checked="meta[param.key]"
                    />

                    <!-- 数字输入 -->
                    <a-input-number
                      v-else-if="param.type === 'number'"
                      size="small"
                      v-model:value="meta[param.key]"
                      :min="param.min || 0"
                      :max="param.max || 100"
                      :step="param.step || 1"
                      style="width: 100px;"
                    />

                    <!-- 文本输入 -->
                    <a-input
                      v-else
                      v-model:value="meta[param.key]"
                      size="small"
                      style="width: 120px;"
                    />
                  </div>
                  <div v-if="param.description" class="param-description">
                    {{ param.description }}
                  </div>
                </div>

                <!-- 如果没有参数 -->
                <div v-if="!state.queryParamsLoading && queryParams.length === 0" class="no-params">
                  <a-empty :image="false" description="暂无可配置的参数" />
                </div>
              </div>
            </div>
            <div class="sider-bottom">
            </div>
          </div>
        </div>
      </a-tab-pane>

      <a-tab-pane
        key="knowledge-graph"
        force-render
        :disabled="(database.kb_type || 'lightrag') !== 'lightrag'"
      >
        <template #tab>
          <span :class="{ 'disabled-tab': (database.kb_type || 'lightrag') !== 'lightrag' }">
            <Waypoints size="14" class="mr-3 bn-1px" />
            知识图谱
            <a-tag
              v-if="(database.kb_type || 'lightrag') !== 'lightrag'"
              size="small"
              color="orange"
              style="margin-left: 4px;"
            >
              仅限LightRAG
            </a-tag>
          </span>
        </template>
        <div class="knowledge-graph-container db-tab-container">
          <div v-if="(database.kb_type || 'lightrag') !== 'lightrag'" class="feature-disabled">
            <a-result
              status="info"
              title="图谱功能不可用"
              sub-title="知识图谱功能仅支持 LightRAG 类型的知识库"
            >
              <template #icon>
                <Waypoints size="48" style="color: #1890ff;" />
              </template>
              <template #extra>
                <p>当前知识库类型：{{ getKbTypeLabel(database.kb_type || 'lightrag') }}</p>
                <p>如需使用图谱功能，请创建 LightRAG 类型的知识库。</p>
              </template>
            </a-result>
          </div>
          <KnowledgeGraphViewer
            v-else
            :initial-database-id="databaseId"
            :hide-db-selector="true"
          />
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
import { onMounted, reactive, ref, watch, toRaw, onUnmounted, computed, h } from 'vue';
import { message, Modal } from 'ant-design-vue';
import { useRoute, useRouter } from 'vue-router';
import { useConfigStore } from '@/stores/config'
import { useUserStore } from '@/stores/user'
import { databaseApi, documentApi, queryApi, fileApi } from '@/apis/knowledge_api'
import { ocrApi } from '@/apis/system_api'
import {
  ReadOutlined,
  LeftOutlined,
  CheckCircleFilled,
  CheckCircleOutlined,
  HourglassFilled,
  CloseCircleFilled,
  ClockCircleFilled,
  DeleteOutlined,
  SearchOutlined,
  LoadingOutlined,
  FileOutlined,
  LinkOutlined,
  EditOutlined,
  PlusOutlined,
  SettingOutlined,
  DatabaseOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import HeaderComponent from '@/components/HeaderComponent.vue';
import KnowledgeGraphViewer from '@/components/KnowledgeGraphViewer.vue';
import { Waypoints, Database, Zap } from 'lucide-vue-next';



const route = useRoute();
const router = useRouter();
const databaseId = ref(route.params.database_id);
const database = ref({});

const fileList = ref([]);
const selectedFile = ref(null);

// 查询测试
const queryText = ref('');
const queryResult = ref(null)
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
  queryParamsLoading: false,
  ocrHealthChecking: false,
});

// OCR服务健康状态
const ocrHealthStatus = ref({
  rapid_ocr: { status: 'unknown', message: '' },
  mineru_ocr: { status: 'unknown', message: '' },
  paddlex_ocr: { status: 'unknown', message: '' }
});

// 动态查询参数
const queryParams = ref([])
const meta = reactive({});

// OCR健康检查函数
const checkOcrHealth = async () => {
  if (state.ocrHealthChecking) return;

  state.ocrHealthChecking = true;
  try {
    const healthData = await ocrApi.getHealth();
    ocrHealthStatus.value = healthData.services;
  } catch (error) {
    console.error('OCR健康检查失败:', error);
    message.error('OCR服务健康检查失败');
  } finally {
    state.ocrHealthChecking = false;
  }
};

// 生成OCR选项的计算属性，包含健康状态信息
const enable_ocr_options = computed(() => [
  {
    value: 'disable',
    label: '不启用',
    title: '不启用'
  },
  {
    value: 'onnx_rapid_ocr',
    label: getRapidOcrLabel(),
    title: 'ONNX with RapidOCR',
    disabled: ocrHealthStatus.value.rapid_ocr.status === 'unavailable' || ocrHealthStatus.value.rapid_ocr.status === 'error'
  },
  {
    value: 'mineru_ocr',
    label: getMinerULabel(),
    title: 'MinerU OCR',
    disabled: ocrHealthStatus.value.mineru_ocr.status === 'unavailable' || ocrHealthStatus.value.mineru_ocr.status === 'error'
  },
  {
    value: 'paddlex_ocr',
    label: getPaddleXLabel(),
    title: 'PaddleX OCR',
    disabled: ocrHealthStatus.value.paddlex_ocr.status === 'unavailable' || ocrHealthStatus.value.paddlex_ocr.status === 'error'
  },
]);

// OCR选项标签生成函数
const getRapidOcrLabel = () => {
  const status = ocrHealthStatus.value.rapid_ocr.status;
  const statusIcons = {
    'healthy': '✅',
    'unavailable': '❌',
    'error': '⚠️',
    'unknown': '❓'
  };
  return `${statusIcons[status] || '❓'} RapidOCR (ONNX)`;
};

const getMinerULabel = () => {
  const status = ocrHealthStatus.value.mineru_ocr.status;
  const statusIcons = {
    'healthy': '✅',
    'unavailable': '❌',
    'unhealthy': '⚠️',
    'timeout': '⏰',
    'error': '⚠️',
    'unknown': '❓'
  };
  return `${statusIcons[status] || '❓'} MinerU OCR`;
};

const getPaddleXLabel = () => {
  const status = ocrHealthStatus.value.paddlex_ocr.status;
  const statusIcons = {
    'healthy': '✅',
    'unavailable': '❌',
    'unhealthy': '⚠️',
    'timeout': '⏰',
    'error': '⚠️',
    'unknown': '❓'
  };
  return `${statusIcons[status] || '❓'} PaddleX OCR`;
};

// 获取当前选中OCR服务的状态
const getSelectedOcrStatus = () => {
  switch (chunkParams.value.enable_ocr) {
    case 'onnx_rapid_ocr':
      return ocrHealthStatus.value.rapid_ocr.status;
    case 'mineru_ocr':
      return ocrHealthStatus.value.mineru_ocr.status;
    case 'paddlex_ocr':
      return ocrHealthStatus.value.paddlex_ocr.status;
    default:
      return null;
  }
};

// 获取当前选中OCR服务的状态消息
const getSelectedOcrMessage = () => {
  switch (chunkParams.value.enable_ocr) {
    case 'onnx_rapid_ocr':
      return ocrHealthStatus.value.rapid_ocr.message;
    case 'mineru_ocr':
      return ocrHealthStatus.value.mineru_ocr.message;
    case 'paddlex_ocr':
      return ocrHealthStatus.value.paddlex_ocr.message;
    default:
      return '';
  }
};



// 验证OCR服务可用性
const validateOcrService = () => {
  if (chunkParams.value.enable_ocr === 'disable') {
    return true;
  }

  const status = getSelectedOcrStatus();
  if (status === 'unavailable' || status === 'error') {
    const ocrMessage = getSelectedOcrMessage();
    message.error(`OCR服务不可用: ${ocrMessage}`);
    return false;
  }

  return true;
};

// 加载知识库类型特定的查询参数
const loadQueryParams = async () => {
  if (!databaseId.value) return

  state.queryParamsLoading = true
  try {
    const response = await queryApi.getKnowledgeBaseQueryParams(databaseId.value)
    queryParams.value = response.params?.options || []

    // 初始化meta对象的默认值
    queryParams.value.forEach(param => {
      if (!(param.key in meta)) {
        meta[param.key] = param.default
      }
    })

    console.log('Loaded query params:', queryParams.value)
    console.log('Initialized meta:', meta)
  } catch (error) {
    console.error('Failed to load query params:', error)
    message.error('加载查询参数失败')
  } finally {
    state.queryParamsLoading = false
  }
}

const pagination = ref({
  pageSize: 15,
  current: 1,
  total: computed(() => database.value?.files?.length || 0),
  showSizeChanger: true,
  onChange: (page, pageSize) => pagination.value.current = page,
  showTotal: (total, range) => `共 ${total} 条`,
  onShowSizeChange: (current, pageSize) => pagination.value.pageSize = pageSize,
})

const onQuery = () => {
  console.log(queryText.value)
  state.searchLoading = true
  if (!queryText.value.trim()) {
    message.error('请输入查询内容')
    state.searchLoading = false
    return
  }
  meta.db_id = database.value.db_id

  try {
    queryApi.queryTest(database.value.db_id, queryText.value.trim(), meta)
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
      databaseApi.deleteDatabase(databaseId.value)
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
    documentApi.getDocumentInfo(databaseId.value, record.file_id)
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
    databaseApi.getDatabaseInfo(db_id)
      .then(async data => {
        database.value = data
        // 加载查询参数
        await loadQueryParams()
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
  return documentApi.deleteDocument(databaseId.value, fileId)
    .then(data => {
      console.log(data)
      message.success(data.message || '删除成功')
      getDatabaseInfo()
    })
    .catch(error => {
      console.error(error)
      message.error(error.message || '删除失败')
      throw error
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

  documentApi.addDocuments(databaseId.value, items, params)
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



const columns = [
  // { title: '文件ID', dataIndex: 'file_id', key: 'file_id' },
  { title: '文件名', dataIndex: 'filename', key: 'filename', ellipsis: true },
  { title: '上传时间', dataIndex: 'created_at', key: 'created_at', width: 150 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 80 },
  { title: '类型', dataIndex: 'type', key: 'type', width: 80 },
  { title: '操作', key: 'action', dataIndex: 'file_id', width: 150 }
];

watch(() => route.params.database_id, async (newId) => {
    databaseId.value = newId;
    console.log(newId)
    stopAutoRefresh();
    await getDatabaseInfo();
    startAutoRefresh();
  }
);


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
  // 初始化时检查OCR服务健康状态
  checkOcrHealth();
})

// 添加 onUnmounted 钩子，在组件卸载时清除定时器
onUnmounted(() => {
  stopAutoRefresh();
})

const uploadMode = ref('file');
const urlList = ref('');

const chunkData = () => {
  // 验证OCR服务可用性
  if (!validateOcrService()) {
    return;
  }

  if (uploadMode.value === 'file') {
    const files = fileList.value.filter(file => file.status === 'done').map(file => file.response.file_path);
    console.log(files);
    addFiles(files, 'file');
  } else if (uploadMode.value === 'url') {
    const urls = urlList.value.split('\n')
      .map(url => url.trim())
      .filter(url => url.length > 0 && (url.startsWith('http://') || url.startsWith('https://')));

    if (urls.length === 0) {
      message.error('请输入有效的网页链接（必须以http://或https://开头）');
      return;
    }

    addFiles(urls, 'url');
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
    const response = await databaseApi.updateDatabase(databaseId.value, {
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

const getKbTypeColor = (type) => {
  const colors = {
    lightrag: 'purple',
    chroma: 'orange',
    milvus: 'red'
  }
  return colors[type] || 'blue'
}


</script>

<style lang="less" scoped>
.database-info {
  margin: 8px 0 0;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;

  .kb-type-tag {
    display: flex;
    align-items: center;
    gap: 4px;
    .type-icon {
      margin-right: 4px;
      font-size: 12px;
      width: 14px;
      height: 14px;
    }
  }
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

.knowledge-graph-container {
  height: calc(100vh - 150px);
  min-height: 600px;
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
          font-size: 16px;
          font-weight: bold;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .params-loading {
          text-align: center;
          color: var(--gray-600);
          padding: 16px;
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

        .param-description {
          font-size: 12px;
          color: var(--gray-500);
          margin-top: 4px;
          line-height: 1.4;
        }

        .no-params {
          text-align: center;
          padding: 20px;
          color: var(--gray-500);
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

  .disabled-tab {
    opacity: 0.5;
    color: var(--gray-400);
  }
}

.params-item.col .ant-segmented {
  width: 100%;

  div.ant-segmented-group {
    display: flex;
    justify-content: space-around;
  }
}

// OCR配置相关样式
.ocr-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.ocr-status-info {
  margin-top: 8px;
  font-size: 12px;
}

.ocr-warning {
  color: #f5222d;
  display: flex;
  align-items: center;
  gap: 4px;
}

.ocr-healthy {
  color: #52c41a;
  display: flex;
  align-items: center;
  gap: 4px;
}

.param-description {
  color: var(--gray-600);
  font-size: 12px;
  margin-left: 8px;
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

.knowledge-graph-container {
  height: calc(100vh - 200px);

  .feature-disabled {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;

    .ant-result {
      p {
        margin: 4px 0;
        color: var(--gray-600);
      }
    }
  }

  :deep(.knowledge-graph-viewer) {
    height: 100%;

    .sigma-container {
      height: calc(100% - 80px);
    }
  }
}

</style>

