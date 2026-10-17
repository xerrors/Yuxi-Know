<template>
  <BaseToolCall :tool-call="toolCall">
    <template #result="{ resultContent }">
      <div class="web-fetch-result">
        <template v-if="resultData?.content">
          <strong>{{ resultData.title || '网页正文' }}</strong>
          <p>{{ resultData.provider }} · {{ resultData.url }}</p>
          <pre>{{ resultData.content }}</pre>
        </template>
        <p v-else>{{ resultData?.error || resultContent }}</p>
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import { computed } from 'vue'
import BaseToolCall from '../BaseToolCall.vue'
import { parseToolCallResult } from '../toolRegistry'

const props = defineProps({ toolCall: { type: Object, required: true } })
const resultData = computed(() => parseToolCallResult(props.toolCall))
</script>

<style scoped lang="less">
.web-fetch-result { padding: 12px; overflow-wrap: anywhere; }
p { color: var(--gray-600); font-size: 12px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 480px; overflow: auto; font-size: 12px; }
</style>
