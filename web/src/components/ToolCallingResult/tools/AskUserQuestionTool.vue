<template>
  <BaseToolCall :tool-call="toolCall" hide-params>
    <template #header>
      <div class="sep-header">
        <span class="note">提问</span>
        <span class="separator">|</span>
        <span class="description">{{ shortQuestionSummary }}</span>
        <span v-if="userAnswer" class="tag tag-answered"> 已回答: {{ displayAnswer }} </span>
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

const questions = computed(() => {
  const rawQuestions = parsedArgs.value.questions
  if (!Array.isArray(rawQuestions)) return []

  return rawQuestions
    .map((item) => {
      if (!item || typeof item !== 'object') return null
      const question = String(item.question || '').trim()
      if (!question) return null
      const questionId = String(item.question_id || item.questionId || '').trim()
      return { questionId, question }
    })
    .filter(Boolean)
})

const shortQuestionSummary = computed(() => {
  if (!questions.value.length) return '无问题'

  const firstQuestion = questions.value[0].question
  const shortFirstQuestion =
    firstQuestion.length > 36 ? firstQuestion.slice(0, 36) + '...' : firstQuestion

  if (questions.value.length === 1) return shortFirstQuestion
  return `${shortFirstQuestion} 等 ${questions.value.length} 题`
})

// 用户答案
const userAnswer = computed(() => {
  const result = parsedResult.value
  if (!result) return null
  return result.user_answer || result.answer || null
})

const formatSingleAnswer = (answer) => {
  if (Array.isArray(answer)) {
    return answer.join(', ')
  }
  if (answer && typeof answer === 'object') {
    if (answer.type === 'other') {
      return `Other: ${String(answer.text || '').trim()}`
    }
    return JSON.stringify(answer)
  }
  return String(answer)
}

// 显示答案
const displayAnswer = computed(() => {
  const answer = userAnswer.value
  if (!answer) return ''

  if (Array.isArray(answer)) {
    return answer.join(', ')
  }

  if (answer && typeof answer === 'object') {
    if (answer.type === 'other') {
      return `Other: ${String(answer.text || '').trim()}`
    }

    const entries = Object.entries(answer)
    if (!entries.length) return ''

    const summary = entries
      .map(([questionId, value]) => {
        const title = String(questionId || '').trim()
        return `${title}: ${formatSingleAnswer(value)}`
      })
      .join(' | ')

    return summary.length > 120 ? summary.slice(0, 120) + '...' : summary
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
