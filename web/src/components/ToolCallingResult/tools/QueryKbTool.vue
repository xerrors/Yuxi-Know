<template>
  <BaseToolCall :tool-call="toolCall" :hide-params="true">
    <template #header>
      <div class="sep-header">
        <span class="note">{{ operationLabel }}</span>
        <span class="separator" v-if="kbName">|</span>
        <span class="description" v-if="kbName">知识库: {{ kbName }}</span>
        <span class="separator" v-if="queryText">|</span>
        <span class="description">{{ queryText }}</span>
      </div>
    </template>
    <template #result="{ resultContent }">
      <div class="query-kb-result">
        <KbResultGroupedList
          v-if="parsedResult(resultContent).chunks.length > 0"
          :chunks="parsedResult(resultContent).chunks"
        />

        <div v-if="hasGraphData(parsedResult(resultContent))" class="graph-result-card">
          <div class="graph-summary">
            图谱检索: 实体 {{ parsedResult(resultContent).entities.length }} 个, 关系
            {{ parsedResult(resultContent).relationships.length }} 条, 引用
            {{ parsedResult(resultContent).references.length }} 条
          </div>

          <div v-if="parsedResult(resultContent).entities.length > 0" class="graph-section">
            <div class="section-title">实体</div>
            <div class="entity-list">
              <div
                v-for="(entity, index) in parsedResult(resultContent).entities"
                :key="`entity-${index}-${getEntityName(entity)}`"
                class="entity-item"
              >
                <div class="entity-header">
                  <span class="entity-name">{{ getEntityName(entity) }}</span>
                  <span class="entity-type">{{ getEntityType(entity) }}</span>
                </div>
                <div v-if="entity?.description" class="entity-description">
                  {{ getPreviewText(entity.description, 220) }}
                </div>
              </div>
            </div>
          </div>

          <div v-if="parsedResult(resultContent).relationships.length > 0" class="graph-section">
            <div class="section-title">关系</div>
            <div class="relation-list">
              <div
                v-for="(relation, index) in parsedResult(resultContent).relationships"
                :key="`relation-${index}`"
                class="relation-item"
              >
                <span class="relation-node">{{ relation?.src_id || '-' }}</span>
                <span class="relation-arrow">→</span>
                <span class="relation-node">{{ relation?.tgt_id || '-' }}</span>
                <span class="relation-keywords">{{ relation?.keywords || '关联' }}</span>
              </div>
            </div>
          </div>

          <div v-if="parsedResult(resultContent).references.length > 0" class="graph-section">
            <div class="section-title">引用</div>
            <div class="reference-list">
              <a
                v-for="(reference, index) in parsedResult(resultContent).references"
                :key="`reference-${index}`"
                class="reference-item"
                :href="getReferenceUrl(reference)"
                target="_blank"
                rel="noopener noreferrer"
              >
                {{ getReferenceLabel(reference, index) }}
              </a>
            </div>
          </div>
        </div>

        <div
          v-if="
            parsedResult(resultContent).chunks.length === 0 &&
            !hasGraphData(parsedResult(resultContent))
          "
          class="no-results"
        >
          未找到相关知识库内容
        </div>
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import { computed } from 'vue'
import BaseToolCall from '../BaseToolCall.vue'
import KbResultGroupedList from '@/components/sources/KbResultGroupedList.vue'

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

const args = computed(() => {
  const value = props.toolCall.args || props.toolCall.function?.arguments
  if (!value) return {}
  if (typeof value === 'object') return value
  try {
    return JSON.parse(value)
  } catch {
    return {}
  }
})

const toolName = computed(() => props.toolCall.name || props.toolCall.function?.name || '知识库')

const operationLabel = computed(() => `${toolName.value} 搜索`)

const kbName = computed(() => args.value.kb_name || '')
const queryText = computed(() => args.value.query_text || '')

const EMPTY_RESULT = Object.freeze({
  chunks: [],
  entities: [],
  relationships: [],
  references: []
})

let lastResultContent = null
let lastParsedResult = EMPTY_RESULT

const normalizeChunks = (payload) => {
  if (Array.isArray(payload)) return payload
  if (!payload || typeof payload !== 'object') return []

  if (Array.isArray(payload.chunks)) return payload.chunks
  if (Array.isArray(payload.data?.chunks)) return payload.data.chunks

  return []
}

