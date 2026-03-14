<template>
  <BaseToolCall :tool-call="toolCall" hide-params>
    <template #header>
      <div class="sep-header">
        <span class="note">提问</span>
        <span class="separator">|</span>
        <span class="description">{{ shortQuestion }}</span>
        <span v-if="userAnswer" class="tag tag-answered">
          已回答: {{ displayAnswer }}
        </span>
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

// 解析参数
const parsedArgs = computed(() => {
  const args = props.toolCall.args || props.toolCall.function?.arguments
  if (!args) return {}
  if (typeof args === 'object') return args
  try {
    return JSON.parse(args)
  } catch {
    return {}
  }
})

// 解析结果
const parsedResult = computed(() => {
  const content = props.toolCall.tool_call_result?.content
  if (!content) return null
  if (typeof content === 'object') return content
  try {
    return JSON.parse(content)
  } catch {
    return null
  }
})

const question = computed(() => parsedArgs.value.question || '')
const shortQuestion = computed(() => {
  const q = question.value
  return q.length > 50 ? q.slice(0, 50) + '...' : q
})

// 用户答案
const userAnswer = computed(() => {
  const result = parsedResult.value
  if (!result) return null
  return result.user_answer || result.answer || null
})

// 显示答案
const displayAnswer = computed(() => {
  const answer = userAnswer.value
  if (!answer) return ''
  if (Array.isArray(answer)) {
    return answer.join(', ')
  }
  return String(answer)
})
</script>

<style lang="less" scoped>
.sep-header {
  .tag-answered {
    margin-left: 8px;
    color: var(--green-600);
    background: var(--green-50);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
  }
}
</style>
