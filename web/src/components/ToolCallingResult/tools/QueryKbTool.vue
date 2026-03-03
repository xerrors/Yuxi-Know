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
        <KbResultGroupedList :chunks="parsedData(resultContent)" />
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

const parseData = (content) => {
  if (typeof content === 'string') {
    try {
      return JSON.parse(content)
    } catch {
      return []
    }
  }
  return content || []
}

const parsedData = (content) => parseData(content)
</script>

<style scoped lang="less">
.query-kb-result {
  background: var(--gray-0);
  border-radius: 8px;
  padding: 4px;
}
</style>
