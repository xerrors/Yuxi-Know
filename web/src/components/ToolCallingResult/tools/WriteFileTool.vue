<template>
  <BaseToolCall :tool-call="toolCall">
    <template #header>
      <div class="sep-header">
        <span class="note">write_file</span>
        <span class="separator" v-if="filePath">|</span>
        <span class="description"
          >{{ filePath }} <span v-if="lineCount"> ({{ lineCount }} lines)</span></span
        >
      </div>
    </template>

    <template #result> </template>
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
const content = computed(() => parsedArgs.value.content || '')
const lineCount = computed(() => {
  if (!content.value) return 0
  return String(content.value).split('\n').length
})
</script>

<style lang="less" scoped></style>
