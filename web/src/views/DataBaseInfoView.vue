<template>
<div class="database-info-container">
  <HeaderComponent
    :title="database.name || '数据库信息加载中'"
    :loading="state.databaseLoading"
    class="database-info-header"
  >
    <template #left>
      <a-button @click="backToDatabase">
        <LeftOutlined />
      </a-button>
    </template>
    <template #behind-title>
      <a-button type="link" @click="showEditModal" :style="{ padding: '0px', color: 'inherit' }">
        <EditOutlined />
      </a-button>
    </template>
    <template #actions>
      <div class="header-info">
        <span class="db-id">ID:
          <span style="user-select: all;">{{ database.db_id || 'N/A' }}</span>
        </span>
        <span class="file-count">{{ database.files ? Object.keys(database.files).length : 0 }} 文件</span>
        <a-tag color="blue">{{ database.embed_info?.name }}</a-tag>
        <a-tag
          :color="getKbTypeColor(database.kb_type || 'lightrag')"
          class="kb-type-tag"
          size="small"
        >
          <component :is="getKbTypeIcon(database.kb_type || 'lightrag')" class="type-icon" />
          {{ getKbTypeLabel(database.kb_type || 'lightrag') }}
        </a-tag>
      </div>
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
        <a-form-item v-if="isQaSplitSupported" label="QA分割模式" name="use_qa_split">
          <a-switch v-model:checked="tempChunkParams.use_qa_split" />
          <p class="param-description">启用后将按QA对分割，忽略上述chunk大小设置</p>
        </a-form-item>
        <a-form-item v-if="tempChunkParams.use_qa_split && isQaSplitSupported" label="QA分隔符" name="qa_separator">
          <a-input v-model:value="tempChunkParams.qa_separator" placeholder="输入QA分隔符" style="width: 100%;" />
          <p class="param-description">用于分割不同QA对的分隔符</p>
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
        添加到知识库
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
                  ✅ {{ getSelectedOcrMessage() }}
                </span>
              </div>
            </div>
          </a-form-item>
        </a-form>
      </div>

      <div class="qa-split-config" v-if="isQaSplitSupported">
        <a-form layout="horizontal">
          <a-form-item label="QA分割模式" name="use_qa_split">
            <div class="toggle-controls">
              <a-switch
                v-model:checked="chunkParams.use_qa_split"
                style="margin-right: 12px;"
              />
              <span class="param-description">
                {{ chunkParams.use_qa_split ? '启用QA分割（忽略chunk大小设置）' : '使用普通分割模式' }}
              </span>
            </div>
          </a-form-item>
          <a-form-item
            v-if="chunkParams.use_qa_split"
            label="QA分隔符"
            name="qa_separator"
          >
            <a-input
              v-model:value="chunkParams.qa_separator"
              placeholder="输入QA分隔符"
              style="width: 200px; margin-right: 12px;"
            />
            <span class="param-description">
              用于分割不同QA对的分隔符，默认为3个换行符
            </span>
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

  <!-- Maximize Graph Modal -->
  <a-modal
    v-model:open="state.isGraphMaximized"
    :footer="null"
    :closable="false"
    width="100%"
    wrap-class-name="full-modal"
    :mask-closable="false"
  >
    <template #title>
      <div class="maximized-graph-header">
        <h3>知识图谱 (最大化)</h3>
        <a-button type="text" @click="toggleGraphMaximize">
          <CompressOutlined /> 退出最大化
        </a-button>
      </div>
    </template>
    <div class="maximized-graph-content">
      <div v-if="!isGraphSupported" class="graph-disabled">
        <div class="disabled-content">
          <h4>知识图谱不可用</h4>
          <p>当前知识库类型 "{{ getKbTypeLabel(database.kb_type || 'lightrag') }}" 不支持知识图谱功能。</p>
          <p>只有 LightRAG 类型的知识库支持知识图谱。</p>
        </div>
      </div>
      <KnowledgeGraphViewer
        v-else-if="state.isGraphMaximized"
        :initial-database-id="databaseId"
        :hide-db-selector="true"
      />
    </div>
  </a-modal>

  <!-- 文件详情弹窗 -->
  <a-modal
    v-model:open="state.fileDetailModalVisible"
    :title="selectedFile?.filename || '文件详情'"
    width="1200px"
    :footer="null"
  >
    <div class="file-detail-content" v-if="selectedFile">
      <div class="file-info-grid">
        <div class="info-item">
          <label>文件ID:</label>
          <span>{{ selectedFile.file_id }}</span>
        </div>
        <div class="info-item">
          <label>上传时间:</label>
          <span>{{ formatRelativeTime(Math.round(selectedFile.created_at*1000)) }}</span>
        </div>
        <div class="info-item">
          <label>处理状态:</label>
          <span class="status-badge" :class="selectedFile.status">
            {{ getStatusText(selectedFile.status) }} - {{ selectedFile.lines.length }} 行
          </span>
        </div>
      </div>

      <div class="file-content-section" v-if="selectedFile.lines && selectedFile.lines.length > 0">
        <h4>文件内容预览</h4>
        <div class="content-lines">
          <div
            v-for="(line, index) in selectedFile.lines"
            :key="index"
            class="content-line"
          >
            <span class="line-number">{{ index + 1 }}</span>
            <span class="line-text">{{ line.text || line }}</span>
          </div>
        </div>
      </div>

      <div v-else-if="state.fileDetailLoading" class="loading-container">
        <a-spin />
      </div>

      <div v-else class="empty-content">
        <p>暂无文件内容</p>
      </div>
    </div>
  </a-modal>

  <div class="unified-layout">
    <div class="left-panel" :style="{ width: leftPanelWidth + '%' }">
      <div class="panel-header">
        <div class="search-container">
          <a-button
            type="secondary"
            @click="showAddFilesModal"
            :loading="state.refrashing"
            :icon="h(PlusOutlined)"
          >添加文件</a-button>
        </div>
        <div class="panel-actions">
          <a-button
            type="text"
            @click="handleRefresh"
            :loading="state.refrashing"
            :icon="h(ReloadOutlined)"
            title="刷新"
          />
          <a-button
            @click="toggleAutoRefresh"
            size="small"
            :type="state.autoRefresh ? 'primary' : 'default'"
            title="自动刷新文件状态"
            class="auto-refresh-btn panel-action-btn"
          >
            Auto
          </a-button>
          <a-input
            v-model:value="filenameFilter"
            placeholder="搜索文件名"
            size="small"
            style="width: 120px; margin-right: 8px; border-radius: 6px; padding: 4px 8px;"
            allow-clear
            @change="onFilterChange"
          />
          <a-button
            type="text"
            @click="toggleRightPanel"
            :icon="h(ChevronLast)"
            title="切换右侧面板"
            class="panel-action-btn expanded"
            :class="{ 'active': state.rightPanelVisible }"
          />
        </div>
      </div>

      <div class="batch-actions-compact" v-if="selectedRowKeys.length > 0">
        <div class="batch-info">
          <span>{{ selectedRowKeys.length }} 项</span>
          <a-button
            type="text"
            size="small"
            @click="selectAllFailedFiles"
            :disabled="state.lock"
            title="选择所有失败的文件"
          >
            选择失败
          </a-button>
        </div>
        <a-button
          type="text"
          danger
          @click="handleBatchDelete"
          :loading="state.batchDeleting"
          :disabled="!canBatchDelete"
          :icon="h(DeleteOutlined)"
          title="批量删除"
        />
      </div>

      <a-table
        :columns="columnsCompact"
        :data-source="filteredFiles"
        row-key="file_id"
        class="my-table-compact"
        size="small"
        :pagination="paginationCompact"
        :row-selection="{
          selectedRowKeys: selectedRowKeys,
          onChange: onSelectChange,
          getCheckboxProps: getCheckboxProps
        }"
        :locale="{
          emptyText: emptyText
        }"
        @change="handleTableChange">
        <template #bodyCell="{ column, text, record }">
          <a-button v-if="column.key === 'filename'"  class="main-btn" type="link" @click="openFileDetail(record)">
            <component :is="getFileIcon(text)" :style="{ marginRight: '6px', color: getFileIconColor(text) }" />
            {{ text }}
          </a-button>
          <span v-else-if="column.key === 'type'" :class="['span-type', text]">{{ text?.toUpperCase() }}</span>
          <div v-else-if="column.key === 'status'" style="display: flex; align-items: center; justify-content: flex-end;">
            <CheckCircleFilled v-if="text === 'done'" style="color: #41A317;"/>
            <CloseCircleFilled v-else-if="text === 'failed'" style="color: #FF4D4F;"/>
            <HourglassFilled v-else-if="text === 'processing'" style="color: #1677FF;"/>
            <ClockCircleFilled v-else-if="text === 'waiting'" style="color: #FFCD43;"/>
          </div>

          <a-tooltip v-else-if="column.key === 'created_at'" :title="formatRelativeTime(Math.round(text*1000))" placement="left">
            <span>{{ formatRelativeTime(Math.round(text*1000)) }}</span>
          </a-tooltip>

          <div v-else-if="column.key === 'action'" style="display: flex; gap: 4px;">
            <a-button class="del-btn" type="text"
              @click="handleDeleteFile(record.file_id)"
              :disabled="state.lock || record.status === 'processing' || record.status === 'waiting'"
              :icon="h(DeleteOutlined)"
              title="删除"
              />
          </div>
          <span v-else>{{ text }}</span>
        </template>
      </a-table>
    </div>

    <div class="resize-handle" ref="resizeHandle"></div>

    <div class="right-panel" :style="{ width: (100 - leftPanelWidth) + '%', display: state.rightPanelVisible ? 'flex' : 'none' }">

      <div class="graph-section" :class="{ collapsed: !panels.graph.visible }" :style="computePanelStyles().graph" v-if="isGraphSupported" >
        <div class="section-header">
          <div class="header-left">
            <h3>知识图谱</h3>
            <div v-if="graphStats.displayed_nodes > 0 || graphStats.displayed_edges > 0" class="graph-stats">
              <a-tag color="blue" size="small">节点: {{ graphStats.displayed_nodes }}</a-tag>
              <a-tag color="green" size="small">边: {{ graphStats.displayed_edges }}</a-tag>
              <a-tag v-if="graphStats.is_truncated" color="red" size="small">已截断</a-tag>
            </div>
          </div>
          <div class="panel-actions">
            <a-button
              type="text"
              size="small"
              :icon="h(ReloadOutlined)"
              title="刷新视图"
              @click="refreshGraph"
              :disabled="!isGraphSupported"
            >
              刷新视图
            </a-button>
            <a-button
              type="text"
              size="small"
              :icon="h(DeleteOutlined)"
              title="清空视图"
              @click="clearGraph"
              :disabled="!isGraphSupported"
            >
              清空视图
            </a-button>
            <a-button
              type="text"
              size="small"
              :icon="h(ExpandOutlined)"
              title="最大化"
              @click="toggleGraphMaximize"
              :disabled="!isGraphSupported"
            >
              最大化
            </a-button>
            <a-button
              type="text"
              size="small"
              @click="togglePanel('graph')"
              title="折叠/展开"
            >
              <component :is="panels.graph.visible ? UpOutlined : DownOutlined" />
            </a-button>
          </div>
        </div>
        <div class="graph-container-compact content" v-show="panels.graph.visible">
          <div v-if="!isGraphSupported" class="graph-disabled">
            <div class="disabled-content">
              <h4>知识图谱不可用</h4>
              <p>当前知识库类型 "{{ getKbTypeLabel(database.kb_type || 'lightrag') }}" 不支持知识图谱功能。</p>
              <p>只有 LightRAG 类型的知识库支持知识图谱。</p>
            </div>
          </div>
          <KnowledgeGraphViewer
            v-else
            :initial-database-id="databaseId"
            :hide-db-selector="true"
            :hide-stats="true"
            @update:stats="handleStatsUpdate"
            ref="graphViewerRef"
          />
        </div>
      </div>
      <div class="resize-handle-horizontal" ref="resizeHandleHorizontal" v-show="panels.query.visible && panels.graph.visible"></div>

      <div class="query-section" :class="{ collapsed: !panels.query.visible }" :style="computePanelStyles().query">
        <div class="section-header">
          <h3>检索测试</h3>
          <div class="panel-actions">
            <a-popover trigger="click" placement="bottomRight" class="query-params-popover">
              <template #content>
                <div class="query-params-compact">
                  <div v-if="state.queryParamsLoading" class="params-loading">
                    <a-spin size="small" />
                  </div>
                  <div v-else class="params-grid">
                    <div v-for="param in queryParams" :key="param.key" class="param-item">
                      <label>{{ param.label }}:</label>
                      <a-select
                        v-if="param.type === 'select'"
                        v-model:value="meta[param.key]"
                        size="small"
                        style="width: 80px;"
                      >
                        <a-select-option
                          v-for="option in param.options"
                          :key="option.value"
                          :value="option.value"
                        >
                          {{ option.label }}
                        </a-select-option>
                      </a-select>
                      <a-switch
                        v-else-if="param.type === 'boolean'"
                        v-model:checked="meta[param.key]"
                        size="small"
                      />
                      <a-input-number
                        v-else-if="param.type === 'number'"
                        v-model:value="meta[param.key]"
                        size="small"
                        style="width: 60px;"
                        :min="param.min || 0"
                        :max="param.max || 100"
                      />
                    </div>
                  </div>
                </div>
              </template>
              <a-button
                type="text"
                size="small"
                :icon="h(SettingOutlined)"
                title="查询参数"
              >查询参数</a-button>
            </a-popover>
            <a-button
              type="text"
              size="small"
              @click="togglePanel('query')"
              title="折叠/展开"
            >
              <component :is="panels.query.visible ? UpOutlined : DownOutlined" />
            </a-button>
          </div>
        </div>

        <div class="query-content content" v-show="panels.query.visible">
          <div class="query-input-row">
            <a-textarea
              v-model:value="queryText"
              placeholder="输入查询内容"
              :auto-size="{ minRows: 3, maxRows: 6 }"
              class="compact-query-textarea"
            />
            <div class="query-actions">
              <div class="search-row">
                <a-button
                  @click="onQuery"
                  :loading="state.searchLoading"
                  class="search-button"
                >
                  <template #icon>
                    <SearchOutlined />
                  </template>
                  搜索
                </a-button>
                <div class="query-examples-compact">
                  <span class="examples-label">示例：</span>
                  <div class="examples-container">
                    <transition name="fade" mode="out-in">
                      <a-button
                        :key="currentExampleIndex"
                        @click="useQueryExample(queryExamples[currentExampleIndex])"
                        size="small"
                        class="example-btn"
                      >
                        {{ queryExamples[currentExampleIndex] }}
                      </a-button>
                    </transition>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="query-results" v-if="queryResult">
            {{ queryResult }}
          </div>
        </div>
      </div>
    </div>
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
  RightOutlined,
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
  ReloadOutlined,
  UpOutlined,
  DownOutlined,
  ExpandOutlined,
  CompressOutlined,
  FileTextFilled,
  FileImageFilled,
  FileMarkdownFilled,
  FilePdfFilled,
  FileWordFilled,
  FileExcelFilled,
  FileUnknownFilled,
} from '@ant-design/icons-vue'
import HeaderComponent from '@/components/HeaderComponent.vue';
import KnowledgeGraphViewer from '@/components/KnowledgeGraphViewer.vue';
import { Waypoints, Database, Zap, ChevronLast } from 'lucide-vue-next';



