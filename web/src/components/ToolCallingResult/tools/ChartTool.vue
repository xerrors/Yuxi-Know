<template>
  <BaseToolCall :tool-call="toolCall">
    <template #result="{ resultContent }">
      <div class="chart-result">
        <img :src="chartUrl" />
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import { computed } from 'vue'
import BaseToolCall from '../BaseToolCall.vue'

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

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

const parsedContent = computed(() => {
  return parseData(props.toolCall.tool_call_result?.content)
})

const chartUrl = computed(() => {
  const content = parsedContent.value
  // chart 返回数组格式 [{ type: "text", text: "url", id: "..." }]
  if (Array.isArray(content) && content.length > 0 && content[0].type === 'text') {
    return content[0].text
  }
  return null
})
</script>

<style lang="less" scoped>
.chart-result {
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 8px;

  img {
    max-width: 100%;
    border-radius: 4px;
  }
}
</style>
