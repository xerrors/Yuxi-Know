<template>
<div class="evaluation-benchmarks-container">
  <!-- 操作栏 -->
  <div class="benchmarks-header">
    <div class="header-left">
      <span class="total-count">{{ benchmarks.length }} 个基准</span>
    </div>
    <div class="header-right">
      <a-button type="primary" @click="showUploadModal">
        <template #icon><UploadOutlined /></template>
        上传基准
      </a-button>
      <a-button @click="showGenerateModal">
        <template #icon><RobotOutlined /></template>
        自动生成
      </a-button>
    </div>
  </div>

  <!-- 基准列表 -->
  <div class="benchmarks-list">
    <div v-if="!loading && benchmarks.length === 0" class="empty-state">
      <div class="empty-icon">📋</div>
      <div class="empty-title">暂无评估基准</div>
      <div class="empty-description">上传或生成评估基准开始使用</div>
    </div>

    <div v-else-if="loading" class="loading-state">
      <a-spin size="large" />
    </div>

    <div v-else class="benchmark-list-content">
      <div
        v-for="benchmark in benchmarks"
        :key="benchmark.benchmark_id"
        class="benchmark-item"
        @click="previewBenchmark(benchmark)"
      >
        <!-- 主要内容 -->
        <div class="benchmark-main">
          <div class="benchmark-header">
            <h4 class="benchmark-name">{{ benchmark.name }}</h4>
            <div class="benchmark-actions">
              <a-button type="text" size="small" @click.stop="previewBenchmark(benchmark)">
                <EyeOutlined />
              </a-button>
              <a-button type="text" size="small" danger @click.stop="deleteBenchmark(benchmark)">
                <DeleteOutlined />
              </a-button>
            </div>
          </div>

          <p class="benchmark-desc">{{ benchmark.description || '暂无描述' }}</p>

          <!-- 标签区域 -->
          <div class="benchmark-meta">
            <div class="meta-row">
              <span
                v-if="benchmark.has_gold_chunks && benchmark.has_gold_answers"
                class="type-badge type-both"
              >
                检索 + 问答
              </span>
              <span
                v-else-if="benchmark.has_gold_chunks"
                class="type-badge type-retrieval"
              >
                检索评估
              </span>
              <span
                v-else-if="benchmark.has_gold_answers"
                class="type-badge type-answer"
              >
                问答评估
              </span>
              <span v-else class="type-badge type-query">仅查询</span>

              <span
                :class="['tag', benchmark.has_gold_chunks ? 'tag-yes' : 'tag-no']"
              >
                {{ benchmark.has_gold_chunks ? '✓' : '✗' }} 黄金Chunk
              </span>
              <span
                :class="['tag', benchmark.has_gold_answers ? 'tag-yes' : 'tag-no']"
              >
                {{ benchmark.has_gold_answers ? '✓' : '✗' }} 黄金答案
              </span>
            </div>
          </div>
        </div>

        <!-- 底部信息 -->
        <div class="benchmark-footer">
          <span class="benchmark-time">{{ formatDate(benchmark.created_at) }}</span>
          <span class="benchmark-id">{{ benchmark.benchmark_id.slice(0, 8) }}</span>
          <span class="benchmark-count">{{ benchmark.question_count }} 个问题</span>
        </div>
      </div>
    </div>
  </div>

  <!-- 上传模态框 -->
  <BenchmarkUploadModal
    v-model:visible="uploadModalVisible"
    :database-id="databaseId"
    @success="onUploadSuccess"
  />

  <!-- 生成模态框 -->
  <BenchmarkGenerateModal
    v-model:visible="generateModalVisible"
    :database-id="databaseId"
    @success="onGenerateSuccess"
  />

  <!-- 预览模态框 -->
  <a-modal
    v-model:open="previewModalVisible"
    title="评估基准详情"
    width="800px"
    :footer="null"
  >
    <div v-if="previewData" class="preview-content">
      <div class="preview-header">
        <h3>{{ previewData.name }}</h3>
        <div class="preview-meta">
          <span class="meta-item">
            <span class="meta-label">问题数:</span>
            {{ previewData.question_count }}
          </span>
          <span class="meta-item">
            <span class="meta-label">黄金Chunk:</span>
            <span :class="previewData.has_gold_chunks ? 'status-yes' : 'status-no'">
              {{ previewData.has_gold_chunks ? '有' : '无' }}
            </span>
          </span>
          <span class="meta-item">
            <span class="meta-label">黄金答案:</span>
            <span :class="previewData.has_gold_answers ? 'status-yes' : 'status-no'">
              {{ previewData.has_gold_answers ? '有' : '无' }}
            </span>
          </span>
        </div>
      </div>

      <div class="preview-questions" v-if="previewQuestions.length > 0">
        <h4>问题示例 (前5条)</h4>
        <div class="question-list">
          <div
            v-for="(item, index) in previewQuestions.slice(0, 5)"
            :key="index"
            class="question-item"
          >
            <div class="question-header">
              <span class="question-num">Q{{ index + 1 }}</span>
            </div>
            <div class="question-body">
              <p class="question-text">{{ item.query }}</p>
              <div v-if="item.gold_chunk_ids" class="question-chunk">
                黄金Chunk: {{ item.gold_chunk_ids.slice(0, 3).join(', ') }}
                <span v-if="item.gold_chunk_ids.length > 3">...等{{ item.gold_chunk_ids.length }}个</span>
              </div>
              <div v-if="item.gold_answer" class="question-answer">
                黄金答案: {{ item.gold_answer.slice(0, 150) }}
                <span v-if="item.gold_answer.length > 150">...</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </a-modal>
