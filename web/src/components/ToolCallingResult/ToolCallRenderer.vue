<template>
  <!-- 知识图谱查询结果 -->
  <KnowledgeGraphTool v-if="isKnowledgeGraphResult" :tool-call="toolCall" ref="graphToolCallRef" />

  <!-- 网页搜索 -->
  <WebSearchTool v-else-if="isWebSearchResult" :tool-call="toolCall" />

  <!-- 知识库 -->
  <KnowledgeBaseTool v-else-if="isKnowledgeBaseResult" :tool-call="toolCall" />

  <!-- 待办事项 -->
  <TodoListTool v-else-if="isTodoListResult" :tool-call="toolCall" />

  <!-- 计算器 -->
  <CalculatorTool v-else-if="isCalculatorResult" :tool-call="toolCall" />

  <!-- 图片 -->
  <ImageTool v-else-if="isImageResult" :tool-call="toolCall" />

  <!-- 任务分配 -->
  <TaskTool v-else-if="isTaskResult" :tool-call="toolCall" />

  <!-- 写文件 -->
  <WriteFileTool v-else-if="isWriteFileResult" :tool-call="toolCall" />

  <!-- 默认展示 -->
  <BaseToolCall v-else :tool-call="toolCall" />
</template>

<script setup>
import { computed, ref } from 'vue'
import BaseToolCall from './BaseToolCall.vue'
import { useAgentStore } from '@/stores/agent'
import { useDatabaseStore } from '@/stores/database'

import WebSearchTool from './tools/WebSearchTool.vue'
import KnowledgeBaseTool from './tools/KnowledgeBaseTool.vue'
import KnowledgeGraphTool from './tools/KnowledgeGraphTool.vue'
import CalculatorTool from './tools/CalculatorTool.vue'
import TodoListTool from './tools/TodoListTool.vue'
import ImageTool from './tools/ImageTool.vue'
import TaskTool from './tools/TaskTool.vue'
import WriteFileTool from './tools/WriteFileTool.vue'

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

const agentStore = useAgentStore()
const databaseStore = useDatabaseStore()

const toolName = computed(() => props.toolCall.name || props.toolCall.function?.name || '')
const tool = computed(() => {
  const toolsList = agentStore?.availableTools ? Object.values(agentStore.availableTools) : []
  const tool = toolsList.find((t) => t.name === toolName.value)
  return tool || null
})

const databases = computed(() => databaseStore.databases || [])

const parseData = (content) => {
  if (typeof content === 'string') {
    try {
      return JSON.parse(content)
    } catch (error) {
      return content
    }
  }
  return content
}

// 识别逻辑
const isWebSearchResult = computed(() => {
  const name = toolName.value.toLowerCase()
  return name.includes('tavily_search')
})

const isTaskResult = computed(() => {
  let args = props.toolCall.args || props.toolCall.function?.arguments
  if (typeof args === 'string') {
    try {
      args = JSON.parse(args)
    } catch {
      return false
    }
  }
  return args && typeof args === 'object' && 'subagent_type' in args
})

const isKnowledgeBaseResult = computed(() => {
  const databaseInfo = databases.value.find((db) => db.name === toolName.value)
  if (databaseInfo && databaseInfo.kb_type !== 'lightrag') {
    return true
  }
  return false
})

const isKnowledgeGraphResult = computed(() => {
  const name = toolName.value.toLowerCase()
  const hasGraphKeyword = name.includes('graph') || name.includes('图谱') || name.includes('kg')
  const data = parseData(props.toolCall.tool_call_result?.content)
  const hasBasicStructure = data && typeof data === 'object'
  const hasTriples = hasBasicStructure && 'triples' in data
  return (
    (hasTriples && Array.isArray(data.triples) && data.triples.length > 0) ||
    (hasTriples && hasGraphKeyword)
  )
})

const isTodoListResult = computed(() => {
  return toolName.value === 'write_todos'
})

const isCalculatorResult = computed(() => {
  const name = toolName.value.toLowerCase()
  return name.includes('calculator') || name.includes('calc') || name.includes('math')
})

const isImageResult = computed(() => {
  const name = toolName.value.toLowerCase()
  if (!name.includes('chart')) return false
  const data = parseData(props.toolCall.tool_call_result?.content)
  return data && typeof data === 'string' && data.startsWith('http')
})

const isWriteFileResult = computed(() => {
  return toolName.value === 'write_file'
})

// 处理知识图谱刷新
const graphToolCallRef = ref(null)
const refreshGraph = () => {
  if (graphToolCallRef.value && typeof graphToolCallRef.value.refreshGraph === 'function') {
    graphToolCallRef.value.refreshGraph()
  }
}

defineExpose({ refreshGraph })
</script>

<style lang="less" scoped></style>
