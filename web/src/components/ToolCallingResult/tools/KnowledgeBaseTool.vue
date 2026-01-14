<template>
  <BaseToolCall :tool-call="toolCall" :hide-params="true">
    <template #header>
      <div class="sep-header">
        <span class="note">{{ operationLabel }}</span>
        <span class="separator" v-if="queryText">|</span>
        <span class="description">{{ queryText }}</span>
        <span class="separator" v-if="fileName">|</span>
        <span class="description" v-if="fileName">文件: {{ fileName }}</span>
      </div>
    </template>
    <template #result="{ resultContent }">
      <!-- get_mindmap 操作：纯文本显示 -->
      <div v-if="operation === 'get_mindmap'" class="knowledge-base-result">
        <div class="mindmap-result">
          <pre class="mindmap-content">{{ formatMindmapResult(resultContent) }}</pre>
        </div>
      </div>

      <!-- search 操作：原有的文件分组显示 -->
      <div v-else class="knowledge-base-result">
        <div class="result-summary">
          找到 {{ parsedData(resultContent).length }} 个相关文档片段，来自
          {{ fileGroups(parsedData(resultContent)).length }} 个文件
        </div>

        <div class="kb-results">
          <div
            v-for="fileGroup in fileGroups(parsedData(resultContent))"
            :key="fileGroup.filename"
            class="file-group"
          >
            <!-- 文件级别的头部 -->
            <div
              class="file-header"
              :class="{ expanded: expandedFiles.has(fileGroup.filename) }"
              @click="toggleFile(fileGroup.filename)"
            >
              <div class="file-info">
                <FileText :size="14" />
                <span class="file-name">{{ fileGroup.filename }}</span>
                <span class="chunk-count">{{ fileGroup.chunks.length }} chunks</span>
              </div>
              <div class="expand-icon">
                <ChevronDown
                  :size="14"
                  :class="{ rotated: expandedFiles.has(fileGroup.filename) }"
                />
              </div>
            </div>

            <!-- 展开的chunks列表 -->
            <div v-if="expandedFiles.has(fileGroup.filename)" class="chunks-container">
              <div
                v-for="(chunk, index) in fileGroup.chunks"
                :key="chunk.id"
                class="chunk-item"
                :class="{ 'high-relevance': chunk.score > 0.5 }"
                @click="showChunkDetail(chunk, index + 1)"
              >
                <div class="chunk-summary">
                  <span class="chunk-index">#{{ index + 1 }}</span>
                  <div class="chunk-scores">
                    <span class="score-item">相似度 {{ (chunk.score * 100).toFixed(0) }}%</span>
                    <span v-if="chunk.rerank_score" class="score-item"
                      >重排序 {{ (chunk.rerank_score * 100).toFixed(0) }}%</span
                    >
                  </div>
                  <span class="chunk-preview">{{ getPreviewText(chunk.content) }}</span>
                  <Eye :size="14" class="view-icon" />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="parsedData(resultContent).length === 0" class="no-results">
          <p>未找到相关知识库内容</p>
        </div>

        <!-- 弹窗展示chunk详细信息 -->
        <a-modal
          v-model:open="modalVisible"
          :title="`文档片段 #${selectedChunk?.index} - ${selectedChunk?.data?.metadata?.source}`"
          width="800px"
          :footer="null"
          class="chunk-detail-modal"
        >
          <div v-if="selectedChunk" class="chunk-detail">
            <div class="detail-header">
              <div class="detail-scores">
                <div class="score-card">
                  <div class="score-label">相似度分数</div>
                  <div class="score-value-large">
                    {{ (selectedChunk.data.score * 100).toFixed(1) }}%
                  </div>
                  <a-progress
                    :percent="getPercent(selectedChunk.data.score)"
                    :stroke-color="getScoreColor(selectedChunk.data.score)"
                    :show-info="false"
                    :stroke-width="6"
                  />
                </div>
                <div v-if="selectedChunk.data.rerank_score" class="score-card">
                  <div class="score-label">重排序分数</div>
                  <div class="score-value-large">
                    {{ (selectedChunk.data.rerank_score * 100).toFixed(1) }}%
                  </div>
                  <a-progress
                    :percent="getPercent(selectedChunk.data.rerank_score)"
                    :stroke-color="getScoreColor(selectedChunk.data.rerank_score)"
                    :show-info="false"
                    :stroke-width="6"
                  />
                </div>
              </div>
              <div class="detail-meta">
                <span class="meta-item"
                  ><Database :size="12" /> ID:
                  {{
                    selectedChunk.data.metadata.chunk_id || selectedChunk.data.metadata.file_id
                  }}</span
                >
              </div>
            </div>

            <div class="detail-content">
              <h5>文档内容</h5>
              <div class="content-text">{{ selectedChunk.data.content }}</div>
            </div>
          </div>
        </a-modal>
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import BaseToolCall from '../BaseToolCall.vue'
import { ref, computed } from 'vue'
import { FileText, ChevronDown, Eye, Database } from 'lucide-vue-next'

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

// 解析参数
const args = computed(() => {
  const args = props.toolCall.args || props.toolCall.function?.arguments
  if (!args) return {}

  if (typeof args === 'object') return args
  try {
    return JSON.parse(args)
  } catch (e) {
    return {}
  }
})

const toolName = computed(() => {
  return props.toolCall.name || props.toolCall.function?.name || '知识库'
})