const route = useRoute();
const router = useRouter();
const databaseId = ref(route.params.database_id);
const database = ref({});

const fileList = ref([]);
const selectedFile = ref(null);

// 文件名过滤
const filenameFilter = ref('');

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
  batchDeleteProgress: { current: 0, total: 0 }, // 批量删除进度
  chunkLoading: false,
  autoRefresh: false,
  loading: false,
  queryParamsLoading: false,
  ocrHealthChecking: false,
  isGraphMaximized: false,
  rightPanelVisible: true, // 添加这一行
});

// 计算属性：是否支持知识图谱
const isGraphSupported = computed(() => {
  const kbType = database.value.kb_type?.toLowerCase();
  return kbType === 'lightrag';
});

// 计算属性：是否支持QA分割
const isQaSplitSupported = computed(() => {
  const kbType = database.value.kb_type?.toLowerCase();
  return kbType === 'chroma' || kbType === 'milvus';
});

// 切换图谱最大化状态
const toggleGraphMaximize = () => {
  state.isGraphMaximized = !state.isGraphMaximized;
};

// 图谱相关数据
const graphViewerRef = ref(null);
const graphStats = ref({
  displayed_nodes: 0,
  displayed_edges: 0,
  is_truncated: false
});

// 处理图谱统计信息更新
const handleStatsUpdate = (stats) => {
  graphStats.value = stats;
};

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
  // Remove db_id from meta to avoid duplicate parameter error
  const queryMeta = { ...toRaw(meta) }
  delete queryMeta.db_id

  try {
    queryApi.queryTest(database.value.db_id, queryText.value.trim(), queryMeta)
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

        // 如果当前知识库类型不支持QA分割，重置相关参数
        const kbType = data.kb_type?.toLowerCase();
        if (kbType !== 'chroma' && kbType !== 'milvus') {
          chunkParams.value.use_qa_split = false;
        }

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
      // message.success(data.message || '删除成功')
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
  const validFileIds = selectedRowKeys.value.filter(fileId => {
    const file = files[fileId];
    return file && !(file.status === 'processing' || file.status === 'waiting');
  });

  if (validFileIds.length === 0) {
    message.info('没有可删除的文件');
    return;
  }

  Modal.confirm({
    title: '批量删除文件',
    content: `确定要删除选中的 ${validFileIds.length} 个文件吗？`,
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      state.batchDeleting = true;
      state.batchDeleteProgress.current = 0;
      state.batchDeleteProgress.total = validFileIds.length;

      let successCount = 0;
      let failureCount = 0;

      // 显示初始进度
      let progressMessage = message.loading(`正在删除文件 0/${validFileIds.length}`, 0);

      try {
        // 逐个删除文件以显示进度
        for (let i = 0; i < validFileIds.length; i++) {
          const fileId = validFileIds[i];
          try {
            await deleteFile(fileId);
            successCount++;
          } catch (error) {
            console.error(`删除文件 ${fileId} 失败:`, error);
            failureCount++;
          }

          // 更新进度
          state.batchDeleteProgress.current = i + 1;
          progressMessage?.();

          // 显示当前进度，如果不是最后一个文件
          if (i + 1 < validFileIds.length) {
            progressMessage = message.loading(`正在删除文件 ${i + 1}/${validFileIds.length}`, 0);
          }
        }

        // 显示最终结果
        progressMessage?.();

        if (successCount > 0 && failureCount === 0) {
          message.success(`成功删除 ${successCount} 个文件`);
        } else if (successCount > 0 && failureCount > 0) {
          message.warning(`成功删除 ${successCount} 个文件，${failureCount} 个文件删除失败`);
        } else if (failureCount > 0) {
          message.error(`${failureCount} 个文件删除失败`);
        }

        selectedRowKeys.value = []; // 清空选择
        getDatabaseInfo(); // 刷新列表状态
      } catch (error) {
        progressMessage?.();
        console.error('批量删除出错:', error);
        message.error('批量删除过程中发生错误');
      } finally {
        state.batchDeleting = false;
        state.batchDeleteProgress.current = 0;
        state.batchDeleteProgress.total = 0;
      }
    },
  });
};

