<template>
  <BaseToolCall :tool-call="toolCall">
    <template #header>
      <div class="sep-header">
        <span class="note">read_file</span>
        <span class="separator" v-if="filePath">|</span>
        <span class="description">
          <span class="code">{{ filePath }}</span>
          <span class="tag" v-if="lineRange">{{ lineRange }}</span>
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

const parsedArgs = computed(() => {
  const args = props.toolCall.args || props.toolCall.function?.arguments
  if (!args) return {}
  if (typeof args === 'object') return args
  try {
    return JSON.parse(args)
  } catch (e) {
    return {}
  }
})

const filePath = computed(() => {
  const path = parsedArgs.value.file_path || ''
  return path.startsWith('/') ? path.slice(1) : path
})

const lineRange = computed(() => {
  const offset = parsedArgs.value.offset
  const limit = parsedArgs.value.limit
  if (offset !== undefined && limit !== undefined) {
    return `Lines ${offset}-${Number(offset) + Number(limit)}`
  } else if (limit !== undefined) {
    return `First ${limit} lines`
  }
  return ''
})
</script>

<style lang="less" scoped>
.sep-header {
  .tag {
    color: var(--color-primary-600);
    background-color: var(--color-primary-50);
  }
}
</style>
