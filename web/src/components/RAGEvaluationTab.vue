<template>
  <div class="rag-evaluation-container">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <!-- 基准选择 -->
        <div class="benchmark-selector">
          <label class="selector-label">评估基准</label>
          <a-select
            v-model:value="selectedBenchmarkId"
            placeholder="请选择评估基准"
            style="width: 300px"
            @change="onBenchmarkChanged"
            :loading="benchmarksLoading"
          >
            <a-select-option
              v-for="benchmark in availableBenchmarks"
              :key="benchmark.benchmark_id"
              :value="benchmark.benchmark_id"
            >
              {{ benchmark.name }}（{{ benchmark.question_count }} 个问题）
            </a-select-option>
          </a-select>
        </div>
      </div>
      <div class="toolbar-right">
        <!-- 开始评估按钮 -->
        <a-button
          type="primary"
          :loading="startingEvaluation"
          @click="startEvaluation"
          :disabled="!selectedBenchmark"
          size="middle"
        >
          开始评估
        </a-button>
      </div>
    </div>

    <!-- 评估结果区域 -->
    <div class="evaluation-results">
      <!-- 模型配置（仅在选中基准且需要时显示） -->
      <div v-if="selectedBenchmark && (selectedBenchmark.has_gold_chunks || selectedBenchmark.has_gold_answers)" class="model-config-section">
        <a-row :gutter="24">
          <a-col :span="12">
            <a-form-item
              :label="selectedBenchmark.has_gold_answers ? '答案生成模型' : '答案生成模型（当前基准无需）'"
            >
              <ModelSelectorComponent
                v-model:model_spec="configForm.answer_llm"
                size="small"
                :disabled="!selectedBenchmark || !selectedBenchmark.has_gold_answers"
                @select-model="(value) => configForm.answer_llm = value"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>

          <a-col :span="12">
            <a-form-item
              :label="selectedBenchmark.has_gold_answers ? '答案评判模型' : '答案评判模型（当前基准无需）'"
            >
              <ModelSelectorComponent
                v-model:model_spec="configForm.judge_llm"
                size="small"
                :disabled="!selectedBenchmark || !selectedBenchmark.has_gold_answers"
                @select-model="(value) => configForm.judge_llm = value"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </div>

      <template v-if="!selectedBenchmark">
        <div class="empty-state">
          <a-empty description="请在顶部选择评估基准或前往基准管理">
            <a-space>
              <a-button @click="$emit('switch-to-benchmarks')">
                前往基准管理
              </a-button>
            </a-space>
          </a-empty>
        </div>
      </template>
      <template v-else>
  
        <!-- 历史评估记录 -->
        <div class="history-section">
          <h4 class="section-title">历史评估记录</h4>
          <a-table
            class="history-table"
            :columns="historyColumns"
            :data-source="evaluationHistory"
            :pagination="{ pageSize: 10 }"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'status'">
                <a-tag :color="getStatusColor(record.status)">
                  {{ getStatusText(record.status) }}
                </a-tag>
              </template>
              <template v-else-if="column.key === 'overall_score'">
                <span v-if="record.overall_score !== null">
                  <a-tag :color="getScoreTagColor(record.overall_score)">
                    {{ (record.overall_score * 100).toFixed(0) }}%
                  </a-tag>
                </span>
                <span v-else>-</span>
              </template>
              <template v-else-if="column.key === 'actions'">
                <a-space>
                  <a-button
                    v-if="record.status === 'completed'"
                    type="link"
                    size="small"
                    @click="viewResults(record.task_id)"
                  >
                    查看结果
                  </a-button>
                  <a-popconfirm
                    title="确定要删除这条评估记录吗？"
                    description="删除后将无法恢复"
                    @confirm="deleteEvaluationRecord(record.task_id)"
                    ok-text="确定"
                    cancel-text="取消"
                  >
                    <a-button
                      type="link"
                      size="small"
                      danger
                      :loading="record.deleting"
                    >
                      删除
                    </a-button>
                  </a-popconfirm>
                </a-space>
              </template>
            </template>
          </a-table>
        </div>
      </template>
    </div>
  </div>

  <!-- 评估结果详情模态框 -->
  <a-modal
    v-model:open="resultModalVisible"
    :title="`评估结果 - ${selectedResult?.task_id?.slice(0, 8) || ''}`"
    width="1200px"
    :footer="null"
  >
    <div v-if="resultsLoading" class="loading-container">
      <a-spin size="large" />
      <p style="margin-top: 16px; color: var(--gray-600)">正在加载评估结果...</p>
    </div>

    <div v-else-if="selectedResult && detailedResults.length > 0">
      <!-- 基本信息 -->
      <a-descriptions title="基本信息" :column="3" size="small" bordered style="margin-bottom: 20px">
        <a-descriptions-item label="任务ID">{{ selectedResult.task_id }}</a-descriptions-item>
        <a-descriptions-item label="状态">
          <a-tag :color="getStatusColor(selectedResult.status)">
            {{ getStatusText(selectedResult.status) }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="总体评分">
          <span v-if="selectedResult.overall_score !== null">
            <a-tag :color="getScoreTagColor(selectedResult.overall_score)">
              {{ (selectedResult.overall_score * 100).toFixed(1) }}%
            </a-tag>
          </span>
          <span v-else>-</span>
        </a-descriptions-item>
        <a-descriptions-item label="总问题数">{{ selectedResult.total_questions }}</a-descriptions-item>
        <a-descriptions-item label="完成数">{{ selectedResult.completed_questions }}</a-descriptions-item>
        <a-descriptions-item label="总耗时">
          <span v-if="evaluationStats.totalDuration">
            {{ formatDuration(evaluationStats.totalDuration) }}
          </span>
          <span v-else>-</span>
        </a-descriptions-item>
      </a-descriptions>

      <!-- 整体评估报告 -->
      <div class="evaluation-report">
        <h4 style="margin-bottom: 16px">整体评估报告</h4>
        <a-row :gutter="[16, 16]">
          <a-col :span="12">
            <a-card size="small" title="检索指标">
              <div v-if="Object.keys(evaluationStats.retrievalMetrics || {}).length > 0">
                <div v-for="(value, key) in evaluationStats.retrievalMetrics" :key="key" class="report-metric">
                  <span class="metric-label">{{ getMetricTitle(key) }}</span>
                  <span class="metric-value" :style="{ color: getScoreColor(value) }">
                    {{ formatMetricValue(value) }}
                  </span>
                </div>
              </div>
              <span v-else class="no-metrics">-</span>
            </a-card>
          </a-col>
          <a-col :span="12">
            <a-card size="small" title="答案准确性">
              <div class="accuracy-stats">
                <div class="accuracy-item">
                  <span class="accuracy-label">正确答案数</span>
                  <span class="accuracy-value">{{ evaluationStats.correctAnswers || 0 }} / {{ evaluationStats.totalQuestions || 0 }}</span>
                </div>
                <div class="accuracy-item">
                  <span class="accuracy-label">准确率</span>
                  <span class="accuracy-value" :style="{ color: getScoreColor(evaluationStats.answerAccuracy) }">
                    {{ (evaluationStats.answerAccuracy * 100).toFixed(1) }}%
                  </span>
                </div>
              </div>
            </a-card>
          </a-col>
        </a-row>
      </div>

      <!-- 详细结果表格 -->
      <h4 style="margin-bottom: 16px">详细评估结果</h4>
      <a-table
        :columns="resultColumns"
        :data-source="detailedResults"
        :pagination="{ pageSize: 10, showSizeChanger: true, showQuickJumper: true }"
        :scroll="{ x: 800 }"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'query'">
            <a-tooltip :title="record.query">
              <span class="query-text">{{ truncateText(record.query, 50) }}</span>
            </a-tooltip>
          </template>
          <template v-else-if="column.key === 'retrieval_score'">
            <div v-if="record.metrics && Object.keys(record.metrics).some(k => k.startsWith('recall') || k.startsWith('f1') || k.startsWith('precision') || k === 'map' || k === 'ndcg')" class="retrieval-metrics">
              <div v-for="(val, key) in record.metrics" :key="key" class="metric-item">
                <span v-if="key.startsWith('recall') || key.startsWith('f1') || key.startsWith('precision') || key === 'map' || key === 'ndcg'"
                      class="metric-content"
                      :class="`metric-${getMetricType(key)}`">
                  <span class="metric-name">{{ getMetricShortName(key) }}</span>
                  <span class="metric-value">{{ formatMetricValue(val) }}</span>
                </span>
              </div>
            </div>
            <span v-else class="no-metrics">-</span>
          </template>
          <template v-else-if="column.key === 'answer_score'">
            <div v-if="record.metrics && record.metrics.score !== undefined">
              <a-tag :color="record.metrics.score > 0.5 ? 'green' : 'red'">
                {{ record.metrics.score === 1.0 ? '正确' : '错误' }}
              </a-tag>
              <div v-if="record.metrics.reasoning" class="answer-reasoning">
                <a-tooltip :title="record.metrics.reasoning">
                  {{ truncateText(record.metrics.reasoning, 80) }}
                </a-tooltip>
              </div>
            </div>
            <span v-else>-</span>
          </template>
        </template>
      </a-table>
    </div>

    <div v-else-if="selectedResult" class="empty-results">
      <a-empty description="暂无详细结果数据">
        <a-button @click="viewDetails(selectedResult)">查看基本信息</a-button>
      </a-empty>
    </div>
  </a-modal>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue';
import { message } from 'ant-design-vue';
import { evaluationApi } from '@/apis/knowledge_api';
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue';

const props = defineProps({
  databaseId: {
    type: String,
    required: true
  }
});

const emit = defineEmits(['switch-to-benchmarks']);

// 状态
const selectedBenchmarkId = ref(null);
const selectedBenchmark = ref(null);
const benchmarksLoading = ref(false);
const availableBenchmarks = ref([]);
const startingEvaluation = ref(false);
const evaluationHistory = ref([]);
const resultModalVisible = ref(false);
const selectedResult = ref(null);
const detailedResults = ref([]);
const evaluationStats = ref({});
const resultsLoading = ref(false);

// 评估配置表单（使用知识库默认配置）
const configForm = reactive({
  answer_llm: '', // 答案生成模型
  judge_llm: '', // 评判模型
});

// 表格列定义
const resultColumns = [
  {
    title: '问题',
    dataIndex: 'query',
    key: 'query',
    width: 200
  },
  {
    title: '检索指标',
    key: 'retrieval_score',
    width: 300
  },
  {
    title: '答案评判',
    key: 'answer_score',
    width: 200
  }
];

const historyColumns = [
  {
    title: '开始时间',
    dataIndex: 'started_at',
    key: 'started_at',
    width: 180,
    customRender: ({ record }) => formatTime(record.started_at)
  },
  {
    title: '评估基准',
    key: 'benchmark_name',
    width: 200,
    customRender: ({ record }) => {
      // 根据 benchmark_id 查找基准名称
      const benchmark = availableBenchmarks.value.find(b => b.benchmark_id === record.benchmark_id);
      return benchmark ? benchmark.name : record.benchmark_id?.slice(0, 8) || '-';
    }
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 100
  },
  {
    title: '总体评分',
    dataIndex: 'overall_score',
    key: 'overall_score',
    width: 100
  },
  {
    title: '操作',
    key: 'actions',
    width: 150
  }
];

// 计算属性：当前选中的基准对象
const currentBenchmark = computed(() => {
  if (!selectedBenchmarkId.value || !availableBenchmarks.value) {
    return null;
  }
  return availableBenchmarks.value.find(b => b.benchmark_id === selectedBenchmarkId.value);
});

// 加载基准列表
const loadBenchmarks = async () => {
  if (!props.databaseId) return;

  benchmarksLoading.value = true;
  try {
    const response = await evaluationApi.getBenchmarks(props.databaseId);

    if (response && response.message === 'success' && Array.isArray(response.data)) {
      availableBenchmarks.value = response.data;

      // 如果之前有选中的基准，重新验证其有效性
      if (selectedBenchmarkId.value) {
        const exists = response.data.some(b => b.benchmark_id === selectedBenchmarkId.value);
        if (!exists) {
          selectedBenchmarkId.value = null;
          selectedBenchmark.value = null;
        }
      }
    } else {
      console.error('响应格式不符合预期:', response);
      message.error('基准数据格式错误');
    }
  } catch (error) {
    console.error('加载评估基准失败:', error);
    message.error('加载评估基准失败');
  } finally {
    benchmarksLoading.value = false;
  }
};

// 下拉框选择变化
const onBenchmarkChanged = (benchmarkId) => {
  const benchmark = availableBenchmarks.value.find(b => b.benchmark_id === benchmarkId);
  selectedBenchmark.value = benchmark || null;
};

// 开始评估
const startEvaluation = async () => {
  if (!selectedBenchmark.value) {
    message.error('请先选择评估基准');
    return;
  }

  startingEvaluation.value = true;

  // 获取检索配置
  let retrievalConfig = {};
  try {
    const savedConfig = localStorage.getItem(`search-config-${props.databaseId}`);
    if (savedConfig) {
      retrievalConfig = JSON.parse(savedConfig);
    }
  } catch (error) {
    console.error('获取检索配置失败:', error);
  }

  // 合并配置，优先使用评估页面的模型配置
  const params = {
    benchmark_id: selectedBenchmark.value.benchmark_id,
    retrieval_config: {
      ...retrievalConfig, // 包含所有检索参数如 top_k, similarity_threshold 等
      answer_llm: configForm.answer_llm, // 传递答案生成模型
      judge_llm: configForm.judge_llm // 传递评判模型
    }
  };

  try {
    const response = await evaluationApi.runEvaluation(props.databaseId, params);

    if (response.message === 'success') {
      message.success('评估任务已开始');
      loadEvaluationHistory();
    } else {
      message.error(response.message || '启动评估失败');
    }
  } catch (error) {
    console.error('启动评估失败:', error);
    message.error('启动评估失败');
  } finally {
    startingEvaluation.value = false;
  }
};


// 加载评估历史
const loadEvaluationHistory = async () => {
  try {
    const response = await evaluationApi.getEvaluationHistory(props.databaseId);
    if (response.message === 'success') {
      evaluationHistory.value = response.data || [];
    }
  } catch (error) {
    console.error('加载评估历史失败:', error);
    message.error('加载评估历史失败');
  }
};

// 计算评估统计信息
const calculateEvaluationStats = (results) => {
  if (!results || results.length === 0) {
    return {};
  }

  const stats = {
    totalQuestions: results.length,
    retrievalMetrics: {},
    answerAccuracy: 0,
    correctAnswers: 0,
    averageResponseTime: 0,
    totalResponseTime: 0
  };

  const metricSums = {};
  const metricCounts = {};

  results.forEach(item => {
    // 答案准确率
    if (item.metrics && item.metrics.score !== undefined) {
      if (item.metrics.score > 0.5) {
        stats.correctAnswers++;
      }
    }

    // 检索指标统计
    if (item.metrics) {
      Object.keys(item.metrics).forEach(key => {
        if (key.startsWith('recall') || key.startsWith('f1') || key.startsWith('precision') || key === 'map' || key === 'ndcg') {
          if (!metricSums[key]) {
            metricSums[key] = 0;
            metricCounts[key] = 0;
          }
          metricSums[key] += item.metrics[key];
          metricCounts[key]++;
        }
      });
    }
  });

  // 计算平均值
  Object.keys(metricSums).forEach(key => {
    stats.retrievalMetrics[key] = metricSums[key] / metricCounts[key];
  });

  // 计算答案准确率
  stats.answerAccuracy = stats.totalQuestions > 0 ? (stats.correctAnswers / stats.totalQuestions) : 0;

  return stats;
};

// 查看结果
const viewResults = async (taskId) => {
  try {
    resultsLoading.value = true;
    const response = await evaluationApi.getEvaluationResults(taskId);
    if (response.message === 'success' && response.data) {
      // API 返回的是直接的评估结果对象
      const resultData = response.data;

      // 设置详细结果 - 如果有 interim_results 就用它，否则尝试其他字段
      detailedResults.value = resultData.interim_results || resultData.results || [];

      // 计算统计信息
      evaluationStats.value = calculateEvaluationStats(detailedResults.value);

      // 从历史记录中找到对应的任务信息，如果没有则使用API返回的数据
      selectedResult.value = evaluationHistory.value.find(r => r.task_id === taskId) || {
        task_id: resultData.task_id,
        status: resultData.status,
        started_at: resultData.started_at,
        completed_at: resultData.completed_at,
        total_questions: resultData.total_questions || 0,
        completed_questions: resultData.completed_questions || 0,
        overall_score: resultData.overall_score
      };

      // 计算总耗时
      if (resultData.started_at && resultData.completed_at) {
        const startTime = new Date(resultData.started_at);
        const endTime = new Date(resultData.completed_at);
        evaluationStats.value.totalDuration = (endTime - startTime) / 1000; // 秒
      }

      resultModalVisible.value = true;
    } else {
      message.error('获取评估结果失败：数据格式错误');
    }
  } catch (error) {
    console.error('获取评估结果失败:', error);
    message.error('获取评估结果失败');
  } finally {
    resultsLoading.value = false;
  }
};


// 删除评估记录
const deleteEvaluationRecord = async (taskId) => {
  try {
    // 找到对应的记录并设置loading状态
    const record = evaluationHistory.value.find(r => r.task_id === taskId);
    if (record) {
      record.deleting = true;
    }

    const response = await evaluationApi.deleteEvaluationResult(taskId);
    if (response.message === 'success') {
      message.success('删除成功');
      // 重新加载评估历史
      await loadEvaluationHistory();
    }
  } catch (error) {
    console.error('删除评估记录失败:', error);
    message.error('删除评估记录失败');
  } finally {
    // 清除loading状态
    const record = evaluationHistory.value.find(r => r.task_id === taskId);
    if (record) {
      record.deleting = false;
    }
  }
};

// 工具函数
const truncateText = (text, maxLength) => {
  if (!text) return '';
  return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
};

const formatTime = (timeStr) => {
  if (!timeStr) return '-';
  const date = new Date(timeStr);
  return date.toLocaleString('zh-CN');
};

const getScoreColor = (score) => {
  if (score >= 0.8) return 'var(--color-success-500)';
  if (score >= 0.6) return 'var(--color-warning-500)';
  return 'var(--color-error-500)';
};

const getScoreTagColor = (score) => {
  if (score >= 0.8) return 'success';
  if (score >= 0.6) return 'warning';
  return 'error';
};

const getStatusColor = (status) => {
  const colors = {
    running: 'blue',
    completed: 'green',
    failed: 'red',
    paused: 'orange'
  };
  return colors[status] || 'default';
};

const getStatusText = (status) => {
  const texts = {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    paused: '已暂停'
  };
  return texts[status] || status;
};

const getMetricTitle = (key) => {
  const titles = {
    precision: '精确率',
    recall: '召回率',
    f1: 'F1分数',
    map: '平均精度',
    ndcg: 'NDCG',
    bleu: 'BLEU分数',
    rouge: 'ROUGE分数',
    answer_correctness: '答案准确性',
    score: '评分',
    reasoning: '理由',
    overall_score: '综合评分'
  };
  // 处理 recall@k, f1@k
  if (key.startsWith('recall@')) return `召回率 (${key.split('@')[1]})`;
  if (key.startsWith('f1@')) return `F1 (${key.split('@')[1]})`;
  if (key.startsWith('precision@')) return `精确率 (${key.split('@')[1]})`;

  return titles[key] || key;
};

// 获取指标类型
const getMetricType = (key) => {
  if (key.startsWith('recall')) return 'recall';
  if (key.startsWith('precision')) return 'precision';
  if (key.startsWith('f1')) return 'f1';
  if (key === 'map') return 'map';
  if (key === 'ndcg') return 'ndcg';
  return 'default';
};

// 获取指标短名称
const getMetricShortName = (key) => {
  if (key.startsWith('recall@')) return `R@${key.split('@')[1]}`;
  if (key.startsWith('precision@')) return `P@${key.split('@')[1]}`;
  if (key.startsWith('f1@')) return `F1@${key.split('@')[1]}`;
  if (key === 'precision') return 'Precision';
  if (key === 'recall') return 'Recall';
  if (key === 'f1') return 'F1';
  if (key === 'map') return 'MAP';
  if (key === 'ndcg') return 'NDCG';
  return key;
};

// 格式化指标值
const formatMetricValue = (val) => {
  if (typeof val !== 'number') return '-';
  if (val < 1) return (val * 100).toFixed(1) + '%';
  return val.toFixed(3);
};

// 格式化持续时间
const formatDuration = (seconds) => {
  if (seconds < 60) {
    return `${Math.round(seconds)}秒`;
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.round(seconds % 60);
    return `${minutes}分${remainingSeconds}秒`;
  } else {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}小时${minutes}分`;
  }
};

// 组件挂载时加载数据
onMounted(() => {
  loadBenchmarks();
  loadEvaluationHistory();
});

</script>

<style lang="less" scoped>
.rag-evaluation-container {
  height: 100%;
  background: var(--gray-0);
  display: flex;
  flex-direction: column;
}

// 顶部工具栏
.toolbar {
  padding: 12px 16px;
  background: var(--gray-0);
  border-bottom: 1px solid var(--gray-200);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;

  .toolbar-left {
    display: flex;
    align-items: center;
  }

  .benchmark-selector {
    display: flex;
    align-items: center;
    gap: 12px;

    .selector-label {
      font-size: 14px;
      font-weight: 500;
      color: var(--gray-700);
      margin: 0;
      white-space: nowrap;
    }
  }

  .toolbar-right {
    .ant-btn {
      display: flex;
      align-items: center;
      gap: 6px;
      border-radius: 6px;
    }
  }
}

// 评估内容区域
.evaluation-content {
  flex: 1;
  overflow: hidden;
  min-height: 0;
  padding: 10px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}


// 评估结果区域
.evaluation-results {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
  padding: 16px;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background-color: rgba(0, 0, 0, 0.2);
    border-radius: 3px;

    &:hover {
      background-color: rgba(0, 0, 0, 0.3);
    }
  }
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gray-0);
  border-radius: 8px;
  border: 1px solid var(--gray-200);
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;

  .progress-stats {
    flex: 1;
    margin-right: 24px;
    min-width: 300px;

    .ant-statistic {
      margin-bottom: 12px;

      .ant-statistic-title {
        font-size: 13px;
        color: var(--gray-600);
      }

      .ant-statistic-content {
        font-size: 18px;
        font-weight: 500;
      }
    }
  }

  .progress-actions {
    flex-shrink: 0;
    padding-top: 24px;
  }
}

.query-text {
  display: inline-block;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}

.log-time {
  color: var(--gray-500);
  margin-left: 8px;
  font-size: 12px;
}


// 优化表格样式
:deep(.ant-table) {
  .ant-table-tbody > tr > td {
    padding: 8px 12px;
  }

  .ant-table-thead > tr > th {
    padding: 8px 12px;
    font-weight: 500;
    background-color: var(--gray-50);
  }
}

// 优化卡片间距
:deep(.ant-card) {
  .ant-card-head {
    padding: 8px 16px;
    min-height: 40px;

    .ant-card-head-title {
      font-size: 14px;
      font-weight: 500;
      padding: 4px 0;
    }
  }
}

// 优化时间线样式
:deep(.ant-timeline) {
  .ant-timeline-item-content {
    margin-left: 20px;
    padding-bottom: 12px;
  }
}

// 优化描述列表样式
:deep(.ant-descriptions) {
  .ant-descriptions-item-label {
    font-size: 13px;
    font-weight: 500;
    color: var(--gray-600);
  }

  .ant-descriptions-item-content {
    font-size: 13px;
  }
}

// 优化表单项间距
:deep(.ant-form) {
  .ant-form-item {
    margin-bottom: 16px;
  }
}

:deep(.ant-form-inline) {
  .ant-form-item {
    margin-right: 24px;
    margin-bottom: 16px;

    &:last-child {
      margin-right: 0;
    }
  }
}

// 优化模型配置表单项
.model-config-section {
  padding: 6px 8px;
  background: var(--gray-10);
  border-radius: 8px;
  border: 1px solid var(--gray-150);

  .ant-form-item {
    margin-bottom: 0;

    .ant-form-item-label {
      font-weight: 500;
    }

    .ant-form-item-extra {
      font-size: 12px;
      color: var(--gray-500);
      margin-top: 4px;
    }
  }

  // 为模型配置部分内的列添加特定样式
  .ant-col {
    &:not(:last-child) .ant-form-item {
      padding-right: 12px;
    }
  }
}

// 优化统计数字样式
:deep(.ant-row) {
  .ant-col {
    .ant-statistic {
      padding: 12px;
      border: 1px solid var(--gray-200);
      border-radius: 6px;
      text-align: center;
      transition: all 0.3s;

      &:hover {
        border-color: var(--gray-300);
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
      }
    }
  }
}

// 检索指标样式
.retrieval-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 20px;
  align-items: center;
}

.metric-item {
  display: flex;
  align-items: center;
}

.metric-content {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.4;
  font-weight: 500;
  white-space: nowrap;

  &.metric-recall {
    background-color: var(--color-info-50);
    color: var(--color-info-900);
  }

  &.metric-precision {
    background-color: var(--color-success-50);
    color: var(--color-success-900);
  }

  &.metric-f1 {
    background-color: var(--color-warning-50);
    color: var(--color-warning-900);
  }

  &.metric-map,
  &.metric-ndcg {
    background-color: var(--color-accent-50);
    color: var(--color-accent-900);
  }
}

.metric-name {
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.metric-value {
  font-weight: 700;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
}

.no-metrics {
  color: var(--gray-400);
  font-style: italic;
}


// 答案推理样式
.answer-reasoning {
  font-size: 12px;
  color: var(--gray-600);
  margin-top: 4px;
  line-height: 1.3;
  cursor: pointer;

  &:hover {
    color: var(--gray-800);
  }
}

// 加载和空状态样式
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 0;
}

.empty-results {
  padding: 40px 0;
  text-align: center;
}

// 评估报告样式
.evaluation-report {
  margin-bottom: 20px;

  .report-metric {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid var(--gray-100);

    &:last-child {
      border-bottom: none;
    }

    .metric-label {
      font-size: 14px;
      color: var(--gray-700);
    }

    .metric-value {
      font-size: 14px;
      font-weight: 600;
      font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
    }
  }

  .accuracy-stats {
    .accuracy-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 0;
      border-bottom: 1px solid var(--gray-100);

      &:last-child {
        border-bottom: none;
      }

      .accuracy-label {
        font-size: 14px;
        color: var(--gray-700);
      }

      .accuracy-value {
        font-size: 16px;
        font-weight: 600;
        font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
      }
    }
  }

  :deep(.ant-card) {
    .ant-card-head {
      border-bottom: 1px solid var(--gray-200);

      .ant-card-head-title {
        font-size: 14px;
        font-weight: 500;
      }
    }
  }
}

// 历史评估记录区域
.history-section {
  .section-title {
    margin: 0 0 12px 0;
    font-size: 14px;
    font-weight: 500;
    color: var(--gray-700);
  }
  :deep(.ant-table) {
    border: 1px solid var(--gray-100);
  }
}

</style>