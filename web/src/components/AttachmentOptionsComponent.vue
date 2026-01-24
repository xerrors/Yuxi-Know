<template>
  <div class="attachment-options">
    <div class="option-item">
      <label class="attachment-upload-label" :class="{ disabled: disabled }">
        <input
          ref="fileInputRef"
          type="file"
          multiple
          accept=".txt,.md,.docx,.html,.htm"
          :disabled="disabled"
          @change="handleFileChange"
          style="display: none"
        />
        <a-tooltip title="支持 txt/md/docx/html 格式 ≤ 5 MB" placement="right">
          <div class="option-content">
            <FileText :size="18" class="option-icon" />
            <span class="option-text">添加附件</span>
          </div>
        </a-tooltip>
      </label>
    </div>

    <div class="option-item" @click="handleImageUpload">
      <a-tooltip title="支持 jpg/jpeg/png/gif， ≤ 5 MB" placement="right">
        <div class="option-content">
          <Image :size="18" class="option-icon" />
          <span class="option-text">上传图片</span>
        </div>
      </a-tooltip>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { FileText, Image } from 'lucide-vue-next'
import { message } from 'ant-design-vue'
import { multimodalApi } from '@/apis/agent_api'

const fileInputRef = ref(null)
const imageInputRef = ref(null)

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['upload', 'upload-image', 'upload-image-success'])

// 处理文件选择变化
const handleFileChange = (event) => {
  const files = event.target.files
  if (files && files.length > 0) {
    emit('upload', Array.from(files))
  }
  // 清空文件输入，允许重复选择同一文件
  event.target.value = ''
}

// 处理图片上传
const handleImageUpload = () => {
  if (props.disabled) return

  // 创建隐藏的文件输入
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*'
  input.multiple = false
  input.style.display = 'none'

  input.onchange = async (event) => {
    const file = event.target.files[0]
    if (file) {
      await processImageUpload(file)
    }
    document.body.removeChild(input)
  }

  document.body.appendChild(input)
  input.click()

  emit('upload-image')
}

// 处理图片上传逻辑
const processImageUpload = async (file) => {
  try {
    // 验证文件大小（10MB）
    if (file.size > 10 * 1024 * 1024) {
      message.error('图片文件过大，请选择小于10MB的图片')
      return
    }

    // 验证文件类型
    if (!file.type.startsWith('image/')) {
      message.error('请选择有效的图片文件')
      return
    }

    message.loading({ content: '正在处理图片...', key: 'image-upload' })

    const result = await multimodalApi.uploadImage(file)

    if (result.success) {
      message.success({
        content: '图片处理成功',
        key: 'image-upload',
        duration: 2
      })

      // 发出上传成功事件，包含处理后的图片数据
      emit('upload-image', {
        success: true,
        imageContent: result.image_content,
        thumbnailContent: result.thumbnail_content,
        width: result.width,
        height: result.height,
        format: result.format,
        mimeType: result.mime_type || file.type,
        sizeBytes: result.size_bytes,
        originalName: file.name
      })

      // 发出上传成功通知事件，用于关闭选项面板
      emit('upload-image-success')
    } else {
      message.error({
        content: `图片处理失败: ${result.error}`,
        key: 'image-upload'
      })
    }
  } catch (error) {
    console.error('图片上传失败:', error)
    message.error({
      content: `图片上传失败: ${error.message || '未知错误'}`,
      key: 'image-upload'
    })
  }
}
</script>

<style lang="less" scoped>
.attachment-options {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 120px;
}

.option-item {
  cursor: pointer;
  transition: all 0.2s ease;

  &:active {
    transform: scale(0.98);
  }

  &.disabled {
    cursor: not-allowed;
    opacity: 0.5;

    .option-content {
      color: var(--gray-400);
    }
  }
}

.option-content {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  color: var(--gray-700);
  font-size: 14px;
  border-radius: 6px;
  transition: all 0.15s ease;

  .option-item:hover & {
    color: var(--main-color);
    background-color: var(--gray-50);
  }
}

.option-icon {
  flex-shrink: 0;
  color: inherit;
}

.option-text {
  font-weight: 500;
}

.attachment-upload-label {
  display: block;
  width: 100%;
  cursor: pointer;

  &.disabled {
    cursor: not-allowed;
    opacity: 0.5;

    .option-content {
      color: var(--gray-400);
    }
  }
}
</style>
