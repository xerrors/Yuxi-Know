<template>
  <div class="image-preview" v-if="imageData">
    <div class="image-container">
      <img
        :src="`data:${imageData.mimeType};base64,${imageData.imageContent}`"
        :alt="imageData.originalName"
        class="preview-image"
      />
      <button class="remove-button" @click="handleRemove">
        <X />
      </button>
    </div>
  </div>
</template>

<script setup>
import { X } from 'lucide-vue-next'

const props = defineProps({
  imageData: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['remove'])

// 移除图片
const handleRemove = () => {
  emit('remove')
}
</script>

<style lang="less" scoped>
.image-container {
  position: relative;
  display: inline-block;
  overflow: hidden;
}

.preview-image {
  width: 80px;
  height: 80px;
  object-fit: cover;
  display: block;
  border-radius: 8px;
  border: 1px solid var(--gray-200);
}

.remove-button {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.2);
  color: var(--gray-0);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.15s ease;

  &:hover {
    background: rgba(0, 0, 0, 0.3);
  }
}
</style>
