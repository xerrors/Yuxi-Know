<template>
  <BaseToolCall :tool-call="toolCall" :hide-params="true">
    <template #header>
      <div class="sep-header">
        <span class="note">{{ operationLabel }}</span>
      </div>
    </template>
    <template #result="{ resultContent }">
      <div class="list-kbs-result">
        <div class="kb-count">共 {{ kbList.length }} 个知识库</div>
        <div class="kb-list">
          <div v-for="kb in kbList" :key="kb.name" class="kb-item">
            <div class="kb-name">{{ kb.name }}</div>
            <div class="kb-description">{{ kb.description || '无描述' }}</div>
          </div>
        </div>
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

const toolName = computed(() => props.toolCall.name || props.toolCall.function?.name || '知识库')

const operationLabel = computed(() => `${toolName.value} 列表`)

const parseData = (content) => {
  if (typeof content === 'string') {
    try {
      return JSON.parse(content)
    } catch {
      return []
    }
  }
  return content || []
}

const kbList = computed(() => {
  const resultContent = props.toolCall.tool_call_result?.content
  const data = parseData(resultContent)
  return Array.isArray(data) ? data : []
})
</script>

<style scoped lang="less">
.list-kbs-result {
  background: var(--gray-0);
  border-radius: 8px;
  padding: 12px 16px;

  .kb-count {
    font-size: 12px;
    color: var(--gray-700);
    margin-bottom: 12px;
  }

  .kb-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .kb-item {
    padding: 10px 12px;
    background: var(--gray-10);
    border-radius: 6px;
    border: 1px solid var(--gray-100);

    .kb-name {
      font-size: 13px;
      font-weight: 500;
      color: var(--gray-700);
      margin-bottom: 4px;
    }

    .kb-description {
      font-size: 12px;
      color: var(--gray-600);
    }
  }
}
</style>
