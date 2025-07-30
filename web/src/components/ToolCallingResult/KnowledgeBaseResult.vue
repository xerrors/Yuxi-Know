<template>
  <div class="knowledge-base-result">
    <div class="kb-header">
      <h4><FileTextOutlined /> 知识库检索结果</h4>
      <div class="result-summary">
        找到 {{ data.length }} 个相关文档片段，来自 {{ fileGroups.length }} 个文件
      </div>
    </div>

    <div class="kb-results">
      <div
        v-for="fileGroup in fileGroups"
        :key="fileGroup.filename"
        class="file-group"
      >
        <!-- 文件级别的头部 -->
        <div
          class="file-header"
          :class="{ 'expanded': expandedFiles.has(fileGroup.filename) }"
          @click="toggleFile(fileGroup.filename)"
        >
          <div class="file-info">
            <FileOutlined />
            <span class="file-name">{{ fileGroup.filename }}</span>
            <span class="chunk-count">{{ fileGroup.chunks.length }} chunks</span>
          </div>
          <div class="expand-icon">
            <DownOutlined :class="{ 'rotated': expandedFiles.has(fileGroup.filename) }" />
          </div>
        </div>

        <!-- 展开的chunks列表 -->
        <div
          v-if="expandedFiles.has(fileGroup.filename)"
          class="chunks-container"
        >
          <div
            v-for="(chunk, index) in fileGroup.chunks"
            :key="chunk.id"
            class="chunk-item"
            :class="{ 'high-relevance': chunk.rerank_score > 0.5 }"
            @click="showChunkDetail(chunk, index + 1)"
          >
            <div class="chunk-summary">
              <span class="chunk-index">#{{ index + 1 }}</span>
              <div class="chunk-scores">
                <span class="score-item">相似度 {{ (chunk.distance * 100).toFixed(0) }}%</span>
                <span v-if="chunk.rerank_score" class="score-item">重排序 {{ (chunk.rerank_score * 100).toFixed(0) }}%</span>
              </div>
              <span class="chunk-preview">{{ getPreviewText(chunk.entity.text) }}</span>
              <EyeOutlined class="view-icon" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="data.length === 0" class="no-results">
      <p>未找到相关知识库内容</p>
    </div>

    <!-- 弹窗展示chunk详细信息 -->
    <a-modal
      v-model:open="modalVisible"
      :title="`文档片段 #${selectedChunk?.index} - ${selectedChunk?.data?.file?.filename}`"
      width="800px"
      :footer="null"
      class="chunk-detail-modal"
    >
      <div v-if="selectedChunk" class="chunk-detail">
        <div class="detail-header">
          <div class="detail-scores">
            <div class="score-card">
              <div class="score-label">相似度分数</div>
              <div class="score-value-large">{{ (selectedChunk.data.distance * 100).toFixed(1) }}%</div>
              <a-progress
                :percent="getPercent(selectedChunk.data.distance)"
                :stroke-color="getScoreColor(selectedChunk.data.distance)"
                :show-info="false"
                stroke-width="6"
              />
            </div>
            <div v-if="selectedChunk.data.rerank_score" class="score-card">
              <div class="score-label">重排序分数</div>
              <div class="score-value-large">{{ (selectedChunk.data.rerank_score * 100).toFixed(1) }}%</div>
              <a-progress
                :percent="getPercent(selectedChunk.data.rerank_score)"
                :stroke-color="getScoreColor(selectedChunk.data.rerank_score)"
                :show-info="false"
                stroke-width="6"
              />
            </div>
          </div>
          <div class="detail-meta">
            <span class="meta-item"><DatabaseOutlined /> ID: {{ selectedChunk.data.id }}</span>
          </div>
        </div>

        <div class="detail-content">
          <h5>文档内容</h5>
          <div class="content-text">{{ selectedChunk.data.entity.text }}</div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { FileTextOutlined, FileOutlined, DownOutlined, EyeOutlined, DatabaseOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  data: {
    type: Array,
    required: true
  }
})

// 管理展开状态
const expandedFiles = ref(new Set())

// 弹窗状态
const modalVisible = ref(false)
const selectedChunk = ref(null)

// 按文件名聚合数据
const fileGroups = computed(() => {
  const groups = new Map()

  props.data.forEach(item => {
    const filename = item.file.filename
    if (!groups.has(filename)) {
      groups.set(filename, {
        filename,
        chunks: []
      })
    }
    groups.get(filename).chunks.push(item)
  })

  // 转换为数组并按文件名排序
  return Array.from(groups.values()).sort((a, b) => a.filename.localeCompare(b.filename))
})

// 切换文件展开/折叠状态
const toggleFile = (filename) => {
  if (expandedFiles.value.has(filename)) {
    expandedFiles.value.delete(filename)
  } else {
    expandedFiles.value.add(filename)
  }
}

// 显示chunk详细信息
const showChunkDetail = (chunk, index) => {
  selectedChunk.value = {
    data: chunk,
    index: index
  }
  modalVisible.value = true
}

// 获取预览文本
const getPreviewText = (text) => {
  if (text.length <= 100) return text
  return text.substring(0, 100) + '...'
}

