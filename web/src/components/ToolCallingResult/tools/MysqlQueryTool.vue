<template>
  <BaseToolCall :tool-call="toolCall">
    <template #header-success>
      <span class="sep-header">
        <span class="keywords">执行SQL查询：</span>
        <span class="description">{{
          truncateSql(extractSql(toolCall.args || toolCall.function?.arguments))
        }}</span>
      </span>
    </template>

    <template #params="{ args }">
      <div class="mysql-params">
        <pre class="sql-text">{{ extractSql(args) }}</pre>
      </div>
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

  // 如果是字符串，尝试解析为 JSON 后再转为格式化字符串
  if (typeof content === 'string') {
    try {
      const parsed = JSON.parse(content)
      return JSON.stringify(parsed, null, 2)
    } catch {
      return content
    }
  }

  // 如果是对象，直接格式化
  if (typeof content === 'object') {
    return JSON.stringify(content, null, 2)
  }

  return String(content)
}

const extractSql = (args) => {
  if (!args) return ''

  // 解析 args（可能是字符串或对象）
  let parsedArgs = args
  if (typeof args === 'string') {
    try {
      parsedArgs = JSON.parse(args)
    } catch {
      return args
    }
  }

  // 提取 sql 字段
  const sql = parsedArgs?.sql || parsedArgs?.query
  return sql || JSON.stringify(parsedArgs, null, 2)
}

const truncateSql = (sql, maxLength = 50) => {
  if (!sql) return ''
  // 移除换行符和多余空格
  const singleLine = sql.replace(/\s+/g, ' ').trim()
  if (singleLine.length <= maxLength) return singleLine
  return singleLine.slice(0, maxLength) + '...'
}
</script>

<style lang="less" scoped>
.mysql-params {
  .sql-text {
    margin: 0;
    font-size: 11px;
    line-height: 1.4;
    color: var(--gray-800);
    white-space: pre-wrap;
    word-break: break-word;
    padding: 6px;
    border-radius: 4px;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    max-height: 200px;
    overflow-y: auto;
  }
}

.mysql-result {
  // background: var(--gray-0);
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
