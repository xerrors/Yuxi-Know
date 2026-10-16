<template>
  <Modal
    :open="Boolean(src)"
    :footer="null"
    :closable="false"
    width="100%"
    wrap-class-name="chat-image-viewer"
    :wrap-props="{ 'aria-label': '图片预览' }"
    destroy-on-close
    @cancel="emit('close')"
  >
    <button
      type="button"
      class="chat-image-viewer-close"
      aria-label="关闭图片预览"
      @click="emit('close')"
    >
      <X :size="20" aria-hidden="true" />
    </button>
    <img
      v-if="src"
      :src="src"
      :alt="alt"
      referrerpolicy="no-referrer"
      class="chat-image-viewer-image"
    />
  </Modal>
</template>

<script setup>
import { Modal } from 'ant-design-vue'
import { X } from '@lucide/vue'

defineProps({
  src: { type: String, default: '' },
  alt: { type: String, default: '图片预览' }
})
const emit = defineEmits(['close'])
</script>

<style lang="less">
.chat-image-viewer {
  .ant-modal {
    top: 0;
    height: 100%;
    padding: 0;
    margin: 0;
    max-width: 100vw;
  }

  .ant-modal-content {
    height: 100dvh;
    padding: 0;
    background: transparent;
    box-shadow: none;
    pointer-events: none;
  }

  .ant-modal-body {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .chat-image-viewer-image {
    max-width: 90vw;
    max-height: 90vh;
    object-fit: contain;
    border-radius: 4px;
  }

  .chat-image-viewer-close {
    position: fixed;
    top: 1.5rem;
    right: 1.5rem;
    width: 2.5rem;
    height: 2.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 50%;
    color: var(--color-text-inverse);
    background: rgba(255, 255, 255, 0.15);
    cursor: pointer;
    pointer-events: auto;

    &:hover {
      background: rgba(255, 255, 255, 0.28);
    }

    &:focus-visible {
      outline: 2px solid var(--main-color);
      outline-offset: 2px;
    }
  }
}
</style>