const parseResult = (content) => {
  if (content === lastResultContent) return lastParsedResult

  let payload = content
  if (typeof content === 'string') {
    try {
      payload = JSON.parse(content)
    } catch {
      lastResultContent = content
      lastParsedResult = EMPTY_RESULT
      return lastParsedResult
    }
  }

  if (!payload || typeof payload !== 'object') {
    lastResultContent = content
    lastParsedResult = EMPTY_RESULT
    return lastParsedResult
  }

  // 兼容 Milvus chunks 与 LightRAG graph/all 结构。
  const nextResult = {
    chunks: normalizeChunks(payload),
    entities: Array.isArray(payload.entities)
      ? payload.entities
      : Array.isArray(payload.data?.entities)
        ? payload.data.entities
        : [],
    relationships: Array.isArray(payload.relationships)
      ? payload.relationships
      : Array.isArray(payload.data?.relationships)
        ? payload.data.relationships
        : [],
    references: Array.isArray(payload.references)
      ? payload.references
      : Array.isArray(payload.data?.references)
        ? payload.data.references
        : []
  }

  lastResultContent = content
  lastParsedResult = nextResult
  return nextResult
}

const parsedResult = (content) => parseResult(content)

const hasGraphData = (result) =>
  result.entities.length > 0 || result.relationships.length > 0 || result.references.length > 0

const getEntityName = (entity) => entity?.entity_name || entity?.name || '未命名实体'
const getEntityType = (entity) => entity?.entity_type || entity?.type || '未分类'

const getPreviewText = (text = '', maxLength = 100) => {
  const normalized = String(text)
  return normalized.length <= maxLength ? normalized : `${normalized.slice(0, maxLength)}...`
}

const getReferenceUrl = (reference) => reference?.file_path || reference?.url || '#'

const getReferenceLabel = (reference, index) => {
  const referenceId = reference?.reference_id || `#${index + 1}`
  const url = getReferenceUrl(reference)
  return `${referenceId}: ${url}`
}
</script>

<style scoped lang="less">
.query-kb-result {
  background: var(--gray-0);
  border-radius: 8px;
  padding: 4px;

  .graph-result-card {
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    overflow: hidden;

    .graph-summary {
      padding: 10px 12px;
      background: var(--gray-25);
      font-size: 12px;
      color: var(--gray-700);
      border-bottom: 1px solid var(--gray-100);
    }

    .graph-section {
      padding: 10px 12px;
      border-bottom: 1px solid var(--gray-100);

      &:last-child {
        border-bottom: none;
      }

      .section-title {
        font-size: 12px;
        font-weight: 600;
        color: var(--gray-700);
        margin-bottom: 8px;
      }
    }

    .entity-list {
      display: flex;
      flex-direction: column;
      gap: 8px;

      .entity-item {
        border: 1px solid var(--gray-150);
        border-radius: 6px;
        padding: 8px;

        .entity-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;

          .entity-name {
            font-size: 13px;
            color: var(--gray-700);
            font-weight: 600;
          }

          .entity-type {
            font-size: 11px;
            color: var(--gray-600);
            background: var(--gray-25);
            border-radius: 4px;
            padding: 1px 6px;
          }
        }

        .entity-description {
          font-size: 12px;
          line-height: 1.5;
          color: var(--gray-700);
          white-space: pre-wrap;
        }
      }
    }

    .relation-list {
      display: flex;
      flex-direction: column;
      gap: 6px;

      .relation-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        color: var(--gray-700);

        .relation-node {
          background: var(--gray-25);
          border-radius: 4px;
          padding: 1px 6px;
        }

        .relation-arrow {
          color: var(--gray-500);
        }

        .relation-keywords {
          color: var(--gray-600);
          margin-left: auto;
          font-size: 11px;
        }
      }
    }

    .reference-list {
      display: flex;
      flex-direction: column;
      gap: 6px;

      .reference-item {
        font-size: 12px;
        color: var(--main-700);
        text-decoration: none;
        word-break: break-all;

        &:hover {
          text-decoration: underline;
        }
      }
    }
  }

  .no-results {
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 12px;
    color: var(--gray-600);
  }
}
</style>
