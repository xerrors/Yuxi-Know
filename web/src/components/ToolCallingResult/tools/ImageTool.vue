<template>
  <BaseToolCall :tool-call="toolCall">
    <template #result="{ resultContent }">
      <div class="image-result">
        <img :src="parseData(resultContent)" />
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
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
    } catch (error) {
      return content
    }
  }
  return content
}
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
</style>
