<template>
  <div v-if="hasAttachments" class="attachment-status">
    <a-popover
      v-model:open="detailsVisible"
      placement="topLeft"
      trigger="click"
      :overlay-class-name="'attachment-details-popover'"
    >
      <template #content>
        <div class="attachment-details">
          <div class="details-header">
            <span class="header-title">已上传附件</span>
          </div>
          <div class="attachment-list">
            <div
              v-for="attachment in attachments"
              :key="attachment.file_id"
              class="attachment-item"
            >
              <div class="file-info">
                <component :is="getFileIcon(attachment.file_type)" :size="15" class="file-icon" />
                <div class="file-details">
                  <div class="file-name">{{ attachment.file_name }}</div>
                  <div class="file-meta">
                    {{ formatFileSize(attachment.file_size) }} ·
                    {{ getStatusLabel(attachment.status) }}
                  </div>
                </div>
              </div>
              <a-button
                type="link"
                class="remove-btn"
                @click="handleRemoveAttachment(attachment.file_id)"
                :disabled="disabled"
              >
                <X :size="15" />
              </a-button>
            </div>
          </div>
        </div>
      </template>

      <a-button type="text" size="small" class="status-indicator has-multiple" :disabled="disabled">
        <template #icon>
          <Paperclip :size="14" />
        </template>
        <span class="attachment-count">
          {{ attachments.length }}
        </span>
      </a-button>
    </a-popover>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Paperclip, FileText, File, X } from 'lucide-vue-next'

const props = defineProps({
  attachments: {
    type: Array,
    default: () => []
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['remove'])

const detailsVisible = ref(false)

// 是否有附件
const hasAttachments = computed(() => {
  return props.attachments && props.attachments.length > 0
})

// 根据文件类型获取图标
const getFileIcon = (fileType) => {
  const iconMap = {
    'text/plain': FileText,
    'text/markdown': FileText,
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': File,
    'text/html': File,
    'text/htm': File
  }
  return iconMap[fileType] || File
}

// 格式化文件大小
const formatFileSize = (bytes) => {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

// 获取状态标签
const getStatusLabel = (status) => {
  const statusMap = {
    uploaded: '已上传',
    processing: '处理中',
    parsed: '已解析',
    failed: '解析失败',
    pending: '待处理'
  }
  return statusMap[status] || status || '未知'
}

// 处理删除附件
const handleRemoveAttachment = (fileId) => {
  if (props.disabled) return
  emit('remove', fileId)
}
</script>

<style lang="less" scoped>
.attachment-status {
  display: flex;
  align-items: center;
}

.status-indicator {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--gray-600);
  transition: all 0.2s ease;
  position: relative;
  border: 1px solid transparent;
  background-color: transparent;

  &:hover:not(:disabled) {
    color: var(--main-color);
  }

  &:active:not(:disabled) {
    color: var(--main-color);
    transform: scale(0.95);
  }

  &.has-multiple {
    .attachment-count {
      position: absolute;
      top: -4px;
      right: -4px;
      background-color: var(--main-500);
      color: var(--gray-0);
      border-radius: 10px;
      width: 18px;
      height: 18px;
      font-size: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 600;
      border: 2px solid var(--gray-0);
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}
</style>

<style lang="less">
.attachment-details-popover {
  .ant-popover-inner-content {
    padding: 0;
  }

  .ant-popover-inner {
    border-radius: 8px;
    border: 1px solid var(--border);
    box-shadow:
      0 10px 15px -3px rgb(0 0 0 / 0.1),
      0 4px 6px -4px rgb(0 0 0 / 0.1);
  }

  .ant-popover-arrow {
    &::before {
      border: 1px solid var(--border);
    }
  }
}

.attachment-details {
  min-width: 260px;
  max-width: 320px;

  .details-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    background-color: var(--muted);

    .header-icon {
      color: var(--main-500);
    }

    .header-title {
      font-weight: 600;
      color: var(--foreground);
      font-size: 12px;
    }
  }

  .attachment-list {
    max-height: 300px;
    overflow-y: auto;
  }

  .attachment-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
    border-radius: 8px;
    transition: background-color 0.15s ease;

    &:last-child {
      border-bottom: none;
    }

    &:hover {
      background-color: var(--gray-50);
    }

    .file-info {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1;
      min-width: 0;
      cursor: pointer;

      .file-icon {
        color: var(--main-500);
        flex-shrink: 0;
      }

      .file-details {
        flex: 1;
        min-width: 0;

        .file-name {
          font-size: 12px;
          font-weight: 500;
          color: var(--foreground);
          margin-bottom: 1px;
          word-break: break-all;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .file-meta {
          font-size: 10px;
          color: var(--muted-foreground);
        }
      }
    }

    .remove-btn {
      color: var(--muted-foreground);
      flex-shrink: 0;
      border-radius: 4px;
      transition: all 0.15s ease;

      &:hover:not(:disabled) {
        color: var(--color-error-500);
      }

      &:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
    }
  }
}
</style>
