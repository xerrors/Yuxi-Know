<template>
  <BaseToolCall :tool-call="toolCall">
    <template #header>
      <div class="sep-header">
        <span class="note">{{ toolCallName }}</span>
        <span class="separator" v-if="filePath">|</span>
        <span class="description">
          <span class="code">{{ filePath }}</span>
          <span class="tag success" v-if="addedLines > 0">+{{ addedLines }}</span>
          <span class="tag error" v-if="removedLines > 0">-{{ removedLines }}</span>
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

const toolCallName = computed(
  () => props.toolCall.name || props.toolCall.function?.name || 'edit_file'
)

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

const addedLines = computed(() => {
  const newStr = parsedArgs.value.new_string || ''
  return newStr ? String(newStr).split('\n').length : 0
})

const removedLines = computed(() => {
  const oldStr = parsedArgs.value.old_string || ''
  return oldStr ? String(oldStr).split('\n').length : 0
})
</script>
