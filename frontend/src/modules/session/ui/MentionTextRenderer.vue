<template>
  <span class="mention-text-renderer">
    <template v-for="segment in segments" :key="`${segment.kind}-${segment.start}-${segment.end}`">
      <span v-if="segment.kind === 'text'" class="mention-text-segment">{{ segment.text }}</span>
      <MentionToken
        v-else
        :type="segment.type"
        :value="segment.value"
        :label="getTokenLabel(segment)"
        :agent="agents.find((agent) => agent.agent_id === segment.value)"
        :class="{ 'mention-ref-editable': editable }"
        :contenteditable="editable ? 'false' : undefined"
        :data-mention-raw="editable ? segment.raw : undefined"
        :data-mention-type="editable ? segment.type : undefined"
        :data-mention-value="editable ? segment.value : undefined"
        :title="segment.raw"
      />
    </template>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { getMentionDisplayLabel, parseMentionText } from '@/modules/session/model/mention_utils'
import MentionToken from '@/modules/session/ui/MentionToken.vue'

const props = defineProps({
  content: {
    type: String,
    default: ''
  },
  editable: {
    type: Boolean,
    default: false
  },
  agents: {
    type: Array,
    default: () => []
  },
  displayLabels: {
    type: Object,
    default: () => ({})
  }
})

const segments = computed(() => parseMentionText(props.content))

const getTokenLabel = (segment) =>
  getMentionDisplayLabel(segment.type, segment.value, props.displayLabels)
</script>

<style lang="less" scoped>
.mention-text-renderer {
  white-space: inherit;
}

.mention-text-segment {
  white-space: inherit;
}
</style>
