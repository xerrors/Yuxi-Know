<template>
  <a-modal
    v-model:open="visible"
    title="从数据库导入"
    width="800px"
    @cancel="handleCancel"
  >
    <template #footer>
      <span><span style="color: red;">*</span>文件名：</span>
      <a-input
        v-model:value="databaseParams.filename"
        placeholder="输入文件名"
        style="width: 180px; margin-right: 12px;"
      />
      <a-button key="back" @click="handleCancel">取消</a-button>
      <a-button
        key="submit"
        type="primary"
        @click="importKnowledgeBaseFromDB"
        :loading="chunkLoading"
        :disabled="(databaseParams.fields.length === 0 || databaseParams.filename.trim() === '')"
      >
        导入知识库
      </a-button>
    </template>

    <div class="upload-database-content">
      <div class="upload-header">
        <div class="source-selector">
          <div class="upload-mode-selector" :class="{ active: true}">
            <FileOutlined /> 连接数据库
          </div>
        </div>
        <div class="config-controls">
          <!-- <a-button type="dashed" @click="showChunkConfigModal" v-if="!isGraphBased"> -->
          <a-button type="dashed" @click="showChunkConfigModal">
            <SettingOutlined /> 分块参数 ({{ chunkParams.chunk_size }}/{{ chunkParams.chunk_overlap }})
          </a-button>
        </div>
      </div>

      <div class="ocr-config">
        <a-form layout="horizontal">
          <a-form-item name="db_host">
            <div class="config-controls">
              <span><span style="color: red;">*</span>Host:</span>
              <a-input
                v-model:value="databaseParams.host"
                placeholder="输入数据库Host"
                style="width: 180px; margin-right: 12px;"
                :disabled="checkedDatabaseConnection"
              />
              <span><span style="color: red;">*</span>Port:</span>
              <a-input
                v-model:value="databaseParams.port"
                placeholder="输入数据库Port"
                style="width: 100px; margin-right: 12px;"
                :disabled="checkedDatabaseConnection"
              />
              <span><span style="color: red;">*</span>User:</span>
              <a-input
                v-model:value="databaseParams.user"
                placeholder="输入数据库User"
                style="width: 100px; margin-right: 12px;"
                :disabled="checkedDatabaseConnection"
              />
              <span><span style="color: red;">*</span>Password:</span>
              <a-input
                v-model:value="databaseParams.password"
                placeholder="输入数据库Password"
                style="width: 100px; margin-right: 12px;"
                type="password"
                :disabled="checkedDatabaseConnection"
              />
            </div>
          </a-form-item>
        </a-form>
      </div>

      <div class="qa-split-config" v-if="isQaSplitSupported">
        <a-form layout="horizontal">
          <a-form-item  name="use_qa_split">
            <div class="config-controls">
              <span class="param-label"><span style="color: red;">*</span>需要连接的数据库名称:</span>
              <a-input
                v-model:value="databaseParams.database"
                placeholder="输入数据库名称"
                style="width: 200px; margin-right: 12px;"
              />
              <a-button
                size="small"
                type="dashed"
                @click="checkDatabaseConnection"
                :loading="databaseConnectionChecking"
                :icon="h(CheckCircleOutlined)"
              >
                检查数据库服务
              </a-button>
            </div>
          </a-form-item>
        </a-form>
      </div>

      <div class="qa-split-config" v-if="isQaSplitSupported">
        <a-form layout="horizontal">
          <a-form-item  name="use_qa_split">
            <span><span style="color: red;">*</span>选择需要连接的数据库表: </span>
            <a-select
              v-model:value="databaseParams.table"
              :options="enableTableOptions"
              style="width: 220px; margin-right: 12px;"
            />
          </a-form-item>
        </a-form>
      </div>

      <!-- 表字段网格展示 -->
      <div class="qa-split-config" v-if="databaseParams.table && databaseParams.table !== 'disable'">
        <div class="table-cards">
          <!-- <a-empty v-if="!state.database.tables || state.database.tables.length === 0" description="暂无数据库表" /> -->
          <a-row :gutter="[16, 16]">
            <a-col
              v-for="(desc,field) in tableData[[databaseParams.table]]"
              :key="field"
              :xs="24"
              :sm="12"
              :md="8"
              :lg="6"
            >
              <a-card
                size="small"
                hoverable
                :class="{ 'table-card-selected': databaseParams.fields.includes(field) }"
                @click="toggleField(field)"
              >
                <div class="table-card-content">
                  <div class="checkbox-container">
                    <a-checkbox
                      :checked="databaseParams.fields.includes(field)"
                      @click.stop
                      @change="(e) => toggleField(field)"
                    />
                  </div>
                  <div class="table-info">
                    <div class="table-description">{{ desc || '暂无描述' }}</div>
                    <div class="table-name">{{ field }}</div>
                  </div>
                </div>
              </a-card>
            </a-col>
          </a-row>
        </div>
      </div>
    </div>
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
          <a-input-number v-model:value="databaseParams.chunk_params.chunk_size" :min="100" :max="10000" style="width: 100%;" />
          <p class="param-description">每个文本片段的最大字符数</p>
        </a-form-item>
        <a-form-item label="Chunk Overlap" name="chunk_overlap">
          <a-input-number v-model:value="databaseParams.chunk_params.chunk_overlap" :min="0" :max="1000" style="width: 100%;" />
          <p class="param-description">相邻文本片段间的重叠字符数</p>
        </a-form-item>
        <!-- <a-form-item v-if="isQaSplitSupported" label="QA分割模式" name="use_qa_split">
          <a-switch v-model:checked="tempChunkParams.use_qa_split" />
          <p class="param-description">启用后将按QA对分割，忽略上述chunk大小设置</p>
        </a-form-item>
        <a-form-item v-if="tempChunkParams.use_qa_split && isQaSplitSupported" label="QA分隔符" name="qa_separator">
          <a-input v-model:value="tempChunkParams.qa_separator" placeholder="输入QA分隔符" style="width: 100%;" />
          <p class="param-description">用于分割不同QA对的分隔符</p>
        </a-form-item> -->
      </a-form>
    </div>
  </a-modal>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { message, Upload } from 'ant-design-vue';
