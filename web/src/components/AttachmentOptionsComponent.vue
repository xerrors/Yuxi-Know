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
          style="display: none;"
        />
        <a-tooltip title="支持 txt/md/docx/html/htm 格式，单文件 ≤ 5 MB" placement="right">
          <div class="option-content">
            <FileText :size="16" class="option-icon" />
            <span class="option-text">添加附件</span>
          </div>
        </a-tooltip>
      </label>
    </div>

    <div class="option-item" @click="handleImageUpload">
      <a-tooltip title="支持 jpg/jpeg/png/gif 格式，单文件 ≤ 5 MB" placement="right">
        <div class="option-content">
          <Image :size="16" class="option-icon" />
          <span class="option-text">上传图片</span>
        </div>
      </a-tooltip>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { FileText, Image } from 'lucide-vue-next';
import { message } from 'ant-design-vue';

const fileInputRef = ref(null);

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(['upload', 'upload-image']);

// 处理文件选择变化
const handleFileChange = (event) => {
  const files = event.target.files;
  if (files && files.length > 0) {
    emit('upload', Array.from(files));
  }
  // 清空文件输入，允许重复选择同一文件
  event.target.value = '';
};

// 处理图片上传（开发中提示）
const handleImageUpload = () => {
  if (props.disabled) return;
  message.info('图片上传功能开发中，敬请期待！');
  emit('upload-image');
};
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
  gap: 8px;
  padding: 6px 10px;
  color: var(--gray-700);
  font-size: 13px;
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