</div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import { message, Modal } from 'ant-design-vue';
import {
  UploadOutlined,
  RobotOutlined,
  EyeOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined
} from '@ant-design/icons-vue';
import { evaluationApi } from '@/apis/knowledge_api';
import BenchmarkUploadModal from './modals/BenchmarkUploadModal.vue';
import BenchmarkGenerateModal from './modals/BenchmarkGenerateModal.vue';

const props = defineProps({
  databaseId: {
    type: String,
    required: true
  }
});

const emit = defineEmits(['refresh']);

// 状态
const loading = ref(false);
const benchmarks = ref([]);
const uploadModalVisible = ref(false);
const generateModalVisible = ref(false);
const previewModalVisible = ref(false);
const previewData = ref(null);
const previewQuestions = ref([]);

// 加载基准列表
const loadBenchmarks = async () => {
  if (!props.databaseId) return;

  loading.value = true;
  try {
    const response = await evaluationApi.getBenchmarks(props.databaseId);

    if (response && response.message === 'success' && Array.isArray(response.data)) {
      benchmarks.value = response.data;
    } else {
      console.error('响应格式不符合预期:', response);
      message.error('基准数据格式错误');
    }
  } catch (error) {
    console.error('加载评估基准失败:', error);
    message.error('加载评估基准失败');
  } finally {
    loading.value = false;
  }
};


// 显示上传模态框
const showUploadModal = () => {
  uploadModalVisible.value = true;
};

// 显示生成模态框
const showGenerateModal = () => {
  generateModalVisible.value = true;
};

// 上传成功回调
const onUploadSuccess = () => {
  loadBenchmarks();
  message.success('基准上传成功');
  // 通知父组件刷新基准列表
  emit('refresh');
};

// 生成成功回调
const onGenerateSuccess = () => {
  loadBenchmarks();
  message.success('基准生成成功');
  // 通知父组件刷新基准列表
  emit('refresh');
};

// 预览基准
const previewBenchmark = async (benchmark) => {
  try {
    const response = await evaluationApi.getBenchmarkByDb(props.databaseId, benchmark.benchmark_id);
    if (response.message === 'success') {
      previewData.value = response.data;
      previewQuestions.value = response.data.questions || [];
      previewModalVisible.value = true;
    }
  } catch (error) {
    console.error('获取基准详情失败:', error);
    message.error('获取基准详情失败');
  }
};

