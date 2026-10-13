<template>
  <figure
    class="widget-image"
    :class="{
      'has-aspect-ratio': node.aspectRatio || thumbnail,
      'is-loading': !loaded && !failed,
      'is-error': failed,
      'is-previewable': previewable && loaded && !failed
    }"
    :style="{ aspectRatio: thumbnail ? 5 / 4 : node.aspectRatio }"
    :role="previewable ? 'button' : undefined"
    :tabindex="previewable && loaded && !failed ? 0 : undefined"
    :aria-label="previewable ? `查看图片：${node.alt}` : undefined"
    @click="openPreview"
    @keydown="handlePreviewKeydown"
    :aria-busy="!loaded && !failed"
    :aria-disabled="previewable ? !loaded || failed : undefined"
  >
    <img
      v-if="src"
      v-show="!failed"
      :src="src"
      :alt="node.alt"
      :style="{ objectFit: thumbnail ? 'cover' : node.fit || 'contain' }"
      :loading="thumbnail ? 'eager' : 'lazy'"
      referrerpolicy="no-referrer"
      @load="loaded = true; failed = false"
      @error="failed = true"
    />
    <figcaption v-if="loaded && !failed && node.caption" class="widget-image-caption">{{ node.caption }}</figcaption>
    <p v-if="failed" class="widget-image-status" role="alert">图片无法加载：{{ node.alt }}</p>
    <p v-else-if="!loaded" class="widget-image-status" role="status">图片加载中…</p>
  </figure>
</template>

<script setup>
import { inject, ref, watch } from 'vue'
const props = defineProps({
  node: { type: Object, required: true },
  thumbnail: Boolean,
  previewable: { type: Boolean, default: true }
})
const emit = defineEmits(['preview'])
const imageLoader = inject('widgetImageLoader', ref(null))
const sourceImageLoader = inject('widgetSourceImageLoader', ref(null))
const src = ref('')
const loaded = ref(false)
const failed = ref(false)

/** 只有已加载图片可以打开预览，键盘与指针共用入口。 */
function openPreview(event) {
  if (!props.previewable || !loaded.value || failed.value) return
  event.currentTarget.focus()
  emit('preview')
}

/** 保留非交互图片所在列表项的默认键盘动作。 */
function handlePreviewKeydown(event) {
  if (props.previewable && ['Enter', ' '].includes(event.key)) {
    event.preventDefault()
    openPreview(event)
  }
}

watch(
  [
    () => props.node.src,
    () => props.node.path,
    () => props.node.path !== undefined ? imageLoader.value : null,
    () => props.node.src !== undefined ? sourceImageLoader.value : null
  ],
  async ([source, path, loader, sourceLoader], _previous, onCleanup) => {
    let disposed = false
    let objectUrl
    onCleanup(() => {
      disposed = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    })
    src.value = ''
    loaded.value = false
    failed.value = false
    try {
      let response
      if (path !== undefined) {
        if (!loader) throw new Error('缺少会话图片读取能力')
        response = await loader(path)
      } else {
        response = sourceLoader ? await sourceLoader(source) : null
        if (!response) {
          if (!disposed) src.value = source
          return
        }
      }
      const blob = await response.blob()
      if (disposed) return
      if (!blob.type.startsWith('image/')) throw new Error('文件无法作为图片预览')
      objectUrl = URL.createObjectURL(blob)
      src.value = objectUrl
    } catch {
      if (!disposed) failed.value = true
    }
  },
  { immediate: true }
)
</script>

<style lang="less">
.yuxi-widget .widget-image {
  position: relative;
  width: 100%;
  max-width: 100%;
  margin: 0;
  overflow: hidden;
  border-radius: 16px;

  img {
    display: block;
    width: 100%;
    height: auto;
    max-width: 100%;
  }

  &.has-aspect-ratio img {
    width: 100%;
    height: 100%;
  }

  &.is-loading,
  &.is-error {
    width: 100%;
    background: var(--widget-field);
  }

  &.is-previewable {
    cursor: zoom-in;
  }

  &:focus-visible {
    outline: 2px solid var(--main-color);
    outline-offset: -2px;
  }

  .widget-image-caption {
    position: absolute;
    bottom: 10px;
    left: 10px;
    display: block;
    max-width: calc(100% - 20px);
    box-sizing: border-box;
    padding: 5px 10px;
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 999px;
    color: var(--color-text-inverse);
    background: rgba(40, 40, 40, 0.64);
    backdrop-filter: blur(8px);
    font-size: 12px;
    line-height: 1.4;
    pointer-events: none;
    text-align: left;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .widget-image-status {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 12px 16px;
    margin: 0;
    font-size: 13px;
    color: var(--widget-muted);
  }

  &.has-aspect-ratio .widget-image-status {
    position: absolute;
    inset: 0;
    padding: 16px;
  }
}

.yuxi-widget .widget-imagegroup {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: max(120px, calc((100% - 32px) / 3));
  gap: 16px;
  width: 100%;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scroll-snap-type: x proximity;
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }

  > .widget-image {
    scroll-snap-align: start;
  }
}
</style>
