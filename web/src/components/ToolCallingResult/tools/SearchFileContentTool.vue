<template>
  <BaseToolCall :tool-call="toolCall">
    <template #header>
      <div class="sep-header">
        <span class="note">search_file_content</span>
        <span class="separator" v-if="pattern">|</span>
        <span class="keywords">{{ pattern }}</span>
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

const pattern = computed(() => parsedArgs.value.pattern || '')
const dirPath = computed(() => parsedArgs.value.dir_path || '')
</script>

<style lang="less" scoped></style>
