<template>
  <div v-if="normalizedToolCalls.length > 0" class="tool-calls-container">
    <button
      v-if="shouldCollapseToolCalls"
      type="button"
      class="tool-calls-summary"
      :class="{ 'is-expanded': areToolCallsExpanded }"
      :aria-expanded="areToolCallsExpanded"
      @click="toggleToolCallsExpanded"
    >
      <span class="summary-leading">
        <Wrench size="14" />
      </span>
      <span class="summary-content">
        <span class="summary-title">{{ toolCallsSummaryTitle }}</span>
        <span class="summary-separator" v-if="normalizedToolCalls.length > 1 && toolCallsNamesMeta">·</span>
        <span class="summary-meta" v-if="normalizedToolCalls.length > 1 && toolCallsNamesMeta">{{ toolCallsNamesMeta }}</span>
        <span class="summary-status-tag" v-if="statusSummary">{{ statusSummary }}</span>
      </span>
      <span class="summary-trailing">
        <component :is="areToolCallsExpanded ? ChevronDown : ChevronRight" size="14" />
      </span>
    </button>

    <div v-if="!shouldCollapseToolCalls || areToolCallsExpanded" class="tool-calls-panel">
      <div
        v-for="(toolCall, index) in normalizedToolCalls"
        :key="toolCall.id || `${getToolCallId(toolCall)}-${index}`"
        class="tool-call-container"
      >
        <ToolCallRenderer :tool-call="toolCall" appearance="timeline" :default-expanded="false" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ChevronDown, ChevronRight, Wrench } from 'lucide-vue-next'
import { ToolCallRenderer } from '@/components/ToolCallingResult'
import { getToolCallId, HIDDEN_TOOL_CALL_IDS } from '@/components/ToolCallingResult/toolRegistry'

const props = defineProps({
  toolCalls: {
    type: Array,
    default: () => []
  },
  isActive: {
    type: Boolean,
    default: false
  }
})

const normalizedToolCalls = computed(() => {
  return (props.toolCalls || []).filter((toolCall) => {
    const toolId = getToolCallId(toolCall)

    return (
      toolCall &&
      !HIDDEN_TOOL_CALL_IDS.includes(toolId) &&
      (toolCall.id || toolCall.name || toolCall.function?.name) &&
      (toolCall.args !== undefined ||
        toolCall.function?.arguments !== undefined ||
        toolCall.tool_call_result !== undefined)
    )
  })
})

const shouldCollapseToolCalls = computed(() => normalizedToolCalls.value.length > 0)
const areToolCallsExpanded = ref(false)

watch(
  [() => normalizedToolCalls.value.length, () => props.isActive],
  ([, isActive], [, previousActive]) => {
    // 如果是活跃状态，强制展开
    if (isActive) {
      areToolCallsExpanded.value = true
      return
    }

    // 从活跃转为非活跃（例如：正文开始输出了），则收起
    if (previousActive === true && isActive === false) {
      areToolCallsExpanded.value = false
      return
    }

    // 初始化或非活跃状态下，默认保持收起
    if (!previousActive && !isActive) {
      areToolCallsExpanded.value = false
    }
  },
  { immediate: true }
)

const getToolCallLabel = (toolCall) => {
  const rawName = getToolCallId(toolCall)
  const name = typeof rawName === 'string' ? rawName.replaceAll('_', ' ') : 'tool'
  return name.charAt(0).toUpperCase() + name.slice(1)
}

const toolCallsSummaryTitle = computed(() => {
  if (normalizedToolCalls.value.length === 1) {
    return `使用了工具: ${getToolCallLabel(normalizedToolCalls.value[0])}`
  }
  return `已调用 ${normalizedToolCalls.value.length} 个工具`
})

const toolCallsNamesMeta = computed(() => {
  const names = normalizedToolCalls.value.map(getToolCallLabel).filter(Boolean)
  const uniqueNames = [...new Set(names)]
  const visibleNames = uniqueNames.slice(0, 3)

  if (visibleNames.length === 0) return ''

  return `${visibleNames.join(' · ')}${uniqueNames.length > visibleNames.length ? ` +${uniqueNames.length - visibleNames.length}` : ''}`
})

const statusSummary = computed(() => {
  const successCount = normalizedToolCalls.value.filter(
    (toolCall) => toolCall.status === 'success' || toolCall.tool_call_result
  ).length
  const runningCount = normalizedToolCalls.value.filter(
    (toolCall) =>
      toolCall.status !== 'success' && toolCall.status !== 'error' && !toolCall.tool_call_result
  ).length
  const errorCount = normalizedToolCalls.value.filter((toolCall) => toolCall.status === 'error')
    .length

  const parts = []
  if (successCount > 0 && successCount === normalizedToolCalls.value.length) {
    return '已完成'
  }
  if (errorCount > 0) parts.push(`${errorCount} 失败`)
  if (runningCount > 0) parts.push(`${runningCount} 进行中`)

  return parts.join(' · ')
})

const toggleToolCallsExpanded = () => {
  if (!shouldCollapseToolCalls.value) return
  areToolCallsExpanded.value = !areToolCallsExpanded.value
}
</script>

<style lang="less" scoped>
.tool-calls-container {
  width: 100%;
  margin: 0;
  padding: 0;

  .tool-calls-summary {
    appearance: none;
    width: auto;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 4px 8px;
    border: 1px solid transparent;
    border-radius: 6px;
    background: transparent;
    color: var(--gray-500);
    text-align: left;
    cursor: pointer;
    outline: none;
    transition: all 0.2s ease;
    user-select: none;

    &:hover {
      background: var(--gray-100);
      color: var(--gray-700);
    }

    &.is-expanded {
      color: var(--gray-700);
      background: var(--gray-50);
      margin-bottom: 4px;
    }

    .summary-leading {
      display: inline-flex;
      align-items: center;
      color: var(--gray-400);
      flex-shrink: 0;
    }

    .summary-content {
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 6px;
      flex: 1;
      font-size: 13px;
    }

    .summary-title {
      font-weight: 500;
      white-space: nowrap;
    }

    .summary-separator {
      color: var(--gray-300);
      flex-shrink: 0;
    }

    .summary-meta {
      color: var(--gray-400);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .summary-status-tag {
      margin-left: 4px;
      font-size: 11px;
      padding: 0px 4px;
      background: var(--gray-25);
      color: var(--gray-500);
      border-radius: 4px;
      white-space: nowrap;
      font-weight: normal;
    }

    .summary-trailing {
      display: inline-flex;
      align-items: center;
      color: var(--gray-300);
      flex-shrink: 0;
    }
  }

  .tool-calls-panel {
    padding: 4px 0 4px 12px;
    border-left: 1px solid var(--gray-100);
    margin-left: 16px;
    margin-top: 4px;
    margin-bottom: 8px;
  }

  .tool-call-container {
    margin-bottom: 4px;
    &:last-child {
      margin-bottom: 0;
    }
  }
}
</style>