import { useUserStore } from '@/stores/user';
import { useDatabaseStore } from '@/stores/database';
import { fileApi, databaseApi } from '@/apis/knowledge_api';
import {
  FileOutlined,
  LinkOutlined,
  SettingOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons-vue';
import { h } from 'vue';

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
});

const emit = defineEmits(['update:visible']);

const store = useDatabaseStore();


const toggleField= (field) => {
  if (databaseParams.value.fields.includes(field)) {
    databaseParams.value.fields = databaseParams.value.fields.filter(t => t !== field);
  } else {
    // 最多只能选3个
    if (databaseParams.value.fields.length >= 3) {
      message.warning('最多只能选择3个字段');
      return;
    }
    databaseParams.value.fields.push(field);
  }
}


onMounted(() => {
});

const visible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value)
});

const databaseId = computed(() => store.databaseId);
const kbType = computed(() => store.database.kb_type);
const chunkLoading = computed(() => store.state.chunkLoading);

const databaseConnectionChecking = ref(false);

const tableData = ref({});

// 数据库参数
const databaseParams = ref({
  host: '127.0.0.1',
  port: '3306',
  user: 'root',
  password: 'root',
  database: '',
  table: 'disable',
  fields: ref([]),
  filename:'',
  // enable_table: 'disable',
  chunk_params: ref({
    chunk_size: 1000,
    chunk_overlap: 200,
  })
});


const defaultDatabaseParams = ref({
  host: '127.0.0.1',
  port: '3306',
  user: 'root',
  password: 'root',
  database: '',
  table: 'disable',
  fields: ref([]),
  filename:'',
  // enable_table: 'disable',
  chunk_params: ref({
    chunk_size: 1000,
    chunk_overlap: 200,
  })
});

// 分块参数
const chunkParams = ref({
  chunk_size: 1000,
  chunk_overlap: 200,
  enable_ocr: 'disable',
  use_qa_split: false,
  qa_separator: '\n\n\n',
});

// 分块参数配置弹窗
const chunkConfigModalVisible = ref(false);

// 临时分块参数（用于配置弹窗）
const tempChunkParams = ref({
  chunk_size: 1000,
  chunk_overlap: 200,
  use_qa_split: false,
  qa_separator: '\n\n\n',
});

// 计算属性：是否支持QA分割
const isQaSplitSupported = computed(() => {
  const type = kbType.value?.toLowerCase();
  return type === 'milvus';
});

const isGraphBased = computed(() => {
  const type = kbType.value?.toLowerCase();
  return type === 'lightrag';
});


const enableTableOptions = ref([
    {
    value: 'disable',
    label: '不启用',
    title: '不启用'
  }
]);

const defaultEnableTableOptions = ref([
    {
    value: 'disable',
    label: '不启用',
    title: '不启用'
  }
]);



const showChunkConfigModal = () => {
  tempChunkParams.value = {
    chunk_size: chunkParams.value.chunk_size,
    chunk_overlap: chunkParams.value.chunk_overlap,
    use_qa_split: isQaSplitSupported.value ? chunkParams.value.use_qa_split : false,
    qa_separator: chunkParams.value.qa_separator,
  };
  chunkConfigModalVisible.value = true;
};