const getPercent = (score) => {
  if (score <= 1) {
    return Math.round(score * 100)
  }
  return Math.min(Math.round(score * 100), 100)
}

const getScoreColor = (score) => {
  if (score >= 0.7) return '#52c41a'  // 绿色 - 高相关性
  if (score >= 0.5) return '#faad14'  // 橙色 - 中等相关性
  return '#ff4d4f'  // 红色 - 低相关性
}
</script>

<style lang="less" scoped>
.knowledge-base-result {
  background: var(--gray-0);
  border-radius: 8px;
  border: 1px solid var(--gray-200);

  .kb-header {
    padding: 10px 14px;
    border-bottom: 1px solid var(--gray-200);
    background: var(--gray-50);

    h4 {
      margin: 0 0 2px 0;
      color: var(--main-color);
      font-size: 14px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .result-summary {
      font-size: 11px;
      color: var(--gray-600);
    }
  }

  .kb-results {
    padding: 6px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .file-group {
    border: 1px solid var(--gray-200);
    border-radius: 6px;
    background: var(--gray-0);
    overflow: hidden;

    .file-header {
      padding: 10px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      transition: all 0.15s ease;
      background: var(--gray-25);

      &:hover {
        background: var(--gray-50);
      }

      &.expanded {
        background: var(--main-10);
        border-bottom: 1px solid var(--gray-200);
      }

      .file-info {
        display: flex;
        align-items: center;
        gap: 8px;
        flex: 1;
        min-width: 0;

        .anticon {
          color: var(--main-color);
          font-size: 13px;
        }

        .file-name {
          font-size: 13px;
          font-weight: 500;
          color: var(--gray-800);
          flex: 1;
          min-width: 0;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .chunk-count {
          font-size: 11px;
          color: var(--gray-500);
          background: var(--gray-100);
          padding: 1px 5px;
          border-radius: 10px;
          white-space: nowrap;
        }
      }

      .expand-icon {
        color: var(--gray-500);
        transition: transform 0.15s ease;
        font-size: 12px;

        .rotated {
          transform: rotate(180deg);
        }
      }
    }

    .chunks-container {
      background: var(--gray-10);
    }

    .chunk-item {
      padding: 8px 12px;
      border-bottom: 1px solid var(--gray-100);
      cursor: pointer;
      transition: all 0.15s ease;

      &:last-child {
        border-bottom: none;
      }

      &.high-relevance {
        background: var(--main-10);
      }

      &:hover {
        background: var(--main-30);

        .view-icon {
          opacity: 1;
        }
      }

      .chunk-summary {
        display: flex;
        align-items: center;
        gap: 8px;

        .chunk-index {
          color: var(--main-color);
          font-size: 10px;
          font-weight: 500;
          min-width: 18px;
          text-align: center;
        }

        .chunk-scores {
          display: flex;
          gap: 4px;

          .score-item {
            font-size: 11px;
            color: var(--gray-700);
            // background: var(--main-10);
            padding: 1px 4px;
            border-radius: 4px;
            white-space: nowrap;
          }
        }

        .chunk-preview {
          flex: 1;
          font-size: 11px;
          color: var(--gray-700);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          min-width: 0;
        }

        .view-icon {
          color: var(--main-color);
          font-size: 12px;
          opacity: 0.6;
          transition: opacity 0.15s ease;
        }
      }
    }
  }

  .no-results {
    text-align: center;
    color: var(--gray-500);
    padding: 20px;
    font-size: 12px;
  }
}

:deep(.chunk-detail-modal) {
  .ant-modal-header {
    border-bottom: 1px solid var(--gray-200);
    margin-bottom: 0;
  }

  .ant-modal-title {
    color: var(--main-color);
    font-weight: 500;
  }
}

.chunk-detail {
  .detail-header {
    margin-bottom: 16px;

    .detail-scores {
      display: flex;
      gap: 16px;
      margin-bottom: 12px;

      .score-card {
        flex: 1;
        padding: 8px 12px;
        background: var(--gray-50);
        border-radius: 6px;
        border: 1px solid var(--gray-200);

        .score-label {
          font-size: 14px;
          color: var(--gray-600);
          margin-bottom: 4px;
        }

        .score-value-large {
          font-size: 18px;
          font-weight: 600;
          color: var(--main-color);
        }
      }
    }

    .detail-meta {
      display: flex;
      gap: 12px;

      .meta-item {
        font-size: 11px;
        color: var(--gray-500);
        display: flex;
        align-items: center;
        gap: 4px;

        .anticon {
          color: var(--main-color);
        }
      }
    }
  }

  .detail-content {
    h5 {
      margin: 0 0 8px 0;
      color: var(--gray-800);
      font-size: 14px;
      font-weight: 500;
    }

    .content-text {
      font-size: 13px;
      line-height: 1.6;
      color: var(--gray-700);
      white-space: pre-wrap;
      word-break: break-word;
      background: var(--gray-50);
      padding: 16px;
      border-radius: 6px;
      border: 1px solid var(--gray-200);
      max-height: 400px;
      overflow-y: auto;
    }
  }
}
</style>