const chunkParams = ref({
  chunk_size: 1000,
  chunk_overlap: 200,
  enable_ocr: 'disable',
  use_qa_split: false,
  qa_separator: '\n\n\n',
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

watch(() => route.params.database_id, async (newId) => {
    databaseId.value = newId;
    console.log(newId)
    stopAutoRefresh();
    await getDatabaseInfo();
    startAutoRefresh();
  }
);

// 监听数据库信息变化，重置过滤条件
watch(() => database.value, () => {
  // 当数据库信息更新时，重置过滤条件和选中状态
  filenameFilter.value = '';
  selectedRowKeys.value = [];
  // 重置排序状态
  sortState.value.field = null;
  sortState.value.order = null;
  // 分页重置由 filteredFiles 计算属性自动处理
}, { deep: true });


// 添加更多示例查询
const queryExamples = ref([
  '孕妇应该避免吃哪些水果？',
  '荔枝应该怎么清洗？',
  '如何判断西瓜是否成熟？',
  '苹果有哪些营养价值？',
  '什么季节最适合吃梨？',
  '如何保存草莓以延长保质期？',
  '香蕉变黑后还能吃吗？',
  '橙子皮可以用来做什么？'
]);

// 当前示例索引
const currentExampleIndex = ref(0);

// 使用示例查询的方法
const useQueryExample = (example) => {
  queryText.value = example;
  onQuery();
};

// 示例轮播相关
let exampleCarouselInterval = null;
const startExampleCarousel = () => {
  if (exampleCarouselInterval) return;

  exampleCarouselInterval = setInterval(() => {
    currentExampleIndex.value = (currentExampleIndex.value + 1) % queryExamples.value.length;
  }, 6000); // 每6秒切换一次
};

const stopExampleCarousel = () => {
  if (exampleCarouselInterval) {
    clearInterval(exampleCarouselInterval);
    exampleCarouselInterval = null;
  }
};

// 组件挂载时启动示例轮播
onMounted(() => {
  getDatabaseInfo();
  startAutoRefresh();
  // 初始化时检查OCR服务健康状态
  checkOcrHealth();

  setTimeout(() => {
    if (isGraphSupported.value) {
      refreshGraph();
    }
  }, 800);

  // 添加拖拽事件监听
  if (resizeHandle.value) {
    resizeHandle.value.addEventListener('mousedown', handleMouseDown);
  }
  if (resizeHandleHorizontal.value) {
    resizeHandleHorizontal.value.addEventListener('mousedown', handleMouseDownHorizontal);
  }

  // 添加键盘事件监听
  document.addEventListener('keydown', handleKeyDown);

  // 启动示例轮播
  startExampleCarousel();
});

// 组件卸载时停止示例轮播
onUnmounted(() => {
  stopAutoRefresh();
  if (resizeHandle.value) {
    resizeHandle.value.removeEventListener('mousedown', handleMouseDown);
  }
  if (resizeHandleHorizontal.value) {
    resizeHandleHorizontal.value.removeEventListener('mousedown', handleMouseDownHorizontal);
  }
  document.removeEventListener('mousemove', handleMouseMove);
  document.removeEventListener('mouseup', handleMouseUp);
  document.removeEventListener('mousemove', handleMouseMoveHorizontal);
  document.removeEventListener('mouseup', handleMouseUpHorizontal);
  document.removeEventListener('keydown', handleKeyDown);

  // 停止示例轮播
  stopExampleCarousel();
});

// 拖拽调整大小功能
const handleMouseDown = () => {
  isDragging.value = true;
  document.addEventListener('mousemove', handleMouseMove);
  document.addEventListener('mouseup', handleMouseUp);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
};

const handleMouseMove = (e) => {
  if (!isDragging.value) return;

  const container = document.querySelector('.unified-layout');
  if (!container) return;

  const containerRect = container.getBoundingClientRect();
  const newWidth = ((e.clientX - containerRect.left) / containerRect.width) * 100;

  // 限制最小和最大宽度
  leftPanelWidth.value = Math.max(20, Math.min(60, newWidth));
};

const handleMouseUp = () => {
  isDragging.value = false;
  document.removeEventListener('mousemove', handleMouseMove);
  document.removeEventListener('mouseup', handleMouseUp);
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
};

const handleMouseDownHorizontal = () => {
  isDraggingVertical.value = true;
  document.addEventListener('mousemove', handleMouseMoveHorizontal);
  document.addEventListener('mouseup', handleMouseUpHorizontal);
  document.body.style.cursor = 'row-resize';
  document.body.style.userSelect = 'none';
};

const handleMouseMoveHorizontal = (e) => {
  if (!isDraggingVertical.value) return;

  const container = document.querySelector('.right-panel');
  if (!container) return;

  const containerRect = container.getBoundingClientRect();
  const newHeight = ((e.clientY - containerRect.top) / containerRect.height) * 100;

  rightPanelHeight.graph = Math.max(10, Math.min(90, newHeight));
  rightPanelHeight.query = 100 - rightPanelHeight.graph;
};

const handleMouseUpHorizontal = () => {
  isDraggingVertical.value = false;
  document.removeEventListener('mousemove', handleMouseMoveHorizontal);
  document.removeEventListener('mouseup', handleMouseUpHorizontal);
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
};


// 键盘事件处理
const handleKeyDown = (e) => {
  // 当按下ESC键时清空过滤条件
  if (e.key === 'Escape' && filenameFilter.value) {
    filenameFilter.value = '';
    selectedRowKeys.value = [];
    // 分页重置由 filteredFiles 计算属性自动处理
  }
};

// 清理事件监听
onUnmounted(() => {
  stopAutoRefresh();
  if (resizeHandle.value) {
    resizeHandle.value.removeEventListener('mousedown', handleMouseDown);
  }
  if (resizeHandleHorizontal.value) {
    resizeHandleHorizontal.value.removeEventListener('mousedown', handleMouseDownHorizontal);
  }
  document.removeEventListener('mousemove', handleMouseMove);
  document.removeEventListener('mouseup', handleMouseUp);
  document.removeEventListener('mousemove', handleMouseMoveHorizontal);
  document.removeEventListener('mouseup', handleMouseUpHorizontal);
  document.removeEventListener('keydown', handleKeyDown);
});

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
  setTimeout(() => {
    addFilesModalVisible.value = false;
    getDatabaseInfo();
  }, 1000);
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
  use_qa_split: false,
  qa_separator: '\n\n\n',
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
    use_qa_split: isQaSplitSupported.value ? chunkParams.value.use_qa_split : false,
    qa_separator: chunkParams.value.qa_separator,
  };
  chunkConfigModalVisible.value = true;
};