const handleChunkConfigSubmit = () => {
  chunkParams.value.chunk_size = tempChunkParams.value.chunk_size;
  chunkParams.value.chunk_overlap = tempChunkParams.value.chunk_overlap;
  // 只有支持QA分割的知识库类型才保存QA分割配置
  if (isQaSplitSupported.value) {
    chunkParams.value.use_qa_split = tempChunkParams.value.use_qa_split;
    chunkParams.value.qa_separator = tempChunkParams.value.qa_separator;
  } else {
    chunkParams.value.use_qa_split = false;
  }
  chunkConfigModalVisible.value = false;
  message.success('分块参数配置已更新');
};

const checkedDatabaseConnection = ref(false);


const checkDatabaseConnection = async () => {
  if (databaseConnectionChecking.value) return;
  checkedDatabaseConnection.value = false
  databaseConnectionChecking.value = true;
  try {
    const connectionData = await databaseApi.getDatabaseConnectionTables(databaseParams.value);
    console.log('数据库连接检查结果:', connectionData);
    const status = connectionData.status;
    if (status === 'failed') {
      message.error('数据库连接检查失败');
    }else {
      message.success('数据库连接检查成功');
      const firstTableKey = Object.keys(connectionData.result)[0];
      if (firstTableKey) {
        // databaseParams.value.enable_table = firstTableKey;
        databaseParams.value.table = firstTableKey;
      }
      enableTableOptions.value = Object.entries(connectionData.result).map(([key, value]) => ({
        value: key,
        label: `${key}:${value}`,
        title: `${key}:${value}`
      }));

      tableData.value = connectionData.field_result;
      console.log('tableData', tableData.value);
      checkedDatabaseConnection.value = true;
    }
  } catch (error) {
    console.error('数据库连接检查失败:', error);
    message.error('数据库连接检查失败');
  } finally {
    databaseConnectionChecking.value = false;
  }
};

const handleCancel = () => {
  emit('update:visible', false);
  defaultSettings();
};

const defaultSettings = () => {
  checkedDatabaseConnection.value = false;
  databaseParams.value.host = '127.0.0.1';
  databaseParams.value.port = '3306';
  databaseParams.value.user = 'root';
  databaseParams.value.password = 'root';
  databaseParams.value.database = '';
  databaseParams.value.table = 'disable';
  databaseParams.value.filename = '';
  databaseParams.value.fields= [];
  // databaseParams.value.chunk_params.chunk_size = 1000;
  // databaseParams.value.chunk_params.chunk_overlap = 200;

  enableTableOptions.value = [
      {
      value: 'disable',
      label: '不启用',
      title: '不启用'
    }
  ]
  tableData.value = {};
}

const importKnowledgeBaseFromDB = async () => {
  if (!databaseConnectionChecking) {return ;}
  try {
    console.log('数据库参数', databaseParams.value);
    const importData = await databaseApi.importKnowledgeBaseFromDB(databaseId.value, databaseParams.value);
    console.log('数据库连接检查结果:', importData);
  } catch (error) {
    console.error('数据库连接检查失败:', error);
    message.error(error);
  } finally {
    emit('update:visible', false);
    defaultSettings();
    store.getDatabaseInfo()
  }
};


</script>

<style lang="less" scoped>
.upload-database-content {
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  height: 100%;

  .ant-form-item {
    margin: 0;
  }
}

.upload-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.source-selector {
  display: flex;
  gap: 12px;
}

.upload-mode-selector {
  padding: 8px 16px;
  border: 1px solid var(--gray-300);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s;
}

.upload-mode-selector:hover {
  border-color: var(--main-color);
}

.upload-mode-selector.active {
  border-color: var(--main-color);
  background-color: var(--main-30);
  color: var(--main-color);
}

.config-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ocr-config,
.qa-split-config {
  margin-bottom: 20px;
  padding: 16px;
  background-color: var(--gray-50);
  border-radius: 6px;
}

.toggle-controls {
  display: flex;
  align-items: center;
}

.param-description {
  font-size: 12px;
  color: var(--gray-600);
  margin-top: 4px;
}

.ocr-warning {
  color: #faad14;
}

.ocr-healthy {
  color: #52c41a;
}

.upload-dragger {
  margin-bottom: 16px;
}

.url-hint {
  font-size: 12px;
  color: var(--gray-600);
  margin-top: 8px;
}

.chunk-config-content .params-info {
  margin-bottom: 16px;
}

// OCR警告提醒样式
.ocr-warning-alert {
  margin: 12px 0;
  padding: 8px 12px;
  background: #fff7e6;
  border: 1px solid #ffd666;
  border-radius: 4px;
  color: #d46b08;
  font-size: 13px;
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
</style>