// 删除基准
const deleteBenchmark = (benchmark) => {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除评估基准"${benchmark.name}"吗？此操作不可恢复。`,
    okText: '确定',
    cancelText: '取消',
    onOk: async () => {
      try {
        const response = await evaluationApi.deleteBenchmark(benchmark.benchmark_id);
        if (response.message === 'success') {
          message.success('删除成功');
          loadBenchmarks();
        }
      } catch (error) {
        console.error('删除基准失败:', error);
        message.error('删除基准失败');
      }
    }
  });
};

// 格式化日期
const formatDate = (dateStr) => {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
};

// 组件挂载时加载数据
onMounted(() => {
  loadBenchmarks();
});
</script>

<style lang="less" scoped>
.evaluation-benchmarks-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.benchmarks-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  margin-bottom: 12px;

  .total-count {
    font-size: 13px;
    color: var(--color-text-secondary);
  }

  .header-right {
    display: flex;
    gap: 8px;
  }
}

.benchmarks-list {
  flex: 1;
  overflow-y: auto;
}

.benchmark-list-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.benchmark-item {
  padding: 12px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  background: var(--color-bg-container);
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: var(--color-primary-100);
    box-shadow: 0 1px 2px var(--shadow-2);
    background: var(--gray-10);
  }

  &:active {
    transform: scale(0.998);
  }
}

.benchmark-main {
  margin-bottom: 8px;
}

.benchmark-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 6px;

  .benchmark-name {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--gray-1000);
    flex: 1;
  }

  .benchmark-actions {
    display: flex;
    gap: 4px;
  }
}

.benchmark-desc {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.benchmark-meta {
  margin-bottom: 8px;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.tag {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  background: var(--main-50);
  color: var(--color-text-tertiary);

  &.tag-yes {
    // background: var(--color-success-50);
    color: var(--main-500);
  }
}

.type-badge {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;

  &.type-both {
    background: var(--color-accent-50);
    color: var(--color-accent-700);
  }

  &.type-retrieval {
    background: var(--color-info-50);
    color: var(--color-info-700);
  }

  &.type-answer {
    background: var(--color-warning-50);
    color: var(--color-warning-700);
  }

  &.type-query {
    background: var(--gray-100);
    color: var(--gray-700);
  }
}

.benchmark-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 8px;
  border-top: 1px solid var(--gray-150);
  font-size: 11px;
  color: var(--color-text-tertiary);

  .benchmark-id {
    font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  }

  .benchmark-count {
    color: var(--color-primary-700);
    font-weight: 500;
  }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  text-align: center;

  .empty-icon {
    font-size: 48px;
    margin-bottom: 16px;
    opacity: 0.5;
  }

  .empty-title {
    font-size: 18px;
    font-weight: 500;
    color: var(--gray-900);
    margin-bottom: 8px;
  }

  .empty-description {
    font-size: 14px;
    color: var(--gray-600);
  }
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
}

// 预览模态框样式
.preview-content {
  .preview-header {
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--gray-200);

    h3 {
      margin: 0 0 12px;
      font-size: 20px;
      font-weight: 600;
      color: var(--gray-1000);
    }

    .preview-meta {
      display: flex;
      gap: 24px;

      .meta-item {
        font-size: 14px;

        .meta-label {
          color: var(--color-text-tertiary);
          margin-right: 4px;
        }

        .status-yes {
          color: var(--color-success-700);
          font-weight: 500;
        }

        .status-no {
          color: var(--color-text-tertiary);
        }
      }
    }
  }

  .preview-questions {
    h4 {
      margin: 0 0 16px;
      font-size: 16px;
      font-weight: 600;
      color: var(--gray-900);
    }

    .question-list {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .question-item {
      padding: 16px;
      background: var(--gray-50);
      border-radius: 8px;
      border: 1px solid var(--gray-200);

      .question-header {
        margin-bottom: 8px;

        .question-num {
          font-size: 14px;
          font-weight: 600;
          color: var(--gray-700);
        }
      }

      .question-body {
        .question-text {
          margin: 0 0 12px;
          font-size: 14px;
          line-height: 1.6;
          color: var(--gray-800);
        }

        .question-chunk,
        .question-answer {
          margin: 8px 0;
          font-size: 13px;
          color: var(--gray-600);
        }
      }
    }
  }
}
</style>