// 处理分块参数配置提交
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

// 显示添加文件弹窗
const showAddFilesModal = () => {
  addFilesModalVisible.value = true;
};





// 选中的行
const selectedRowKeys = ref([]);

// 面板可见性控制
const panels = reactive({
  query: { visible: true },
  graph: { visible: true },
});

const togglePanel = (panel) => {
  panels[panel].visible = !panels[panel].visible;
};

// 切换右侧面板显示/隐藏
const toggleRightPanel = () => {
  state.rightPanelVisible = !state.rightPanelVisible;
};

// 拖拽调整大小
const leftPanelWidth = ref(45); // 百分比
const isDragging = ref(false);
const resizeHandle = ref(null);

const rightPanelHeight = reactive({ query: 50, graph: 50 });
const isDraggingVertical = ref(false);
const resizeHandleHorizontal = ref(null);

// 计算面板样式的方法
const computePanelStyles = () => {
  const queryVisible = panels.query.visible;
  const graphVisible = panels.graph.visible;

  if (queryVisible && graphVisible) {
    // 两个面板都显示时，按比例分配
    return {
      query: { height: rightPanelHeight.query + '%' },
      graph: { height: rightPanelHeight.graph + '%' }
    };
  } else if (queryVisible && !graphVisible) {
    // 只显示查询面板时，查询面板占满
    return {
      query: { height: 'calc(100% - 40px)' },
      graph: { height: '36px' }
    };
  } else if (!queryVisible && graphVisible) {
    // 只显示图谱面板时，图谱面板占满
    return {
      query: { height: '36px' },
      graph: { height: 'calc(100% - 40px)' }
    };
  } else {
    // 两个面板都折叠时
    return {
      query: { height: '36px' },
      graph: { height: '36px' }
    };
  }
};

