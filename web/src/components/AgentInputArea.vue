<template>
  <MessageInputComponent
    ref="inputRef"
    :model-value="modelValue"
    @update:modelValue="updateValue"
    :is-loading="isLoading"
    :disabled="disabled"
    :send-button-disabled="sendButtonDisabled"
    :placeholder="placeholder"
    @send="handleSend"
    @keydown="handleKeyDown"
  >
    <template #top>
      <ImagePreviewComponent
        v-if="currentImage"
        :image-data="currentImage"
        @remove="handleImageRemoved"
        class="image-preview-wrapper"
      />
    </template>
    <template #options-left>
      <AttachmentOptionsComponent
        v-if="supportsFileUpload"
        :disabled="disabled"
        @upload="handleAttachmentUpload"
        @upload-image="handleImageUpload"
        @upload-image-success="handleImageUploadSuccess"
      />
    </template>
    <template #actions-left>
      <AttachmentStatusIndicator
        :attachments="currentAttachments"
        :disabled="disabled"
        @remove="handleAttachmentRemove"
      />
    </template>
  </MessageInputComponent>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import MessageInputComponent from '@/components/MessageInputComponent.vue'
import ImagePreviewComponent from '@/components/ImagePreviewComponent.vue'
import AttachmentOptionsComponent from '@/components/AttachmentOptionsComponent.vue'
import AttachmentStatusIndicator from '@/components/AttachmentStatusIndicator.vue'
import { threadApi } from '@/apis'
import { AgentValidator } from '@/utils/agentValidator'
import { handleChatError, handleValidationError } from '@/utils/errorHandler'

const props = defineProps({
  modelValue: { type: String, default: '' },
  isLoading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  sendButtonDisabled: { type: Boolean, default: false },
  placeholder: { type: String, default: '输入问题...' },
  supportsFileUpload: { type: Boolean, default: false },
  agentId: { type: String, default: '' },
  threadId: { type: String, default: null },
  ensureThread: { type: Function, required: true }
})

const emit = defineEmits(['update:modelValue', 'send', 'keydown'])

const inputRef = ref(null)
const currentImage = ref(null)
const attachmentState = reactive({
  itemsByThread: {},
  limits: null,
  isUploading: false
})

const updateValue = (val) => {
  emit('update:modelValue', val)
}

const currentAttachments = computed(() => {
  if (!props.threadId) return []
  return attachmentState.itemsByThread[props.threadId] || []
})

const loadThreadAttachments = async (threadId, { silent = false } = {}) => {
  if (!threadId) return
  try {
    const response = await threadApi.getThreadAttachments(threadId)
    attachmentState.itemsByThread[threadId] = response.attachments || []
    if (response.limits) {
      attachmentState.limits = response.limits
    }
  } catch (error) {
    if (silent) {
      console.warn('Failed to load attachments:', error)
    } else {
      handleChatError(error, 'load')
    }
  }
}

const handleImageUpload = (imageData) => {
  if (imageData && imageData.success) {
    currentImage.value = imageData
  }
}

const handleImageRemoved = () => {
  currentImage.value = null
}

const handleImageUploadSuccess = () => {
  if (inputRef.value) {
    inputRef.value.closeOptions()
  }
}

const handleAttachmentUpload = async (files) => {
  if (!files?.length) return
  if (!AgentValidator.validateAgentIdWithError(props.agentId, '上传附件', handleValidationError))
    return

  const preferredTitle = files[0]?.name || '新的对话'
  let threadId = props.threadId

  if (!threadId) {
    try {
      threadId = await props.ensureThread(preferredTitle)
    } catch (e) {
      return
    }
  }

  if (!threadId) {
    message.error('创建对话失败，无法上传附件')
    return
  }

  attachmentState.isUploading = true
  try {
    for (const file of files) {
      await threadApi.uploadThreadAttachment(threadId, file)
      message.success(`${file.name} 上传成功`)
    }
    await loadThreadAttachments(threadId, { silent: true })
  } catch (error) {
    handleChatError(error, 'upload')
  } finally {
    attachmentState.isUploading = false
  }
}

const handleAttachmentRemove = async (fileId) => {
  if (!fileId || !props.threadId) return
  try {
    await threadApi.deleteThreadAttachment(props.threadId, fileId)
    await loadThreadAttachments(props.threadId, { silent: true })
    message.success('附件已删除')
  } catch (error) {
    handleChatError(error, 'delete')
  }
}

const handleSend = () => {
  emit('send', { image: currentImage.value })
  currentImage.value = null
}

const handleKeyDown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  } else {
    emit('keydown', e)
  }
}

watch(
  () => props.threadId,
  (newId) => {
    if (newId) {
      loadThreadAttachments(newId, { silent: true })
    }
  },
  { immediate: true }
)

defineExpose({
  focus: () => inputRef.value?.focus(),
  closeOptions: () => inputRef.value?.closeOptions()
})
</script>
