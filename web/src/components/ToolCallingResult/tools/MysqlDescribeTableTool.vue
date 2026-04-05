<template>
  <BaseToolCall :tool-call="toolCall" :hide-params="true">
    <template #header-success>
      <span class="sep-header">
        <span class="keywords">描述表结构：</span>
        <span class="description code">{{
          extractTableName(toolCall.args || toolCall.function?.arguments)
        }}</span>
      </span>
    </template>

    <template #result="{ resultContent }">
      <div class="mysql-result">
        <pre class="result-text">{{ formatResult(resultContent) }}</pre>
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import BaseToolCall from '../BaseToolCall.vue'

defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

const formatResult = (content) => {
  if (!content) return ''

  if (typeof content === 'string') {
    try {
      const parsed = JSON.parse(content)
      return JSON.stringify(parsed, null, 2)
    } catch {
      return content
    }
  }

  if (typeof content === 'object') {
    return JSON.stringify(content, null, 2)
  }

  return String(content)
}

const extractTableName = (args) => {
  if (!args) return ''

  let parsedArgs = args
  if (typeof args === 'string') {
    try {
      parsedArgs = JSON.parse(args)
    } catch {
      return args
    }
  }

  return parsedArgs?.table_name || ''
}
</script>

<style lang="less" scoped>
.mysql-result {
  border-radius: 8px;
  padding: 12px;

  .result-text {
    margin: 0;
    font-size: 12px;
    line-height: 1.4;
    color: var(--gray-700);
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 400px;
    overflow-y: auto;
    background: var(--gray-50);
    padding: 10px;
    border-radius: 4px;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  }
}
</style>