// 紧凑表格列定义
const columnsCompact = [
  {
    title: '文件名',
    dataIndex: 'filename',
    key: 'filename',
    ellipsis: true,
    width: undefined, // 不设置宽度，让它占据剩余空间
    sorter: (a, b) => (a.filename || '').localeCompare(b.filename || ''),
    sortDirections: ['ascend', 'descend']
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 60,
    align: 'right',
    sorter: (a, b) => {
      const statusOrder = { 'done': 1, 'processing': 2, 'waiting': 3, 'failed': 4 };
      return (statusOrder[a.status] || 5) - (statusOrder[b.status] || 5);
    },
    sortDirections: ['ascend', 'descend']
  },
  {
    title: '时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 80,
    align: 'right',
    sorter: (a, b) => (a.created_at || 0) - (b.created_at || 0),
    sortDirections: ['ascend', 'descend']
  },
  { title: '', key: 'action', dataIndex: 'file_id', width: 40, align: 'center' }
];

// 过滤后的文件列表
const filteredFiles = computed(() => {
  const files = Object.values(database.value.files || {});
  let filtered = files;

  // 应用文件名过滤
  if (filenameFilter.value.trim()) {
    const filterText = filenameFilter.value.toLowerCase().trim();
    filtered = files.filter(file =>
      file.filename && file.filename.toLowerCase().includes(filterText)
    );
  }

  // 应用排序
  if (sortState.value.field && sortState.value.order) {
    filtered = [...filtered].sort((a, b) => {
      let result = 0;

      if (sortState.value.field === 'status') {
        const statusOrder = { 'done': 1, 'processing': 2, 'waiting': 3, 'failed': 4 };
        result = (statusOrder[a.status] || 5) - (statusOrder[b.status] || 5);
      } else if (sortState.value.field === 'filename') {
        result = (a.filename || '').localeCompare(b.filename || '');
      } else if (sortState.value.field === 'created_at') {
        result = (a.created_at || 0) - (b.created_at || 0);
      }

      return sortState.value.order === 'descend' ? -result : result;
    });
  }

  // 同步分页状态 - 确保当前页码在有效范围内
  const totalPages = Math.ceil(filtered.length / paginationCompact.value.pageSize);
  if (totalPages > 0 && paginationCompact.value.current > totalPages) {
    // 如果当前页超出范围，调整到最后一页
    paginationCompact.value.current = totalPages;
  } else if (filtered.length === 0) {
    // 如果没有数据，重置到第一页
    paginationCompact.value.current = 1;
  }

  return filtered;
});

// 空状态文本
const emptyText = computed(() => {
  return filenameFilter.value ? `没有找到包含"${filenameFilter.value}"的文件` : '暂无文件';
});

// 排序状态
const sortState = ref({
  field: null,
  order: null
});

