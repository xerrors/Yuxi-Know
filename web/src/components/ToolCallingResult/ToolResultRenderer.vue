<template>
  <div class="tool-result-renderer">
    <!-- 网页搜索结果 -->
    <WebSearchResult
      v-if="isWebSearchResult"
      :data="parsedData"
    />

    <!-- 知识库检索结果 -->
    <KnowledgeBaseResult
      v-else-if="isKnowledgeBaseResult"
      :data="parsedData"
    />

    <!-- 知识图谱查询结果 -->
    <KnowledgeGraphResult
      v-else-if="isKnowledgeGraphResult"
      :data="parsedData"
    />

    <!-- 计算器结果 -->
    <CalculatorResult
      v-else-if="isCalculatorResult"
      :data="parsedData"
    />

    <!-- 默认的原始数据展示 -->
    <div v-else class="default-result">
      <div class="default-header">
        <h4><ToolOutlined /> {{ toolName }} 执行结果</h4>
      </div>
      <div class="default-content">
        <pre>{{ formatData(parsedData) }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ToolOutlined } from '@ant-design/icons-vue'
import WebSearchResult from './WebSearchResult.vue'
import KnowledgeBaseResult from './KnowledgeBaseResult.vue'
import KnowledgeGraphResult from './KnowledgeGraphResult.vue'
import CalculatorResult from './CalculatorResult.vue'

const props = defineProps({
  toolName: {
    type: String,
    required: true
  },
  resultContent: {
    type: [String, Object, Array, Number],
    required: true
  }
})

// 解析数据
const parsedData = computed(() => {
  if (typeof props.resultContent === 'string') {
    try {
      return JSON.parse(props.resultContent)
    } catch {
      return props.resultContent
    }
  }
  return props.resultContent
})

// 判断是否为网页搜索结果
const isWebSearchResult = computed(() => {
  const toolNameLower = props.toolName.toLowerCase()
  const isWebSearchTool = toolNameLower.includes('search') ||
                         toolNameLower.includes('tavily') ||
                         toolNameLower.includes('web')

  if (!isWebSearchTool) return false

  const data = parsedData.value
  return data &&
         typeof data === 'object' &&
         'results' in data &&
         Array.isArray(data.results) &&
         'query' in data
})

// 判断是否为知识库检索结果
const isKnowledgeBaseResult = computed(() => {
  const toolNameLower = props.toolName.toLowerCase()
  const isKnowledgeBaseTool = toolNameLower.includes('retrieve') ||
                             toolNameLower.includes('knowledge')

  if (!isKnowledgeBaseTool) return false

  const data = parsedData.value
  return Array.isArray(data) &&
         data.length > 0 &&
         data.every(item =>
           item &&
           typeof item === 'object' &&
           'id' in item &&
           'distance' in item &&
           'entity' in item &&
           'file' in item
         )
})

// 判断是否为知识图谱查询结果
const isKnowledgeGraphResult = computed(() => {
  const toolNameLower = props.toolName.toLowerCase()
  const isGraphTool = toolNameLower.includes('graph') ||
                     toolNameLower.includes('kg') ||
                     toolNameLower.includes('query_knowledge_graph')

  if (!isGraphTool) return false

  const data = parsedData.value
  return Array.isArray(data) &&
         data.length > 0 &&
         data.some(item =>
           Array.isArray(item) &&
           item.length >= 3 &&
           item.some(subItem =>
             subItem &&
             typeof subItem === 'object' &&
             ('element_id' in subItem || 'properties' in subItem)
           )
         )
})

// 判断是否为计算器结果
const isCalculatorResult = computed(() => {
  const toolNameLower = props.toolName.toLowerCase()
  const isCalculatorTool = toolNameLower.includes('calculator') ||
                          toolNameLower.includes('calc') ||
                          toolNameLower.includes('math')

  if (!isCalculatorTool) return false

  return typeof parsedData.value === 'number'
})

// 格式化数据用于默认展示
const formatData = (data) => {
  if (typeof data === 'object') {
    return JSON.stringify(data, null, 2)
  }
  return String(data)
}
</script>

<style lang="less" scoped>
.tool-result-renderer {
  width: 100%;

  .default-result {
    background: var(--gray-0);
    border-radius: 8px;
    border: 1px solid var(--gray-200);

    .default-header {
      padding: 12px 16px;
      border-bottom: 1px solid var(--gray-200);
      background: var(--gray-50);

      h4 {
        margin: 0;
        color: var(--main-color);
        font-size: 14px;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 6px;
      }
    }

    .default-content {
      background: var(--gray-0);
      padding: 12px;

      pre {
        margin: 0;
        font-size: 12px;
        line-height: 1.4;
        color: var(--gray-700);
        white-space: pre-wrap;
        word-break: break-word;
        max-height: 300px;
        overflow-y: auto;
        background: var(--gray-50);
        padding: 10px;
        border-radius: 4px;
        border-left: 2px solid var(--main-color);
      }
    }
  }
}
</style>