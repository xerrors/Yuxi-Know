<template>
  <div class="monitoring-config-view">
    <div class="page-header">
      <div></div>
      <a-space>
        <a-button type="default" @click="reloadAll" :loading="loadingAll">刷新数据</a-button>
      </a-space>
    </div>

    <a-tabs v-model:activeKey="activeTab" class="main-tabs" tab-position="left">
      <!-- 监控配置：左侧监控目标 + 右侧任务执行记录 -->
      <a-tab-pane key="center" tab="监控配置">
        <div class="center-layout">
          <div class="task-list-card">
            <div class="card-header">
              <div class="card-title">监控目标</div>
              <a-button type="primary" size="small" @click="openCreate">新增</a-button>
            </div>
            <div class="task-list" v-if="taskList.length">
              <div
                v-for="item in taskList"
                :key="item.id"
                class="task-item"
                :class="{ active: selectedTaskId === item.id }"
                @click="selectTask(item)"
              >
                <div class="task-item-main">
                  <div class="task-name">{{ item.name }}</div>
                  <a-tag :color="item.status === 'active' ? 'green' : 'default'">
                    {{ item.status === 'active' ? '启用' : '暂停' }}
                  </a-tag>
                </div>
                <div class="task-url">{{ item.url }}</div>
                <div class="task-meta">
                  <div>模式：{{ modeText(item.mode) }}</div>
                  <div>频率：{{ frequencyText(item.frequency) }}</div>
                </div>
              </div>
            </div>
            <div v-else class="empty-tip"></div>
          </div>

          <div class="job-list-card">
            <div class="card-header">
              <div>
                <div class="card-title">
                  {{ selectedTask ? selectedTask.name : '任务执行记录' }}
                </div>
                <div class="card-subtitle" v-if="selectedTask">{{ selectedTask.url }}</div>
                <div class="card-subtitle" v-else>请先在左侧选择一个监控任务</div>
              </div>
              <a-space v-if="selectedTask">
                <a-button size="small" @click="runTask(selectedTask)" :loading="running">
                  立即运行
                </a-button>
                <a-button size="small" @click="editTask(selectedTask)">编辑</a-button>
                <a-button size="small" @click="viewResults(selectedTask)">历史数据</a-button>
              </a-space>
            </div>

            <div class="card-body">
              <div class="table-body-scroll">
                <a-table
                  v-if="selectedTask"
                  :data-source="centerJobList"
                  :columns="centerJobColumns"
                  row-key="job_id"
                  size="small"
                  :pagination="false"
                  :scroll="{ x: 900, y: 500 }"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'status'">
                      <a-tag
                        :color="
                          record.status === 'success'
                            ? 'green'
                            : record.status === 'failed'
                              ? 'red'
                              : 'orange'
                        "
                      >
                        {{ record.status }}
                      </a-tag>
                    </template>
                    <template v-else-if="column.key === 'progress'">
                      <div class="job-progress-cell">
                        <a-progress
                          :percent="jobProgress(record)"
                          :size="'small'"
                          :status="
                            record.status === 'failed'
                              ? 'exception'
                              : record.status === 'success'
                                ? 'success'
                                : 'active'
                          "
                        />
                        <div class="progress-meta">
                          总 {{ record.total_pages || 0 }} / 成功 {{ record.success_pages || 0 }} /
                          失败 {{ record.failed_pages || 0 }} / 跳过 {{ record.skipped_pages || 0 }}
                        </div>
                        <div class="progress-meta">
                          列表页 {{ record.list_page_count || 0 }} / 发现链接
                          {{ record.discovered_links || 0 }} / 有效链接
                          {{ record.effective_links || 0 }}
                        </div>
                      </div>
                    </template>
                    <template v-else-if="column.key === 'updated_at'">
                      {{ formatTime(record.updated_at) }}
                    </template>
                    <template v-else-if="column.key === 'actions'">
                      <a-space size="small">
                        <a-button type="link" size="small" @click="openJobPages(record)">
                          页面日志
                        </a-button>
                        <a-button type="link" size="small" @click="openJobLogs(record)">
                          执行日志
                        </a-button>
                      </a-space>
                    </template>
                  </template>
                </a-table>
              </div>
              <div class="table-pagination">
                <a-pagination
                  :current="centerJobPagination.current"
                  :pageSize="centerJobPagination.pageSize"
                  :total="centerJobPagination.total"
                  :showSizeChanger="true"
                  :pageSizeOptions="['10', '20', '50', '100']"
                  @change="onCenterJobPageChange"
                  @showSizeChange="onCenterJobPageSizeChange"
                />
              </div>
            </div>
          </div>
        </div>
      </a-tab-pane>

      <!-- 页面库 -->
      <a-tab-pane key="pages" tab="页面库">
        <div class="toolbar">
          <a-input
            v-model:value="resultQuery"
            allow-clear
            placeholder="搜索标题或URL"
            style="width: 260px"
          />
          <a-button type="default" @click="loadAllResults">查询</a-button>
        </div>
        <div class="card-body">
          <div class="table-body-scroll">
            <a-table
              :data-source="allResultList"
              :columns="resultColumns"
              row-key="id"
              size="small"
              :pagination="false"
              :scroll="{ x: 1200, y: 500 }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.dataIndex === 'created_at' || column.dataIndex === 'publish_date'">
                  {{ record[column.dataIndex] }}
                </template>
                <template v-else-if="column.key === 'actions'">
                  <a-button type="link" size="small" @click="openResultDetail(record)">查看详情</a-button>
                </template>
              </template>
            </a-table>
          </div>
          <div class="table-pagination">
            <a-pagination
              :current="resultPagination.current"
              :pageSize="resultPagination.pageSize"
              :total="resultPagination.total"
              :showSizeChanger="true"
              :pageSizeOptions="['10', '20', '50', '100']"
              @change="onResultPageChange"
              @showSizeChange="onResultPageSizeChange"
            />
          </div>
        </div>
      </a-tab-pane>

      <!-- 监控任务（暂时隐藏） -->
      <a-tab-pane v-if="false" key="tasks" tab="监控任务">
        <!-- 预留 -->
      </a-tab-pane>

      <!-- 执行任务 -->
      <a-tab-pane key="jobs" tab="执行任务">
        <div class="toolbar">
          <a-select v-model:value="jobStatus" style="width: 150px">
            <a-select-option value="all">全部状态</a-select-option>
            <a-select-option value="pending">待执行</a-select-option>
            <a-select-option value="running">执行中</a-select-option>
            <a-select-option value="success">执行成功</a-select-option>
            <a-select-option value="failed">执行失败</a-select-option>
          </a-select>
          <a-select v-model:value="jobSource" style="width: 150px">
            <a-select-option value="all">全部来源</a-select-option>
            <a-select-option value="manual">手动触发</a-select-option>
            <a-select-option value="schedule">定时触发</a-select-option>
            <a-select-option value="adhoc">临时抽取</a-select-option>
          </a-select>
          <a-button @click="loadJobs">刷新</a-button>
        </div>
        <div class="card-body">
          <div class="table-body-scroll">
            <a-table
              :data-source="filteredJobList"
              :columns="jobColumns"
              row-key="job_id"
              size="small"
              :pagination="false"
              :scroll="{ x: 1000, y: 500 }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'trigger_source'">
                  {{ triggerSourceText(record.trigger_source) }}
                </template>
                <template v-else-if="column.key === 'status'">
                  <a-tag
                    :color="
                      record.status === 'success'
                        ? 'green'
                        : record.status === 'failed'
                          ? 'red'
                          : 'orange'
                    "
                  >
                    {{ record.status }}
                  </a-tag>
                </template>
                <template v-else-if="column.key === 'progress'">
                  <div class="job-progress-cell">
                    <a-progress
                      :percent="jobProgress(record)"
                      :size="'small'"
                      :status="
                        record.status === 'failed'
                          ? 'exception'
                          : record.status === 'success'
                            ? 'success'
                            : 'active'
                      "
                    />
                    <div class="progress-meta">
                      总 {{ record.total_pages || 0 }} / 成功 {{ record.success_pages || 0 }} / 失败
                      {{ record.failed_pages || 0 }} / 跳过 {{ record.skipped_pages || 0 }}
                    </div>
                    <div class="progress-meta">
                      列表页 {{ record.list_page_count || 0 }} / 发现链接
                      {{ record.discovered_links || 0 }} / 有效链接
                      {{ record.effective_links || 0 }}
                    </div>
                  </div>
                </template>
                <template v-else-if="column.key === 'created_at'">
                  {{ formatTime(record.created_at) }}
                </template>
                <template v-else-if="column.key === 'updated_at'">
                  {{ formatTime(record.updated_at) }}
                </template>
                <template v-else-if="column.key === 'actions'">
                  <a-space size="small">
                    <a-button type="link" size="small" @click="openJobPages(record)">页面日志</a-button>
                    <a-button type="link" size="small" @click="openJobLogs(record)">执行日志</a-button>
                    <a-button
                      v-if="record.status === 'failed'"
                      type="link"
                      danger
                      size="small"
                      @click="openJobDetail(record)"
                    >
                      失败详情
                    </a-button>
                  </a-space>
                </template>
              </template>
            </a-table>
          </div>
          <div class="table-pagination">
            <a-pagination
              :current="jobPagination.current"
              :pageSize="jobPagination.pageSize"
              :total="jobPagination.total"
              :showSizeChanger="true"
              :pageSizeOptions="['10', '20', '50', '100']"
              @change="onJobPageChange"
              @showSizeChange="onJobPageSizeChange"
            />
          </div>
        </div>
      </a-tab-pane>

      <!-- 日志管理 -->
      <a-tab-pane key="logs" tab="日志管理">
        <div class="toolbar between">
          <div class="toolbar-left">
            <a-range-picker
              v-model:value="logDateRange"
              value-format="YYYY-MM-DD"
              style="width: 260px"
            />
            <a-select v-model:value="logStatus" style="width: 140px">
              <a-select-option value="all">全部状态</a-select-option>
              <a-select-option value="success">success</a-select-option>
              <a-select-option value="failed">failed</a-select-option>
            </a-select>
            <a-input
              v-model:value="logJobId"
              allow-clear
              placeholder="按 job_id 过滤"
              style="width: 270px"
            />
            <a-button @click="loadLogs">查询</a-button>
          </div>
          <a-button @click="exportLogs">导出CSV</a-button>
        </div>
        <div class="card-body">
          <div class="table-body-scroll">
            <a-table
              :data-source="logList"
              :columns="logColumns"
              row-key="id"
              size="small"
              :pagination="false"
              :scroll="{ x: 1200, y: 500 }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'execution_time'">
                  <span class="time-text">{{ formatTime(record.execution_time) }}</span>
                </template>
                <template v-else-if="column.key === 'task_name'">
                  {{ record.task_name || '-' }}
                </template>
                <template v-else-if="column.key === 'status'">
                  <a-tag :color="record.status === 'success' ? 'green' : 'red'">
                    {{ record.status || '-' }}
                  </a-tag>
                </template>
                <template v-else-if="column.key === 'detail_log'">
                  <div class="log-detail-text">
                    {{ record.detail_log || record.error_message || '-' }}
                  </div>
                </template>
                <template v-else-if="column.key === 'items_count'">
                  {{ record.items_count ?? 0 }}
                </template>
                <template v-else-if="column.key === 'token_usage'">
                  {{ record.token_usage ?? 0 }}
                </template>
                <template v-else-if="column.key === 'actions'">
                  <a-button
                    v-if="record.detail_log || record.status === 'failed'"
                    type="link"
                    size="small"
                    :danger="record.status === 'failed'"
                    @click="openLogDetail(record)"
                  >
                    查看日志
                  </a-button>
                  <span v-else>-</span>
                </template>
              </template>
            </a-table>
          </div>
          <div class="table-pagination">
            <a-pagination
              :current="logPagination.current"
              :pageSize="logPagination.pageSize"
              :total="logPagination.total"
              :showSizeChanger="true"
              :pageSizeOptions="['10', '20', '50', '100']"
              @change="onLogPageChange"
              @showSizeChange="onLogPageSizeChange"
            />
          </div>
        </div>
      </a-tab-pane>
    </a-tabs>

    <!-- 历史数据弹窗 -->
    <a-modal
      v-model:open="resultDialogVisible"
      title="任务历史数据"
      width="900px"
      :footer="null"
      :body-style="{ maxHeight: '70vh', overflowY: 'auto' }"
    >
      <a-table
        :data-source="resultList"
        :columns="resultColumns"
        row-key="id"
        size="small"
        :pagination="{ pageSize: 10 }"
        :scroll="{ x: 1200 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'actions'">
            <a-button type="link" size="small" @click="openResultDetail(record)">查看详情</a-button>
          </template>
        </template>
      </a-table>
    </a-modal>

    <!-- 正文详情弹窗 -->
    <a-modal
      v-model:open="resultDetailVisible"
      title="爬虫正文详情"
      width="1000px"
      :footer="null"
      :body-style="{ maxHeight: '75vh', overflowY: 'auto' }"
    >
      <div class="result-detail-layout">
        <div class="result-meta">
          <div class="meta-item">
            <span class="meta-label">source_url:</span>
            <div class="meta-value">{{ selectedResult.source_url }}</div>
          </div>
          <div class="meta-item">
            <span class="meta-label">title:</span>
            <div class="meta-value">{{ selectedResult.title }}</div>
          </div>
          <div class="meta-item">
            <span class="meta-label">publish_date:</span>
            <div class="meta-value">{{ selectedResult.publish_date }}</div>
          </div>
          <div class="meta-item">
            <span class="meta-label">created_at:</span>
            <div class="meta-value">{{ selectedResult.created_at }}</div>
          </div>
        </div>
        <div class="result-content">
          <div class="section-title">正文（Markdown 渲染）</div>
          <MdPreview
            class="markdown-body markdown-preview-body"
            :modelValue="selectedResult.markdownContent"
            previewTheme="github"
          />
        </div>
      </div>
      <div class="raw-json-section">
        <div class="section-title">原始抽取结果（JSON）</div>
        <pre class="raw-json">{{ selectedResult.rawJson }}</pre>
      </div>
    </a-modal>

    <!-- 执行日志详情 -->
    <a-modal
      v-model:open="logDetailVisible"
      title="执行日志详情"
      width="900px"
      :footer="null"
      :body-style="{ maxHeight: '80vh', overflowY: 'auto' }"
    >
      <pre class="raw-json">{{ selectedLogError }}</pre>
    </a-modal>

    <!-- 任务页面执行日志 -->
    <a-modal
      v-model:open="jobPagesVisible"
      title="任务页面执行日志"
      width="1100px"
      :footer="null"
      :body-style="{ maxHeight: '75vh', overflowY: 'auto' }"
    >
      <a-table
        :data-source="jobPageList"
        :columns="jobPageColumns"
        row-key="id"
        size="small"
        :pagination="{ pageSize: 50 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag
              :color="
                record.status === 'success'
                  ? 'green'
                  : record.status === 'failed'
                    ? 'red'
                    : record.status === 'skipped'
                      ? 'blue'
                      : 'orange'
              "
            >
              {{ pageStatusText(record.status) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'started_at'">
            {{ formatTime(record.started_at) }}
          </template>
          <template v-else-if="column.key === 'finished_at'">
            {{ formatTime(record.finished_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-button
              v-if="record.content_markdown"
              type="link"
              size="small"
              @click="openPageContent(record)"
            >
              查看正文
            </a-button>
            <span v-else>-</span>
          </template>
        </template>
      </a-table>
    </a-modal>

    <!-- 页面正文弹窗 -->
    <a-modal
      v-model:open="pageContentVisible"
      title="页面正文（Markdown）"
      width="1000px"
      :footer="null"
      :body-style="{ maxHeight: '75vh', overflowY: 'auto' }"
    >
      <div class="section-title">{{ pageContentTitle }}</div>
      <div class="markdown-body page-content-body" v-html="pageContentHtml"></div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { message, notification } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { crawlerApi } from '@/apis'

const activeTab = ref('center')

const taskQuery = ref('')
const taskStatus = ref('all')
const jobStatus = ref('all')
const jobSource = ref('all')
const logDateRange = ref([])
const logStatus = ref('all')
const logJobId = ref('')
const resultQuery = ref('')
const selectedTaskId = ref(null)

const taskList = ref([])
const jobList = ref([])
const centerJobs = ref([])
const logList = ref([])
const resultList = ref([])
const allResultList = ref([])

const taskDialogVisible = ref(false)
const resultDialogVisible = ref(false)
const resultDetailVisible = ref(false)
const logDetailVisible = ref(false)
const jobPagesVisible = ref(false)
const pageContentVisible = ref(false)
const isEdit = ref(false)
const editingTaskId = ref(null)
const selectedLogError = ref('')
const jobPageList = ref([])
const pageContentTitle = ref('')
const pageContentHtml = ref('')
const currentJobPagesId = ref('')
const jobPagesTimer = ref(null)
const loadingAll = ref(false)
const running = ref(false)
const savingTask = ref(false)

const selectedResult = reactive({
  source_url: '',
  title: '',
  publish_date: '',
  created_at: '',
  markdownContent: '',
  rawJson: ''
})

// 分页
const centerJobPagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const resultPagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const jobPagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const logPagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const selectedTask = computed(() => {
  if (!selectedTaskId.value) return null
  return taskList.value.find((item) => item.id === selectedTaskId.value) || null
})

const filteredJobList = computed(() =>
  jobList.value.filter((item) => {
    if (jobStatus.value !== 'all' && item.status !== jobStatus.value) return false
    if (jobSource.value !== 'all' && item.trigger_source !== jobSource.value) return false
    return true
  })
)

const centerJobList = computed(() => centerJobs.value)

const formatTime = (val) => {
  if (!val) return ''
  const d = new Date(val)
  if (Number.isNaN(d.getTime())) return val
  return d.toLocaleString('zh-CN', { hour12: false })
}

const frequencyText = (value) => {
  const map = { hourly: '每小时', daily: '每天', weekly: '每周', manual: '手动' }
  if (map[value]) return map[value]
  if (typeof value === 'string' && value.includes('*')) return `Cron: ${value}`
  return value || '-'
}

const modeText = (value) => {
  const map = { auto: '智能判断', scrape: '单页抓取', crawl: '深度爬取', list: '列表监控' }
  return map[value] || value || '-'
}

const triggerSourceText = (value) => {
  const map = { manual: '手动触发', schedule: '定时触发', adhoc: '临时抽取', unknown: '未知' }
  return map[value] || value || '-'
}

const pageStatusText = (value) => {
  const map = {
    pending: '排队中',
    running: '执行中',
    success: '执行成功',
    failed: '执行失败',
    skipped: '已爬取跳过'
  }
  return map[value] || value || '-'
}

const jobProgress = (row) => {
  const total = Number(row?.total_pages || 0)
  if (total <= 0) {
    if (row?.status === 'success') return 100
    if (row?.status === 'failed') return 100
    return 0
  }
  const done =
    Number(row?.success_pages || 0) +
    Number(row?.failed_pages || 0) +
    Number(row?.skipped_pages || 0)
  return Math.min(100, Math.round((done / total) * 100))
}

const escapeHtml = (text) =>
  String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')

const normalizeResultRows = (payload) => {
  const source = Array.isArray(payload) ? payload : []
  return source
    .filter((item) => item && typeof item === 'object')
    .map((item) => {
      const firstData =
        Array.isArray(item.data) && item.data.length > 0 && item.data[0] && typeof item.data[0] === 'object'
          ? item.data[0]
          : null
      return {
        id: item.id ?? `${item.source_url || ''}-${item.created_at || ''}`,
        task_name: item.task_name || '-',
        source_url: item.source_url || '-',
        title: item.title || firstData?.title || '-',
        publish_date: item.publish_date || firstData?.publish_date || '-',
        created_at: item.created_at || '-',
        rawItem: item
      }
    })
}

const openResultDetail = (row) => {
  const raw = row?.rawItem || {}
  const data = raw?.data
  let content = ''
  let bestItem = null

  if (Array.isArray(data)) {
    bestItem = data.find((item) => item && typeof item === 'object' && item.content) || data[0] || null
  } else if (data && typeof data === 'object') {
    bestItem = data
  }

  if (bestItem && typeof bestItem.content === 'string') {
    content = bestItem.content
  }

  selectedResult.source_url = row.source_url || '-'
  selectedResult.title = row.title || '-'
  selectedResult.publish_date = row.publish_date || '-'
  selectedResult.created_at = row.created_at || '-'
  selectedResult.markdownContent = content || '（该记录无正文内容）'
  selectedResult.rawJson = JSON.stringify(raw, null, 2)
  resultDetailVisible.value = true
}

const openLogDetail = (row) => {
  selectedLogError.value = row?.detail_log || row?.error_message || '无执行详情'
  logDetailVisible.value = true
}

const openJobDetail = (row) => {
  selectedLogError.value = row?.error_message || '无失败详情'
  logDetailVisible.value = true
}

const loadTasks = async () => {
  try {
    const params = { page: 1, size: 50 }
    if (taskQuery.value) params.q = taskQuery.value
    if (taskStatus.value !== 'all') params.status = taskStatus.value
    const data = await crawlerApi.getTasks(params)
    taskList.value = data.items || []
    if (taskList.value.length === 0) {
      selectedTaskId.value = null
      centerJobs.value = []
      centerJobPagination.total = 0
      return
    }
    const exists = taskList.value.some((item) => item.id === selectedTaskId.value)
    if (!exists) {
      await selectTask(taskList.value[0])
    }
  } catch (e) {
    message.error(`加载任务失败: ${e.message}`)
  }
}

const loadLogs = async () => {
  try {
    const params = { page: logPagination.current, size: logPagination.pageSize }
    if (logStatus.value !== 'all') params.status = logStatus.value
    if (logJobId.value) params.job_id = logJobId.value.trim()
    if (Array.isArray(logDateRange.value) && logDateRange.value.length === 2) {
      params.start_date = logDateRange.value[0]
      params.end_date = logDateRange.value[1]
    }
    const data = await crawlerApi.getLogs(params)
    logList.value = data.items || []
    logPagination.total = data.total || data.total_count || data.items?.length || 0
  } catch (e) {
    message.error(`加载日志失败: ${e.message}`)
  }
}

const loadJobs = async () => {
  try {
    const params = { page: jobPagination.current, size: jobPagination.pageSize }
    if (jobStatus.value !== 'all') params.status = jobStatus.value
    const data = await crawlerApi.getJobs(params)
    jobList.value = data.items || []
    jobPagination.total = data.total || data.total_count || data.items?.length || 0
  } catch (e) {
    message.error(`加载执行任务失败: ${e.message}`)
  }
}

const loadAllResults = async () => {
  try {
    const params = { page: resultPagination.current, size: resultPagination.pageSize }
    if (resultQuery.value) params.q = resultQuery.value
    const data = await crawlerApi.getResults(params)
    allResultList.value = normalizeResultRows(data.items || [])
    resultPagination.total = data.total || data.total_count || data.items?.length || 0
  } catch (e) {
    message.error(`加载页面库失败: ${e.message}`)
  }
}

const selectTask = async (row) => {
  selectedTaskId.value = row?.id || null
  if (!selectedTaskId.value) {
    centerJobs.value = []
    centerJobPagination.total = 0
    return
  }
  try {
    const params = {
      page: centerJobPagination.current,
      size: centerJobPagination.pageSize,
      task_id: selectedTaskId.value
    }
    const data = await crawlerApi.getJobs(params)
    centerJobs.value = data.items || []
    centerJobPagination.total = data.total || data.total_count || data.items?.length || 0
  } catch (e) {
    message.error(`加载任务执行记录失败: ${e.message}`)
  }
}

const loadJobPages = async (jobId) => {
  const data = await crawlerApi.getJobPages(jobId, { page: 1, size: 200 })
  jobPageList.value = data.items || []
}

const openJobPages = async (row) => {
  try {
    currentJobPagesId.value = row.job_id
    await loadJobPages(row.job_id)
    jobPagesVisible.value = true
    if (jobPagesTimer.value) {
      clearInterval(jobPagesTimer.value)
      jobPagesTimer.value = null
    }
    jobPagesTimer.value = setInterval(async () => {
      if (!jobPagesVisible.value || !currentJobPagesId.value) return
      await loadJobPages(currentJobPagesId.value)
    }, 2000)
  } catch (e) {
    message.error(`加载页面日志失败: ${e.message}`)
  }
}

const openPageContent = (row) => {
  pageContentTitle.value = row.page_url || ''
  pageContentHtml.value = row.content_markdown
    ? escapeHtml(row.content_markdown)
    : '（暂无正文）'
  pageContentVisible.value = true
}

const openJobLogs = async (row) => {
  activeTab.value = 'logs'
  logJobId.value = row?.job_id || ''
  await loadLogs()
}

const viewResults = async (row) => {
  try {
    const data = await crawlerApi.getTaskResults(row.id, { page: 1, size: 50 })
    resultList.value = normalizeResultRows(data.items)
    resultDialogVisible.value = true
  } catch (e) {
    message.error(`加载历史数据失败: ${e.message}`)
  }
}

const exportLogs = () => {
  const params = {}
  if (logStatus.value !== 'all') params.status = logStatus.value
  if (logJobId.value) params.job_id = logJobId.value.trim()
  if (Array.isArray(logDateRange.value) && logDateRange.value.length === 2) {
    params.start_date = logDateRange.value[0]
    params.end_date = logDateRange.value[1]
  }
  window.open(crawlerApi.exportLogsUrl(params), '_blank')
}

const taskForm = reactive({
  name: '',
  url: '',
  frequency: 'manual',
  schedule_type: 'manual',
  schedule_cycle: 'hourly',
  schedule_interval: 1,
  schedule_time: '09:00',
  schedule_weekday: 1,
  custom_cron: '',
  mode: 'auto',
  detail_url_pattern: '',
  max_depth: 1,
  concurrency: 2,
  use_proxy: false,
  status: 'active',
  options: {
    html_to_markdown: true,
    remove_scripts_styles: true,
    include_images: true,
    cache_mode: 'bypass',
    wait_until: 'domcontentloaded',
    page_timeout: 60000,
    wait_for: '',
    only_text: false,
    remove_forms: false,
    exclude_external_links: false,
    simulate_user: false,
    magic: false,
    user_agent: ''
  },
  schemaText: JSON.stringify(
    {
      title: 'string',
      publish_date: 'string',
      content: 'markdown',
      source: 'string'
    },
    null,
    2
  )
})

const parseFrequencyToSchedule = (frequency) => {
  if (frequency === 'manual') {
    taskForm.schedule_type = 'manual'
    taskForm.schedule_cycle = 'hourly'
    taskForm.schedule_interval = 1
    return
  }
  taskForm.schedule_type = 'scheduled'
  if (frequency === 'hourly') {
    taskForm.schedule_cycle = 'hourly'
    taskForm.schedule_interval = 1
    return
  }
  if (frequency === 'daily') {
    taskForm.schedule_cycle = 'daily'
    taskForm.schedule_time = '09:00'
    return
  }
  if (frequency === 'weekly') {
    taskForm.schedule_cycle = 'weekly'
    taskForm.schedule_time = '09:00'
    taskForm.schedule_weekday = 1
    return
  }
  const weeklyMatch = /^(\d+)\s+(\d+)\s+\*\s+\*\s+([0-6])$/.exec(frequency || '')
  if (weeklyMatch) {
    taskForm.schedule_cycle = 'weekly'
    taskForm.schedule_time = `${String(weeklyMatch[2]).padStart(2, '0')}:${String(
      weeklyMatch[1]
    ).padStart(2, '0')}`
    taskForm.schedule_weekday = Number(weeklyMatch[3])
    return
  }
  const dailyMatch = /^(\d+)\s+(\d+)\s+\*\s+\*\s+\*$/.exec(frequency || '')
  if (dailyMatch) {
    taskForm.schedule_cycle = 'daily'
    taskForm.schedule_time = `${String(dailyMatch[2]).padStart(2, '0')}:${String(
      dailyMatch[1]
    ).padStart(2, '0')}`
    return
  }
  const hourlyMatch = /^0\s+\*\/(\d+)\s+\*\s+\*\s+\*$/.exec(frequency || '')
  if (hourlyMatch) {
    taskForm.schedule_cycle = 'hourly'
    taskForm.schedule_interval = Number(hourlyMatch[1])
    return
  }
  taskForm.schedule_cycle = 'cron'
  taskForm.custom_cron = frequency || ''
}

const buildFrequency = () => {
  if (taskForm.schedule_type === 'manual') return 'manual'
  if (taskForm.schedule_cycle === 'hourly') {
    return taskForm.schedule_interval > 1
      ? `0 */${taskForm.schedule_interval} * * *`
      : 'hourly'
  }
  const [hourText, minuteText] = (taskForm.schedule_time || '09:00').split(':')
  const hour = Number(hourText || 9)
  const minute = Number(minuteText || 0)
  if (taskForm.schedule_cycle === 'daily') return `${minute} ${hour} * * *`
  if (taskForm.schedule_cycle === 'weekly') return `${minute} ${hour} * * ${taskForm.schedule_weekday}`
  return (taskForm.custom_cron || '').trim() || 'hourly'
}

const openCreate = () => {
  isEdit.value = false
  editingTaskId.value = null
  taskForm.name = ''
  taskForm.url = ''
  taskForm.frequency = 'manual'
  parseFrequencyToSchedule(taskForm.frequency)
  taskForm.mode = 'auto'
  taskForm.detail_url_pattern = ''
  taskForm.max_depth = 1
  taskForm.concurrency = 2
  taskForm.use_proxy = false
  taskForm.status = 'active'
  taskDialogVisible.value = true
}

const editTask = (row) => {
  isEdit.value = true
  editingTaskId.value = row.id
  taskForm.name = row.name
  taskForm.url = row.url
  taskForm.frequency = row.frequency || 'hourly'
  parseFrequencyToSchedule(taskForm.frequency)
  taskForm.mode = row.mode || 'auto'
  taskForm.detail_url_pattern = row.detail_url_pattern || ''
  taskForm.max_depth = row.max_depth || 1
  taskForm.concurrency = row.concurrency || 1
  taskForm.use_proxy = !!row.use_proxy
  taskForm.status = row.status || 'active'
  Object.assign(taskForm.options, {
    html_to_markdown: row.options?.html_to_markdown ?? true,
    remove_scripts_styles: row.options?.remove_scripts_styles ?? true,
    include_images: row.options?.include_images ?? true,
    cache_mode: row.options?.cache_mode || 'bypass',
    wait_until: row.options?.wait_until || 'domcontentloaded',
    page_timeout: row.options?.page_timeout || 60000,
    wait_for: row.options?.wait_for || '',
    only_text: row.options?.only_text ?? false,
    remove_forms: row.options?.remove_forms ?? false,
    exclude_external_links: row.options?.exclude_external_links ?? false,
    simulate_user: row.options?.simulate_user ?? false,
    magic: row.options?.magic ?? false,
    user_agent: row.options?.user_agent || ''
  })
  taskForm.schemaText = JSON.stringify(
    row.schema || {
      title: 'string',
      publish_date: 'string',
      content: 'markdown',
      source: 'string'
    },
    null,
    2
  )
  taskDialogVisible.value = true
}

const saveTask = async () => {
  try {
    savingTask.value = true
    const schema = JSON.parse(taskForm.schemaText)
    const frequency = buildFrequency()
    const payload = {
      name: taskForm.name,
      url: taskForm.url,
      frequency,
      mode: taskForm.mode,
      detail_url_pattern: taskForm.detail_url_pattern,
      max_depth: taskForm.max_depth,
      concurrency: taskForm.concurrency,
      use_proxy: taskForm.use_proxy,
      status: taskForm.status,
      schema,
      options: {
        ...taskForm.options,
        wait_for: taskForm.options.wait_for || null,
        user_agent: taskForm.options.user_agent || null
      }
    }
    if (isEdit.value) {
      await crawlerApi.updateTask(editingTaskId.value, payload)
      message.success('任务已更新')
    } else {
      await crawlerApi.createTask(payload)
      message.success('任务已创建')
    }
    taskDialogVisible.value = false
    await loadTasks()
  } catch (e) {
    message.error(`保存任务失败: ${e.message}`)
  } finally {
    savingTask.value = false
  }
}

const runTask = async (row) => {
  try {
    running.value = true
    const resp = await crawlerApi.runTask(row.id)
    notification.success({
      message: '任务已触发',
      description: `job_id: ${resp.job_id}`
    })
    setTimeout(async () => {
      await loadTasks()
      await loadJobs()
      await loadLogs()
      if (selectedTaskId.value) await selectTask({ id: selectedTaskId.value })
    }, 3000)
  } catch (e) {
    message.error(`运行失败: ${e.message}`)
  } finally {
    running.value = false
  }
}

const toggleTask = async (row, active) => {
  try {
    await crawlerApi.toggleTask(row.id, active)
    await loadTasks()
  } catch (e) {
    message.error(`切换状态失败: ${e.message}`)
  }
}

const deleteTask = async (row) => {
  if (!window.confirm(`确定要删除任务「${row.name}」吗？`)) return
  try {
    await crawlerApi.deleteTask(row.id)
    message.success('任务已删除')
    await loadTasks()
    if (selectedTaskId.value === row.id) {
      if (taskList.value.length > 0) {
        await selectTask(taskList.value[0])
      } else {
        selectedTaskId.value = null
        centerJobs.value = []
      }
    }
  } catch (e) {
    message.error(`删除失败: ${e.message}`)
  }
}

const reloadAll = async () => {
  loadingAll.value = true
  try {
    await Promise.all([loadTasks(), loadJobs(), loadLogs(), loadAllResults()])
    message.success('已刷新爬虫监控数据')
  } catch (e) {
    // 单个接口已提示
  } finally {
    loadingAll.value = false
  }
}

// 页码/每页大小变化
const onCenterJobPageChange = (page, pageSize) => {
  centerJobPagination.current = page
  centerJobPagination.pageSize = pageSize
  if (selectedTaskId.value) {
    selectTask({ id: selectedTaskId.value })
  }
}

const onCenterJobPageSizeChange = (page, pageSize) => {
  centerJobPagination.current = page
  centerJobPagination.pageSize = pageSize
  if (selectedTaskId.value) {
    selectTask({ id: selectedTaskId.value })
  }
}

const onResultPageChange = (page, pageSize) => {
  resultPagination.current = page
  resultPagination.pageSize = pageSize
  loadAllResults()
}

const onResultPageSizeChange = (page, pageSize) => {
  resultPagination.current = page
  resultPagination.pageSize = pageSize
  loadAllResults()
}

const onJobPageChange = (page, pageSize) => {
  jobPagination.current = page
  jobPagination.pageSize = pageSize
  loadJobs()
}

const onJobPageSizeChange = (page, pageSize) => {
  jobPagination.current = page
  jobPagination.pageSize = pageSize
  loadJobs()
}

const onLogPageChange = (page, pageSize) => {
  logPagination.current = page
  logPagination.pageSize = pageSize
  loadLogs()
}

const onLogPageSizeChange = (page, pageSize) => {
  logPagination.current = page
  logPagination.pageSize = pageSize
  loadLogs()
}

onMounted(async () => {
  await reloadAll()
})

onBeforeUnmount(() => {
  if (jobPagesTimer.value) {
    clearInterval(jobPagesTimer.value)
    jobPagesTimer.value = null
  }
})

const centerJobColumns = [
  { title: 'job_id', dataIndex: 'job_id', key: 'job_id', width: 200, ellipsis: true },
  { title: '状态', key: 'status', width: 90 },
  { title: '进度', key: 'progress', width: 260 },
  { title: '更新时间', key: 'updated_at', width: 170 },
  { title: '操作', key: 'actions', width: 180, fixed: 'right' }
]

const jobColumns = [
  { title: 'job_id', dataIndex: 'job_id', key: 'job_id', width: 200, ellipsis: true },
  { title: '任务名', dataIndex: 'task_name', key: 'task_name', width: 150 },
  { title: '触发来源', key: 'trigger_source', width: 90 },
  { title: '状态', key: 'status', width: 90 },
  { title: '执行进度', key: 'progress', width: 240 },
  { title: '创建时间', key: 'created_at', width: 120 },
  { title: '更新时间', key: 'updated_at', width: 120 },
  { title: '详情', key: 'actions', width: 220, fixed: 'right' }
]

const logColumns = [
  { title: '执行时间', key: 'execution_time', width: 200 },
  { title: '所属任务', key: 'task_name', width: 160 },
  { title: '状态', key: 'status', width: 90 },
  { title: '系统日志详情', dataIndex: 'system_status', key: 'system_status', width: 120 },
  { title: '日志详情', key: 'detail_log', width: 320 },
  { title: '数据量', key: 'items_count', width: 80 },
  { title: 'Token', key: 'token_usage', width: 90 },
  { title: '失败详情', key: 'actions', width: 120, fixed: 'right' }
]

const resultColumns = [
  { title: '所属任务', dataIndex: 'task_name', key: 'task_name', width: 160 },
  { title: 'source_url', dataIndex: 'source_url', key: 'source_url', ellipsis: true },
  { title: 'title', dataIndex: 'title', key: 'title', width: 220 },
  { title: 'publish_date', dataIndex: 'publish_date', key: 'publish_date', width: 170 },
  { title: 'created_at', dataIndex: 'created_at', key: 'created_at', width: 180 },
  { title: '正文详情', key: 'actions', width: 110, fixed: 'right' }
]

const jobPageColumns = [
  { title: '页面 URL', dataIndex: 'page_url', key: 'page_url', ellipsis: true },
  { title: '状态', key: 'status', width: 100 },
  { title: '说明', dataIndex: 'message', key: 'message', width: 180 },
  { title: 'Token', dataIndex: 'token_usage', key: 'token_usage', width: 90 },
  { title: '开始时间', key: 'started_at', width: 170 },
  { title: '结束时间', key: 'finished_at', width: 170 },
  { title: '正文', key: 'actions', width: 120, fixed: 'right' }
]
</script>

<style lang="less" scoped>
.monitoring-config-view {
  height: calc(100vh - 76px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  margin: 16px;
  margin-top: 60px;
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: 16px;
  box-sizing: border-box;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.main-tabs {
  margin-top: 8px;
  flex: 1;
}

:deep(.ant-tabs-content-holder) {
  height: 100%;
  overflow: hidden;
}

.center-layout {
  display: flex;
  gap: 16px;
  height: 100%;
}

.task-list-card {
  flex: 0 0 320px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  background: #f9fafb;
  display: flex;
  flex-direction: column;
  height: 680px; // 固定高度，内部列表滚动
}

.job-list-card {
  flex: 1;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  background: #ffffff;
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;

  .card-title {
    font-weight: 600;
    color: #111827;
  }

  .card-subtitle {
    font-size: 12px;
    color: #6b7280;
    margin-top: 2px;
  }
}

.task-list {
  margin-top: 8px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.task-item {
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  padding: 8px;
  cursor: pointer;
  background: #ffffff;
  transition: all 0.15s ease-in-out;
  flex: 0 0 calc(50% - 4px);
  box-sizing: border-box;

  &.active {
    border-color: #3b82f6;
    background: #eff6ff;
  }

  &:hover {
    border-color: #3b82f6;
  }

  .task-item-main {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .task-name {
    font-size: 13px;
    font-weight: 500;
    color: #111827;
  }

  .task-url {
    margin-top: 2px;
    font-size: 12px;
    color: #6b7280;
    word-break: break-all;
  }

  .task-meta {
    margin-top: 2px;
    font-size: 12px;
    color: #9ca3af;
  }
}

.empty-tip {
  margin-top: 24px;
  font-size: 13px;
  color: #9ca3af;
  text-align: center;
}

.job-progress-cell {
  .progress-meta {
    margin-top: 2px;
    font-size: 11px;
    color: #6b7280;
  }
}

.card-body {
  display: flex;
  flex-direction: column;
}

.table-body-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.table-pagination {
  margin-top: 8px;
  text-align: right;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;

  &.between {
    justify-content: space-between;
  }

  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.target-cell {
  .target-name {
    font-weight: 500;
    color: #111827;
    margin-bottom: 2px;
  }

  .target-url {
    font-size: 12px;
    color: #6b7280;
  }
}

.time-text {
  font-size: 12px;
  color: #6b7280;
}

.log-detail-text {
  font-size: 12px;
  color: #4b5563;
  max-width: 320px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-detail-layout {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 16px;
}

.result-meta {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px;
  font-size: 12px;

  .meta-item {
    margin-bottom: 6px;
  }

  .meta-label {
    color: #6b7280;
  }

  .meta-value {
    color: #111827;
    word-break: break-all;
  }
}

.result-content {
  .markdown-body {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px;
    background-color: #ffffff;
    max-height: 420px;
    overflow-y: auto;
    font-size: 14px;
    line-height: 1.7;
  }
}

.markdown-preview-body :deep(.md-editor) {
  min-height: 100%;
}

.markdown-preview-body :deep(.md-editor-preview) {
  padding: 0;
}

.raw-json-section {
  margin-top: 16px;

  .raw-json {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 8px;
    font-size: 12px;
    max-height: 240px;
    overflow: auto;
  }
}

.section-title {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 6px;
}

.raw-json {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px;
  font-size: 12px;
  max-height: 320px;
  overflow: auto;
}

.page-content-body {
  max-height: 520px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  background-color: #ffffff;
}
</style>