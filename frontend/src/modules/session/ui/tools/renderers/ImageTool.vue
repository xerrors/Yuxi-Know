<template>
  <BaseToolCall :tool-call="toolCall">
    <template #header>
      <div class="sep-header">
        <span class="note">生成图片</span>
      </div>
    </template>
    <template #result="{}">
      <ToolResultContent :content="resultContent" image-urls />
    </template>
  </BaseToolCall>
</template>

<script setup>
import { computed } from 'vue'
import BaseToolCall from '../BaseToolCall.vue'
import ToolResultContent from '../ToolResultContent.vue'
import { getToolCallResultContent } from '@/modules/session/model/toolCallProjection'

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

const resultContent = computed(() => getToolCallResultContent(props.toolCall))
</script>
