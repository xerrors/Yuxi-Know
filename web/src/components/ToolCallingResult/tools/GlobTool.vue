<template>
  <BaseToolCall :tool-call="toolCall">
    <template #header>
      <div class="sep-header">
        <span class="note">glob</span>
        <span class="separator" v-if="pattern">|</span>
        <span class="description">{{ pattern }}</span>
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
</script>

<style lang="less" scoped></style>