// 获取操作类型
const operation = computed(() => {
  return args.value.operation || 'search'
})

// 获取操作标签
const operationLabel = computed(() => {
  const labels = {
    search: `${toolName.value} 搜索`,
    get_mindmap: toolName.value
  }
  return labels[operation.value] || operation.value
})

// 获取查询文本
const queryText = computed(() => {
  return args.value.query_text || ''
})

const fileName = computed(() => {
  return args.value.file_name || ''
})

const parseData = (content) => {
  if (typeof content === 'string') {
    try {
      return JSON.parse(content)
    } catch (error) {
      return []
    }
  }
  return content || []
}

const parsedData = (content) => parseData(content)

// 管理展开状态
const expandedFiles = ref(new Set())

// 弹窗状态
const modalVisible = ref(false)
const selectedChunk = ref(null)

// 按文件名聚合数据
const fileGroups = (data) => {
  const groups = new Map()

  data.forEach((item) => {
    const filename = item.metadata.source
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
}

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
  if (score >= 0.7) return '#52c41a' // 绿色 - 高相关性
  if (score >= 0.5) return '#faad14' // 橙色 - 中等相关性
  return '#ff4d4f' // 红色 - 低相关性
}

// 格式化思维导图结果
const formatMindmapResult = (content) => {
  if (typeof content === 'string') {
    return content
  }
  if (typeof content === 'object') {
    return JSON.stringify(content, null, 2)
  }
  return String(content)
}
</script>

<style lang="less" scoped>
.knowledge-base-result {
  background: var(--gray-0);
  border-radius: 8px;
  // border: 1px solid var(--gray-200);

  .mindmap-result {
    padding: 12px 16px;
    max-height: 300px;
    overflow-y: auto;

    .mindmap-content {
      margin: 0;
      font-size: 13px;
      line-height: 1.6;
      color: var(--gray-700);
      white-space: pre-wrap;
      word-break: break-word;
      font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    }
  }

  .result-summary {
    padding: 12px 16px;
    background: var(--gray-25);
    font-size: 12px;
    color: var(--gray-700);
    border-bottom: 1px solid var(--gray-100);
  }

  .kb-results {
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .file-group {
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    background: var(--gray-0);
    overflow: hidden;

    .file-header {
      padding: 8px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      transition: all 0.2s ease;
      background: var(--gray-10);

      &:hover {
        background: var(--gray-25);
      }

      &.expanded {
        background: var(--gray-25);
        border-bottom: 1px solid var(--gray-100);
      }

      .file-info {
        display: flex;
        align-items: center;
        gap: 10px;
        flex: 1;
        min-width: 0;

        svg {
          color: var(--gray-700);
        }

        .file-name {
          font-size: 13px;
          font-weight: 500;
          color: var(--gray-700);
          flex: 1;
          min-width: 0;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .chunk-count {
          font-size: 11px;
          color: var(--gray-700);
          white-space: nowrap;
          margin-right: 4px;
        }
      }

      .expand-icon {
        color: var(--gray-700);
        transition: transform 0.2s ease;

        .rotated {
          transform: rotate(180deg);
        }
      }
    }

    .chunks-container {
      background: var(--gray-0);
    }

    .chunk-item {
      padding: 10px 14px;
      border-bottom: 1px solid var(--gray-100);
      cursor: pointer;
      transition: all 0.2s ease;

      &:last-child {
        border-bottom: none;
      }

      &.high-relevance {
        background: var(--main-5);
      }

      &:hover {
        background: var(--gray-25);

        .view-icon {
          opacity: 1;
        }
      }

      .chunk-summary {
        display: flex;
        align-items: center;
        gap: 10px;

        .chunk-index {
          color: var(--gray-700);
          font-size: 11px;
          font-weight: 500;
          min-width: 20px;
          text-align: center;
          background: var(--gray-25);
          padding: 1px 4px;
          border-radius: 4px;
        }

        .chunk-scores {
          display: flex;
          gap: 6px;

          .score-item {
            font-size: 11px;
            color: var(--gray-700);
            background: var(--gray-25);
            padding: 1px 5px;
            border-radius: 4px;
            border: 1px solid var(--gray-100);
            white-space: nowrap;
          }
        }

        .chunk-preview {
          flex: 1;
          font-size: 12px;
          color: var(--gray-700);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          min-width: 0;
        }

        .view-icon {
          color: var(--gray-700);
          opacity: 0.5;
          transition: opacity 0.2s ease;
        }
      }
    }
  }

  .no-results {
    text-align: center;
    color: var(--gray-700);
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
        padding: 12px 14px;
        background: var(--gray-25);
        border-radius: 8px;
        border: 1px solid var(--gray-150);

        .score-label {
          font-size: 12px;
          color: var(--gray-700);
          margin-bottom: 6px;
          font-weight: 500;
        }

        .score-value-large {
          font-size: 18px;
          font-weight: 600;
          color: var(--gray-800);
          margin-bottom: 8px;
        }
      }
    }

    .detail-meta {
      display: flex;
      gap: 12px;

      .meta-item {
        font-size: 11px;
        color: var(--gray-700);
        display: flex;
        align-items: center;
        gap: 4px;

        svg {
          color: var(--gray-700);
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
      background: var(--gray-25);
      padding: 16px;
      border-radius: 8px;
      border: 1px solid var(--gray-150);
      max-height: 400px;
      overflow-y: auto;
    }
  }
}
</style>
