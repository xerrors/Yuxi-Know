<template>
  <BaseToolCall :tool-call="toolCall">
    <template #result="{}">
      <div v-if="imageUrl" class="image-result">
        <img :src="imageUrl" />
      </div>
      <div v-else class="text-result">
        {{ parsedContent }}
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

const parseData = (content) => {
  if (typeof content === 'string') {
    try {
      return JSON.parse(content)
    } catch {
      return content
    }
  }
  return content
}

const parsedContent = computed(() => {
  return parseData(props.toolCall.tool_call_result?.content)
})

const imageUrl = computed(() => {
  const content = parsedContent.value
  // text_to_img_qwen_image 返回 URL 字符串
  if (content && typeof content === 'string' && content.startsWith('http')) {
    return content
  }
  return null
})
</script>

<style lang="less" scoped>
.image-result {
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 8px;

  img {
    max-width: 100%;
    border-radius: 4px;
  }
}

.text-result {
  padding: 8px;
  color: var(--color-text);
}
</style>
