<template>
  <BaseToolCall :tool-call="toolCall" :hide-params="true">
    <template #header>
      <div class="sep-header">
        <span class="note">{{ toolCallName }}</span>
        <span class="separator" v-if="dirPath">|</span>
        <span class="description code">{{ dirPath }}</span>
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
  () => props.toolCall.name || props.toolCall.function?.name || 'list_directory'
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

const dirPath = computed(() => {
  return parsedArgs.value.dir_path || parsedArgs.value.path || ''
})
</script>

<style lang="less" scoped></style>
