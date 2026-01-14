<template>
  <div class="attachment-panel">
    <label class="attachment-upload" :class="{ disabled: disabled || isUploading }">
      <input
        type="file"
        multiple
        accept=".txt,.md,.docx,.html,.htm"
        :disabled="disabled || isUploading"
        @change="handleFileChange"
      />
      <Paperclip size="14" />
      <span>{{ isUploading ? '上传中…' : '添加附件' }}</span>
    </label>

    <p class="attachment-hint" v-if="limits">支持 {{ extensionsText }}，单文件 ≤ {{ sizeHint }}</p>

    <div class="attachment-list" v-if="attachments.length">
      <div class="attachment-chip" v-for="item in attachments" :key="item.file_id">
        <Paperclip size="14" class="chip-icon" />
        <span class="chip-name" :title="item.file_name">{{ item.file_name }}</span>
        <span class="chip-status" :class="`status-${item.status}`">
          {{ statusLabel(item) }}
        </span>
        <a-tooltip title="移除附件">
          <a-button
            type="text"
            size="small"
            class="chip-remove"
            :disabled="disabled"
            @click="$emit('remove', item.file_id)"
          >
            <template #icon>
              <Trash2 size="14" />
            </template>
          </a-button>
        </a-tooltip>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Paperclip, Trash2 } from 'lucide-vue-next'

const props = defineProps({
  attachments: { type: Array, default: () => [] },
  limits: { type: Object, default: () => null },
  isUploading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false }
})

const emit = defineEmits(['upload', 'remove'])

const extensionsText = computed(() => {
  if (!props.limits?.allowed_extensions?.length) return 'txt/md/docx/html'
  return props.limits.allowed_extensions.map((item) => item.replace('.', '')).join(' / ')
})

const sizeHint = computed(() => {
  if (!props.limits?.max_size_bytes) return '5 MB'
  const mb = props.limits.max_size_bytes / (1024 * 1024)
  return `${mb.toFixed(1)} MB`
})

const statusLabel = (item) => {
  if (item.status === 'parsed') {
    return item.truncated ? '已解析（截断）' : '已解析'
  }
  if (item.status === 'failed') return '解析失败'
  return '处理中'
}

const handleFileChange = (event) => {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  emit('upload', files)
}
</script>

<style scoped>
.attachment-panel {
  min-width: 220px;
  max-width: 320px;
}

.attachment-upload {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--main-700);
  cursor: pointer;
  font-weight: 500;
}

.attachment-upload.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.attachment-upload input {
  display: none;
}

.attachment-hint {
  margin: 4px 0 8px;
  font-size: 11px;
  color: var(--gray-500);
  line-height: 1.4;
}

.attachment-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 220px;
  overflow-y: auto;
}

.attachment-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: var(--gray-25);
  border: 1px solid var(--gray-100);
  border-radius: 6px;
}

.chip-icon {
  color: var(--gray-600);
}

.chip-name {
  flex: 1;
  font-size: 12px;
  color: var(--gray-800);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-status {
  font-size: 11px;
  color: var(--gray-600);
}

.chip-status.status-parsed {
  color: var(--color-success-600);
}

.chip-status.status-failed {
  color: var(--color-error-600);
}

.chip-remove {
  margin-left: 2px;
  color: var(--gray-500);
}

.chip-remove:hover {
  color: var(--gray-700);
}
</style>