// 紧凑分页配置
const paginationCompact = ref({
  pageSize: 20,
  current: 1,
  total: 0,
  showSizeChanger: false,
  showTotal: (total) => `${total}`,
  size: 'small',
  showQuickJumper: false,
  onChange: (page, pageSize) => {
    paginationCompact.value.current = page;
    paginationCompact.value.pageSize = pageSize;
    // 清空选中的行，因为分页后选中的行可能不在当前视图中
    selectedRowKeys.value = [];
  },
});

// 监听过滤后的文件列表变化，更新分页总数
watch(filteredFiles, (newFiles) => {
  paginationCompact.value.total = newFiles.length;
  // filteredFiles 计算属性已经处理了分页范围检查，这里不需要重复处理
}, { immediate: true });

// 行选择改变处理
const onSelectChange = (keys) => {
  selectedRowKeys.value = keys;
};

// 获取复选框属性
const getCheckboxProps = (record) => ({
  disabled: state.lock || record.status === 'processing' || record.status === 'waiting',
});

// 排序事件处理
const handleTableChange = (_, __, sorter) => {
  // 处理排序
  if (sorter && sorter.field) {
    sortState.value.field = sorter.field;
    sortState.value.order = sorter.order;
    // 清空选中的行，因为排序后选中的行可能不在当前视图中
    selectedRowKeys.value = [];
    // 不再强制重置到第一页，让 filteredFiles 计算属性自动处理分页调整
  }
};

// 过滤相关方法
const onFilterChange = (e) => {
  filenameFilter.value = e.target.value;
  // 清空选中的行，因为过滤后选中的行可能不在当前视图中
  selectedRowKeys.value = [];
  // 重置排序状态
  sortState.value.field = null;
  sortState.value.order = null;
  // 分页调整由 filteredFiles 计算属性自动处理
};

// 选择所有失败的文件
const selectAllFailedFiles = () => {
  const failedFiles = filteredFiles.value
    .filter(file => file.status === 'failed')
    .map(file => file.file_id);

  // 合并当前选中的文件ID和失败的文件ID，去重
  const newSelectedKeys = [...new Set([...selectedRowKeys.value, ...failedFiles])];
  selectedRowKeys.value = newSelectedKeys;

  if (failedFiles.length > 0) {
    message.success(`已选择 ${failedFiles.length} 个失败的文件`);
  } else {
    message.info('当前没有失败的文件');
  }
};

