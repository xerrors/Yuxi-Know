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
      ref="graphResultRef"
    />

    <!-- 待办事项结果 -->
    <TodoListResult
      v-else-if="isTodoListResult"
      :data="todoListData"
    />

    <!-- 计算器结果 -->
    <CalculatorResult
      v-else-if="isCalculatorResult"
      :data="parsedData"
    />

    <!-- 图片结果 -->
    <div v-else-if="isImageResult" class="image-result">
      <img :src="parsedData" />
    </div>

    <!-- 默认的原始数据展示 -->
    <div v-else class="default-result">
      <!-- <div class="default-header">
        <h4><ToolOutlined /> {{ toolName }} 执行结果</h4>
      </div> -->
      <div class="default-content">
        <pre>{{ formatData(parsedData) }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ToolOutlined } from '@ant-design/icons-vue'
import WebSearchResult from './WebSearchResult.vue'
import KnowledgeBaseResult from './KnowledgeBaseResult.vue'
import KnowledgeGraphResult from './KnowledgeGraphResult.vue'
import CalculatorResult from './CalculatorResult.vue'
import TodoListResult from './TodoListResult.vue'
import { useAgentStore } from '@/stores/agent';

const agentStore = useAgentStore()

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

const tool = computed(() => {
  return agentStore?.availableTools?.[props.toolName] || null
})


// 解析数据
const parsedData = computed(() => {
  if (typeof props.resultContent === 'string') {
    try {
      return JSON.parse(props.resultContent)
    } catch (error) {
      return props.resultContent
    }
  }
  return props.resultContent
})

const todoListData = computed(() => {
  if (props.toolName !== 'write_todos') return []
  
  const raw = props.resultContent
  
  // 1. Try from parsedData (JSON object)
  const data = parsedData.value
  if (data && typeof data === 'object') {
     if (Array.isArray(data)) return data
     if (data.todos && Array.isArray(data.todos)) return data.todos
  }
  
  // 2. Try parsing string if it matches specific pattern
  if (typeof raw === 'string') {
    let str = raw
    if (str.startsWith('Updated todo list to ')) {
      str = str.replace('Updated todo list to ', '')
    }
    
    // Try regex parsing for Python-like string
    const items = []
    // Matches {'content': '...', 'status': '...'} with escaped quotes support
    // content might contain escaped quotes
    const contentRegex = /'content':\s*'((?:[^'\\]|\\.)*)'/
    const statusRegex = /'status':\s*'((?:[^'\\]|\\.)*)'/
    
    // Split by "}, {" roughly, or just look for objects
    // Since it is a list of dicts, we can match individual dicts
    const dictRegex = /\{.*?\}/g
    const dictMatches = str.match(dictRegex)
    
    if (dictMatches) {
      for (const dictStr of dictMatches) {
        const contentMatch = dictStr.match(contentRegex)
        const statusMatch = dictStr.match(statusRegex)
        
        if (contentMatch && statusMatch) {
          items.push({
            content: contentMatch[1].replace(/\\'/g, "'").replace(/\\\\/g, "\\"),
            status: statusMatch[1]
          })
        }
      }
    }
    if (items.length > 0) return items
  }
  
  return []
})

const isTodoListResult = computed(() => {
  return props.toolName === 'write_todos' && todoListData.value.length > 0
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
  // 首先检查工具的 metadata
  const currentTool = tool.value
  if (currentTool && currentTool.metadata) {
    const metadata = currentTool.metadata
    const hasKnowledgebaseTag = metadata.tag && metadata.tag.includes('knowledgebase')
    const isNotLightrag = metadata.kb_type !== 'lightrag'

    if (hasKnowledgebaseTag && isNotLightrag) {
      const data = parsedData.value
      return Array.isArray(data) &&
             data.length > 0 &&
             data.every(item =>
               item &&
               typeof item === 'object' &&
               'content' in item &&
               'score' in item &&
               'metadata' in item
             )
    }
  }

  return false
})

const isImageResult = computed(() => {
  // 包含 chart 且返回值是url
  const data = parsedData.value
  const toolNameLower = props.toolName.toLowerCase()
  const isImageTool = toolNameLower.includes('chart')

  if (!isImageTool) return false

  return data && typeof data === 'string' && data.startsWith('http')
})

// 判断是否为知识图谱查询结果
const isKnowledgeGraphResult = computed(() => {
  const toolNameLower = props.toolName.toLowerCase()

  // 工具名称初步筛选 - 支持中英文关键词
  const hasGraphKeyword = toolNameLower.includes('graph') ||
                         toolNameLower.includes('图谱') ||
                         toolNameLower.includes('kg')

  const data = parsedData.value

  // 数据格式验证 - 核心判断依据
  const hasBasicStructure = data && typeof data === 'object'
  const hasTriples = hasBasicStructure && 'triples' in data
  const triplesIsArray = hasTriples && Array.isArray(data.triples)
  const triplesHasContent = triplesIsArray && data.triples.length > 0

  // 进一步验证triples数组的内容格式
  let triplesHasValidFormat = false
  if (triplesHasContent) {
    // 检查是否至少有一个有效的三元组
    triplesHasValidFormat = data.triples.some(triple => {
      return Array.isArray(triple) &&
             triple.length >= 3 &&
             triple.every(item => typeof item === 'string' && item.trim() !== '')
    })
  }

  // 最终判断：数据格式符合规范优先，工具名称作为辅助判断
  // 1. 如果数据格式完全符合规范，直接认为是知识图谱结果
  if (hasBasicStructure && triplesIsArray && triplesHasContent && triplesHasValidFormat) {
    return true
  }

  // 2. 如果数据格式基本符合且有相关关键词，也认为是知识图谱结果
  return hasTriples && triplesIsArray && hasGraphKeyword
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

// 图表结果的引用
const graphResultRef = ref(null)

// 提供给父组件调用的刷新方法
const refreshGraph = () => {
  if (graphResultRef.value && typeof graphResultRef.value.refreshGraph === 'function') {
    graphResultRef.value.refreshGraph()
  }
}

// 向父组件暴露方法
defineExpose({
  refreshGraph
})
</script>

<style lang="less" scoped>
.tool-result-renderer {
  width: 100%;
  height: 100%;

  .default-result {
    background: var(--gray-0);
    border-radius: 8px;

    .default-header {
      padding: 12px 16px;
      border-bottom: 1px solid var(--gray-100);
      background: var(--gray-25);

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
        // border-left: 2px solid var(--main-color);
      }
    }
  }

  .image-result {
    width: 100%;
    height: 100%;
    display: flex;
    justify-content: center;
    align-items: center;
  }

  img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
}
</style>