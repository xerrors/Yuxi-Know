<template>
  <MarkdownPreview
    :content="content"
    :references="citations"
    widgets
    :widgets-disabled="widgetsDisabled"
    :widget-action="widgetAction"
    :widget-image-loader="widgetImageLoader"
    code-copy
    class="message-md"
    @open-reference="openReference"
  />
  <a-modal v-model:open="snippetOpen" :title="selected?.source.title" :footer="null">
    <p class="reference-quote">{{ selected?.quote }}</p>
    <p class="reference-location-notice">此来源暂不支持原文行定位。</p>
  </a-modal>
  <FileDetailModal
    v-if="selected?.source.kind === 'knowledge' && selected.source.supports_documents && selected.source.file_id"
    v-model:open="fileOpen"
    :kb-id="selected.source.kb_id"
    :file-id="selected.source.file_id"
    :start-line="selected.source_start_line"
    :end-line="selected.source_end_line"
    :reference-source="selected.source"
  />
</template>

<script setup>
import { computed, ref } from 'vue'
import { threadApi } from '@/apis/agent_api'
import MarkdownPreview from '@/modules/workspace/ui/MarkdownPreview.vue'
import FileDetailModal from '@/modules/knowledge/ui/FileDetailModal.vue'
import { useTurnReferencesStore } from '@/modules/session/model/turnReferences'

const props = defineProps({
  widgetsDisabled: Boolean,
  widgetAction: { type: Function, default: null },
  content: { type: String, default: '' },
  threadId: { type: String, default: '' },
  message: { type: Object, required: true }
})
const widgetImageLoader = computed(() => {
  const threadId = props.threadId
  return threadId ? (path) => threadApi.previewThreadArtifact(threadId, path) : null
})
const store = useTurnReferencesStore()
const selected = ref(null)
const snippetOpen = ref(false)
const fileOpen = ref(false)
const citations = computed(() => {
  if (!props.threadId || !props.message.turn_id || props.message.phase !== 'final_answer') return []
  const entry = store.getEntry(props.threadId, props.message.turn_id)
  if (!entry.visible || !entry.references) return []
  const byId = new Map(entry.references.sources.map((source) => [source.id, source]))
  return entry.references.citations.flatMap((citation) => {
    const resolved = byId.get(citation.source_id)
    return resolved ? [{ ...citation, source: resolved }] : []
  })
})

function openReference(citation) {
  selected.value = citation
  if (citation.source.kind === 'web') {
    const url = new URL(citation.source.url)
    if (['http:', 'https:'].includes(url.protocol)) window.open(url.href, '_blank', 'noopener,noreferrer')
    return
  }
  if (citation.source.supports_documents && citation.source.file_id) fileOpen.value = true
  else snippetOpen.value = true
}
</script>

<style scoped lang="less">
.reference-quote { white-space: pre-wrap; }
.reference-location-notice { color: var(--gray-600); font-size: 12px; }
</style>