// 计算是否可以批量删除
const canBatchDelete = computed(() => {
  return selectedRowKeys.value.some(key => {
    const file = filteredFiles.value.find(f => f.file_id === key);
    return file && !(state.lock || file.status === 'processing' || file.status === 'waiting');
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
const toggleAutoRefresh = () => {
  state.autoRefresh = !state.autoRefresh; // Toggle the state directly
  if (state.autoRefresh) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
};

// 获取状态文本
const getStatusText = (status) => {
  const statusMap = {
    'done': '处理完成',
    'failed': '处理失败',
    'processing': '处理中',
    'waiting': '等待处理'
  }
  return statusMap[status] || status
}

// 刷新图谱
const refreshGraph = () => {
  if (graphViewerRef.value) {
    graphViewerRef.value.loadFullGraph();
  }
};

// 清空图谱
const clearGraph = () => {
  if (graphViewerRef.value) {
    graphViewerRef.value.clearGraph();
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

// 根据文件扩展名获取文件图标
const getFileIcon = (filename) => {
  if (!filename) return FileUnknownFilled

  const extension = filename.toLowerCase().split('.').pop()

  const iconMap = {
    // 文本文件
    'txt': FileTextFilled,
    'text': FileTextFilled,
    'log': FileTextFilled,

    // Markdown文件
    'md': FileMarkdownFilled,
    'markdown': FileMarkdownFilled,

    // PDF文件
    'pdf': FilePdfFilled,

    // Word文档
    'doc': FileWordFilled,
    'docx': FileWordFilled,

    // Excel文档
    'xls': FileExcelFilled,
    'xlsx': FileExcelFilled,
    'csv': FileExcelFilled,

    // 图片文件
    'jpg': FileImageFilled,
    'jpeg': FileImageFilled,
    'png': FileImageFilled,
    'gif': FileImageFilled,
    'bmp': FileImageFilled,
    'svg': FileImageFilled,
    'webp': FileImageFilled,
  }

  return iconMap[extension] || FileUnknownFilled
}

// 根据文件扩展名获取文件图标颜色
const getFileIconColor = (filename) => {
  if (!filename) return '#8c8c8c'

  const extension = filename.toLowerCase().split('.').pop()

  const colorMap = {
    // 文本文件 - 蓝色
    'txt': '#1890ff',
    'text': '#1890ff',
    'log': '#1890ff',

    // Markdown文件 - 深蓝色
    'md': '#0050b3',
    'markdown': '#0050b3',

    // PDF文件 - 红色
    'pdf': '#ff4d4f',

    // Word文档 - 深蓝色
    'doc': '#2f54eb',
    'docx': '#2f54eb',

    // Excel文档 - 绿色
    'xls': '#52c41a',
    'xlsx': '#52c41a',
    'csv': '#52c41a',

    // 图片文件 - 紫色
    'jpg': '#722ed1',
    'jpeg': '#722ed1',
    'png': '#722ed1',
    'gif': '#722ed1',
    'bmp': '#722ed1',
    'svg': '#722ed1',
    'webp': '#722ed1',
  }

  return colorMap[extension] || '#8c8c8c'
}


</script>

<style lang="less" scoped>
.database-info-header {
  padding: 8px 16px 6px 16px;
  height: 50px;
}

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

.header-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto; /* Push to the right */

  span {
    margin: 0;
  }

  .kb-type-tag {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .type-icon {
    font-size: 12px;
    width: 12px;
    height: 12px;
  }

  .db-id,
  .file-count {
    font-size: 12px;
    color: var(--gray-600);
    font-weight: 500;
  }
}

.db-main-container {
  display: flex;
  width: 100%;
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

  .docx,
  .doc {
    background: #2C59B7;
  }

  .md {
    background: #020817;
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

  .file-info-grid {
    display: grid;
    grid-template-columns: 100px 1fr;
    gap: 6px;
    padding: 12px;
    background-color: var(--gray-100);
    border-radius: 6px;

    .info-item {
      display: contents;

      label {
        font-weight: 600;
        color: var(--gray-700);
        font-size: 13px;
      }

      span {
        font-size: 13px;
        color: var(--gray-800);
      }
    }

    .status-badge {
      font-size: 12px;
      font-weight: 500;

      &.done {
        color: #52c41a;
      }

      &.failed {
        color: #ff4d4f;
      }

      &.processing {
        color: #1890ff;
      }

      &.waiting {
        color: #faad14;
      }
    }
  }

  .file-content-section {
    margin-top: 8px;

    h4 {
      margin: 0 0 12px 0;
      font-size: 14px;
      font-weight: 600;
      color: var(--gray-800);
    }

    .content-lines {
      overflow-y: auto;
      border: 1px solid var(--gray-200);
      border-radius: 4px;

      .content-line {
        display: flex;
        padding: 8px 12px;
        border-bottom: 1px solid var(--gray-100);
        font-size: 13px;
        line-height: 1.5;

        &:last-child {
          border-bottom: none;
        }

        &:hover {
          background-color: var(--gray-50);
        }

        .line-number {
          flex-shrink: 0;
          width: 40px;
          color: var(--gray-500);
          font-family: monospace;
          font-size: 12px;
          text-align: right;
          margin-right: 12px;
        }

        .line-text {
          flex: 1;
          color: var(--gray-800);
          white-space: pre-wrap;
          word-break: break-word;
        }
      }
    }
  }

  .empty-content {
    text-align: center;
    padding: 40px;
    color: var(--gray-500);
  }

  .loading-container {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100px;
  }
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

    .ocr-controls {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .ocr-status-info {
      font-size: 11px; /* Reduced from 12px */
      margin-top: 4px;
    }

    .ocr-warning {
      color: #faad14;
      font-weight: 500;
    }

    .ocr-healthy {
      color: #52c41a;
      font-weight: 500;
    }
  }

  .qa-split-config {
    margin-bottom: 16px;
    padding: 12px 16px;
    background-color: var(--main-light-6);
    border-radius: 8px;
    border: 1px solid var(--main-light-3);

    .ant-form-item {
      margin-bottom: 12px;

      &:last-child {
        margin-bottom: 0;
      }

      .ant-form-item-label {
        color: var(--gray-800);
        font-weight: 500;
      }
    }

    .toggle-controls {
      display: flex;
      align-items: center;
    }

    .param-description {
      color: var(--gray-600);
      font-size: 12px;
      margin-left: 0;
      margin-top: 4px;
    }

    .ant-input {
      border-color: var(--main-light-3);

      &:hover,
      &:focus {
        border-color: var(--main-color);
      }
    }

    .ant-switch {
      &.ant-switch-checked {
        background-color: var(--main-color);
      }
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

    &:hover,
    &:focus {
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

/* Unified Layout Styles */
.unified-layout {
  display: flex;
  height: calc(100vh - 54px); /* Adjust based on actual header height */
  gap: 0;

  .left-panel,
  .right-panel {
    background-color: #fff;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .left-panel {
    flex-shrink: 0;
    flex-grow: 1;
    border-right: 1px solid var(--gray-200);
    background-color: var(--bg-sider);
    padding: 8px;
  }

  .right-panel {
    flex-grow: 1;
    overflow-y: auto;
  }

  .resize-handle,
  .resize-handle-horizontal {
    width: 2px;
    cursor: col-resize;
    background-color: var(--gray-200);
    transition: background-color 0.2s ease;
    position: relative;
    z-index: 10;

    &:hover {
      background-color: var(--main-light-2);
    }
  }

  .resize-handle-horizontal {
    height: 2px;
    width: 100%;
    cursor: row-resize;
    background-color: var(--gray-200);
    transition: background-color 0.2s ease;
    z-index: 10;

    &:hover {
      background-color: var(--main-light-2);
    }
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
    flex-shrink: 0;
    padding: 4px 2px;

    h3 {
      margin: 0;
      font-size: 14px;
      font-weight: 600;
      color: var(--gray-800);

      &.left-panel-title {
        margin-left: 8px;
      }
    }

    .panel-actions {
      display: flex;
      align-items: center;
      gap: 6px;

      .search-container {
        position: relative;
        display: flex;
        align-items: center;

        .search-hint {
          position: absolute;
          right: -60px;
          top: 50%;
          transform: translateY(-50%);
          font-size: 10px;
          color: var(--gray-500);
          white-space: nowrap;
        }
      }

      .ant-input-search {
        .ant-input {
          font-size: 12px;
          border-radius: 4px;

          &:hover,
          &:focus {
            border-color: var(--main-color);
          }
        }

        .ant-btn {
          font-size: 12px;
          border-radius: 0 4px 4px 0;

          &:hover {
            border-color: var(--main-color);
            color: var(--main-color);
          }
        }
      }

      .ant-btn {
        transition: all 0.2s ease;
        border-radius: 4px;

        &:hover {
          background-color: var(--main-light-5);
          color: var(--main-color);
        }
      }
    }
  }

  .batch-actions-compact {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 2px 4px;
    background-color: var(--main-light-5);
    border-radius: 4px;
    margin-bottom: 4px;
    flex-shrink: 0;

    .batch-info {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    span {
      font-size: 11px;
      font-weight: 500;
      color: var(--gray-700);
    }

    .ant-btn {
      font-size: 11px;
      padding: 0 6px;
      height: 22px;
      border-radius: 3px;

      &:hover {
        background-color: var(--main-light-4);
        color: var(--main-color);
      }
    }
  }

  .my-table-compact {
    flex: 1;
    overflow: auto;
    background-color: transparent;
    min-height: 0; /* 让 flex 子项可以正确缩小 */

    .main-btn {
      padding: 0;
      height: auto;
      line-height: 1.4;
      font-size: 14px;
      font-weight: 600;
      color: var(--color-text);
      text-decoration: none;

      &:hover {
        cursor: pointer;
        color: var(--main-color);
      }
    }

    .del-btn {
      color: var(--gray-500);

      &:hover {
        color: var(--error-color);
      }

      &:disabled {
        cursor: not-allowed;
      }
    }

    .span-type {
      display: inline-block;
      padding: 1px 5px;
      font-size: 10px;
      font-weight: bold;
      color: white;
      border-radius: 4px;
      text-transform: uppercase;
      opacity: 0.9;
    }
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--gray-200);
    padding: 8px;
    height: 36px;
    flex-shrink: 0;
    background-color: var(--gray-100);
    backdrop-filter: blur(4px);
    position: sticky;
    top: 0;
    z-index: 1;

    h3 {
      margin: 0;
      font-size: 14px;
      font-weight: 600;
    }

    .header-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .graph-stats {
      display: flex;
      gap: 4px;
    }

    .panel-actions {
      display: flex;
      gap: 4px;
      .ant-btn {
        transition: all 0.2s ease;
        border-radius: 4px;

        &:hover {
          background-color: var(--main-light-5);
          color: var(--main-color);
        }
      }
    }
  }

  .graph-disabled {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    background-color: var(--gray-50);
    border-radius: 6px;

    .disabled-content {
      text-align: center;
      color: var(--gray-600);

      h4 {
        margin: 0 0 8px 0;
        color: var(--gray-800);
        font-size: 16px;
      }

      p {
        margin: 4px 0;
        font-size: 13px;
        line-height: 1.4;
      }
    }
  }

  .query-section {
    position: relative;


    .query-content {
      display: flex;
      flex-direction: column;
      flex: 1;
      overflow: hidden;
      padding-bottom: 10px;
    }

    .query-input-row {
      margin-bottom: 4px;
      flex-shrink: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .compact-query-textarea {
      width: 100%;
      border-radius: 6px;
      font-size: 13px;
      border: 1px solid var(--gray-300);
      box-shadow: 0 0 4px 0px rgba(2, 10, 15, 0.05);
      transition: border-color 0.2s ease;
      padding: 8px 12px;

      &:focus {
        border-color: var(--main-color);
        box-shadow: 0 0 4px 0px rgba(2, 10, 15, 0.05);
      }

      :deep(.ant-input) {
        font-size: 13px;
        padding: 8px 12px;
      }

      :deep(.ant-input:focus) {
        border-color: var(--main-color);
        box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
      }
    }

    .query-actions {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .search-row {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .search-button {
      font-size: 13px;
      height: 32px;
      padding: 4px 16px;
      border-color: var(--gray-300);
      border-radius: 6px;
    }

    .query-examples-compact {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-shrink: 0;

      .examples-label {
        font-size: 12px;
        color: var(--gray-600);
        white-space: nowrap;
      }

      .examples-container {
        position: relative;
        height: 26px;
        min-width: 150px;
        font-size: 13px;

        .example-btn {
          background-color: var(--gray-100);
          border: 1px solid var(--gray-200);
          color: var(--gray-700);
          font-size: 13px;

          &:hover {
            background-color: var(--main-light-5);
            border-color: var(--main-color);
            color: var(--main-400);
          }
        }
      }
    }

    // 轮播动画
    .fade-enter-active, .fade-leave-active {
      transition: opacity 0.2s;
    }
    .fade-enter-from, .fade-leave-to {
      opacity: 0;
    }


    .query-results {
      margin-top: 6px;
      padding: 8px;
      background-color: var(--gray-50);
      border: 1px solid var(--gray-200);
      border-radius: 4px;
      white-space: pre-wrap;
      font-size: 12px;
      line-height: 1.5;
      flex: 1; /* 自动占据剩余所有空间 */
      overflow-y: auto;
      min-height: 0; /* 允许 flex 项目缩小 */
    }
  }

  .graph-section {
    flex-grow: 1;

    &.collapsed {
      flex-grow: 0;
    }

    .graph-container-compact {
      flex-grow: 1;
      border-radius: 6px;
      overflow: hidden;
      margin-top: 2px;
      background-color: #fff;
      position: relative;
      max-width: 100%;
      padding-top: 0;
    }
  }
}

/* Improve panel transitions */
.query-section,
.graph-section {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-top: 1px solid var(--gray-300);

  &.collapsed {
    height: 36px;
    min-height: 36px;
  }

  .content {
    padding: 8px;
  }
}

/* Improve the resize handle visibility */
.resize-handle,
.resize-handle-horizontal {
  transition: all 0.2s ease;
  opacity: 0.6;

  &:hover {
    opacity: 1;
    background-color: var(--main-color);
  }
}

/* Table row selection styling */
:deep(.ant-table-tbody > tr.ant-table-row-selected > td) {
  background-color: var(--main-light-5);
}

:deep(.ant-table-tbody > tr:hover > td) {
  background-color: var(--main-light-6);
}

.panel-action-btn {
  border-radius: 6px;
  border: 1px solid var(--gray-300);
  background-color: var(--gray-50);
  color: var(--gray-700);
  transition: all 0.1s ease;

  &.expanded {
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    transform: scaleX(-1);
    padding: 4px;
  }


  &.auto-refresh-btn {
    &.ant-btn-primary {
      background-color: var(--main-color);
      border-color: var(--main-color);
      color: #fff;

      &:hover {
        background-color: var(--main-color) !important;
        color: #fff !important;
      }
    }
  }

  &.active.expanded {
    transform: scaleX(1);
    &:hover {
      background-color: var(--main-light-5);
      border-color: var(--main-color);
      color: var(--main-color);
    }
  }
}
</style>

<style lang="less">
:deep(.full-modal) {
  .ant-modal {
    max-width: 100%;
    top: 0;
    padding-bottom: 0;
    margin: 0;
    padding: 0;
  }

  .ant-modal-content {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 200px);
  }

  .ant-modal-body {
    flex: 1;
  }
}



.maximized-graph-header {
  display: flex;
  justify-content: space-between;
  align-items: center;

  h3 {
    margin: 0;
    color: var(--gray-800);
  }
}


.maximized-graph-content {
  height: calc(100vh - 300px);
  border-radius: 6px;
  overflow: hidden;
}


/* 全局样式作为备用方案 */
.ant-popover .query-params-compact {
  width: 220px;
}

.ant-popover .query-params-compact .params-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 80px;
}

.ant-popover .query-params-compact .params-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
}

.ant-popover .query-params-compact .param-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
}

.ant-popover .query-params-compact .param-item label {
  font-weight: 500;
  color: var(--gray-700);
  margin-right: 8px;
}


</style>