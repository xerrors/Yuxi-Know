<template>
  <div class="yuxi-widget">
    <p v-if="!closed" class="widget-notice" role="status">组件生成中…</p>
    <div v-else-if="parsed.error" class="widget-error" role="alert">
      <p>无法展示组件：{{ parsed.error }}</p>
      <details>
        <summary>查看原始内容</summary>
        <pre>{{ source }}</pre>
      </details>
    </div>
    <template v-else>
      <WidgetNode :node="parsed.node" :disabled="disabled" @action="handleAction" @preview="preview = $event" />
      <p v-if="feedback" class="widget-notice" role="status">{{ feedback }}</p>
    </template>
    <Modal
      :open="Boolean(preview)"
      :footer="null"
      :closable="false"
      :mask-closable="false"
      width="100%"
      wrap-class-name="widget-image-viewer"
      :wrap-props="{ 'aria-label': '图片预览', 'aria-modal': true }"
      destroy-on-close
      @cancel="preview = null"
    >
      <div v-if="preview" class="widget-viewer-layout">
        <div class="widget-viewer-toolbar">
          <button type="button" class="widget-viewer-button" aria-label="关闭图片预览" @click="preview = null">
            <X :size="22" aria-hidden="true" />
          </button>
        </div>
        <div class="widget-viewer-stage">
          <div class="yuxi-widget widget-image-preview">
            <WidgetImage :key="preview.index" :node="previewNode" :previewable="false" />
          </div>
          <button
            v-if="preview.images.length > 1"
            type="button"
            class="widget-viewer-button widget-viewer-previous"
            aria-label="上一张"
            :disabled="preview.index === 0"
            @click="preview.index--"
          ><ChevronLeft :size="24" aria-hidden="true" /></button>
          <button
            v-if="preview.images.length > 1"
            type="button"
            class="widget-viewer-button widget-viewer-next"
            aria-label="下一张"
            :disabled="preview.index === preview.images.length - 1"
            @click="preview.index++"
          ><ChevronRight :size="24" aria-hidden="true" /></button>
        </div>
        <p class="widget-viewer-caption">{{ preview.images[preview.index].caption || previewNode.alt }}</p>
      </div>
    </Modal>
  </div>
</template>

<script setup>
import { computed, provide, ref, watch } from 'vue'
import WidgetNode from '@/shared/ui/WidgetNode.vue'
import WidgetImage from '@/shared/ui/WidgetImage.vue'
import { Modal } from 'ant-design-vue'
import { X, ChevronLeft, ChevronRight } from '@lucide/vue'
import { parseWidget } from '@/shared/lib/chatWidgets'
const props = defineProps({
  source: { type: String, required: true },
  closed: Boolean,
  disabled: Boolean,
  actionable: Boolean,
  imageLoader: { type: Function, default: null },
  sourceImageLoader: { type: Function, default: null }
})
provide('widgetImageLoader', computed(() => props.imageLoader))
provide('widgetSourceImageLoader', computed(() => props.sourceImageLoader))
const emit = defineEmits(['action'])
const feedback = ref('')
const preview = ref(null)
const previewNode = computed(() => {
  if (!preview.value) return null
  return {
    ...preview.value.images[preview.value.index],
    aspectRatio: undefined,
    fit: 'contain',
    caption: undefined
  }
})
watch([() => props.source, () => props.imageLoader, () => props.sourceImageLoader], () => {
  preview.value = null
})
watch(preview, (value, _previous, onCleanup) => {
  if (!value) return
  window.addEventListener('keydown', handlePreviewKeydown)
  onCleanup(() => window.removeEventListener('keydown', handlePreviewKeydown))
})
const parsed = computed(() => {
  if (!props.closed) return {}
  try {
    return { node: parseWidget(props.source) }
  } catch (error) {
    return { error: error.message }
  }
})

/** 图片预览的方向键只切换当前图片组。 */
function handlePreviewKeydown(event) {
  if (!preview.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    preview.value = null
    return
  }
  const index = preview.value.index
  if (event.key === 'ArrowLeft' && index > 0) {
    event.preventDefault()
    preview.value.index--
  } else if (event.key === 'ArrowRight' && index < preview.value.images.length - 1) {
    event.preventDefault()
    preview.value.index++
  }
}

/** 明确告知操作结果，避免把草稿动作显示成业务完成。 */
function handleAction(text) {
  if (props.disabled) return
  if (!props.actionable) {
    feedback.value = '请在会话中使用此组件'
    return
  }
  emit('action', text)
  feedback.value = '已填写到消息草稿，请检查后发送。'
}
</script>

<style lang="less">
.widget-image-viewer.ant-modal-wrap {
  background: var(--color-bg-container);

  .ant-modal {
    top: 0;
    width: 100% !important;
    max-width: none;
    margin: 0;
    padding: 0;
  }

  .ant-modal-content {
    height: 100dvh;
    padding: 0;
    border-radius: 0;
    box-shadow: none;
    background: transparent;
  }

  .ant-modal-body {
    height: 100%;
  }
}

.widget-viewer-layout {
  display: grid;
  grid-template-rows: 64px minmax(0, 1fr) 48px;
  height: 100%;
  color: var(--gray-900);
}

.widget-viewer-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 0 20px;
}

.widget-viewer-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 1px solid var(--gray-200);
  border-radius: 50%;
  background: var(--color-bg-container);
  color: var(--gray-900);
  cursor: pointer;

  &:hover:not(:disabled) { background: var(--gray-50); }
  &:disabled { opacity: 0.3; cursor: default; }
  &:focus-visible { outline: 2px solid var(--main-color); outline-offset: 3px; }
}

.widget-viewer-stage {
  position: relative;
  min-height: 0;
  padding: 0 84px;

  .yuxi-widget.widget-image-preview {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    margin: 0;

    .widget-image {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100%;
      border-radius: 0;
      background: transparent;
    }

    .widget-image img {
      width: 100%;
      height: 100%;
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
    }
  }
}

.widget-viewer-previous,
.widget-viewer-next {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
}
.widget-viewer-previous { left: 20px; }
.widget-viewer-next { right: 20px; }

.widget-viewer-caption {
  align-self: center;
  margin: 0;
  padding: 0 24px;
  overflow: hidden;
  color: var(--gray-600);
  font-size: 13px;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 600px) {
  .widget-viewer-toolbar { padding: 0 12px; }
  .widget-viewer-stage { padding: 0 12px; }
  .widget-viewer-previous { left: 12px; }
  .widget-viewer-next { right: 12px; }
}

.yuxi-widget,
.yk-markdown-preview .yuxi-widget {
  --widget-surface: var(--color-bg-container);
  --widget-field: var(--gray-25);
  --widget-hover: var(--gray-50);
  --widget-border: var(--gray-200);
  --widget-muted: var(--gray-600);
  --widget-on-solid: var(--color-text-inverse);
  --widget-shadow: 0 2px 6px var(--shadow-1);
  margin: 16px 0;
  color: var(--gray-900);
  font-size: 14px;
  line-height: 1.5;
  overflow-wrap: anywhere;
  color-scheme: light;
  .widget-node {
    min-width: 0;
  }
  .widget-card,
  .widget-listview {
    width: 100%;
    max-width: 440px;
    box-sizing: border-box;
    margin: 0;
    padding: 20px;
    border: 1px solid var(--widget-border);
    border-radius: 16px;
    background: var(--widget-surface);
    box-shadow: var(--widget-shadow);
  }
  .widget-card.widget-size-sm {
    max-width: 360px;
  }
  .widget-card.widget-size-lg {
    max-width: 560px;
  }
  .widget-card.widget-size-full {
    max-width: none;
  }
  .widget-card,
  .widget-col,
  .widget-listviewitem {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .widget-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }
  .widget-row > .widget-col {
    flex: 1 1 100px;
  }
  .widget-listview {
    list-style: none;
    padding: 4px;
  }
  .widget-listviewitem {
    padding: 16px;
    gap: 8px;
  }
  .widget-listviewitem + .widget-listviewitem {
    border-top: 1px solid var(--widget-border);
  }
  .widget-listviewitem:has(> .widget-listitem-action) {
    padding: 0;
  }
  .widget-listitem-action {
    display: flex;
    flex-direction: column;
    gap: inherit;
    align-items: inherit;
    width: 100%;
    padding: 16px;
    border: 0;
    border-radius: 12px;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: start;
    cursor: pointer;
  }
  .widget-listitem-action:hover:not(:disabled) {
    background: var(--widget-hover);
  }
  .widget-title,
  .widget-text,
  .widget-caption {
    margin: 0;
    color: inherit;
  }
  .widget-title {
    font-size: 20px;
    font-weight: 600;
    line-height: 1.35;
    letter-spacing: -0.02em;
  }
  .widget-text {
    font-size: 14px;
    white-space: pre-wrap;
  }
  .widget-caption,
  .widget-notice {
    font-size: 12px;
    color: var(--widget-muted);
  }
  .widget-notice {
    margin: 8px 0 0;
  }
  .widget-divider {
    width: 100%;
    margin: 4px 0;
    border: 0;
    border-top: 1px solid var(--widget-border);
  }
  .widget-spacer {
    flex: 1;
  }
  .widget-icon {
    flex-shrink: 0;
  }
  .widget-color-primary {
    color: var(--main-700);
  }
  .widget-color-secondary {
    color: var(--gray-700);
  }
  .widget-color-tertiary {
    color: var(--widget-muted);
  }
  .widget-color-success {
    color: var(--color-success-900);
  }
  .widget-color-warning {
    color: var(--second-700);
  }
  .widget-color-danger {
    color: var(--color-error-900);
  }
  .widget-color-info {
    color: var(--color-info-900);
  }
  .widget-tone-secondary {
    --widget-tone: var(--gray-900);
    --widget-soft: var(--gray-100);
  }
  .widget-tone-success {
    --widget-tone: var(--color-success-900);
    --widget-soft: var(--color-success-50);
  }
  .widget-tone-warning {
    --widget-tone: var(--second-700);
    --widget-soft: var(--color-warning-50);
  }
  .widget-tone-danger {
    --widget-tone: var(--color-error-900);
    --widget-soft: var(--color-error-50);
  }
  .widget-tone-info {
    --widget-tone: var(--color-info-900);
    --widget-soft: var(--color-info-50);
  }
  .widget-badge {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border: 1px solid transparent;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    line-height: 1.5;
  }
  .widget-badge.widget-size-sm {
    font-size: 11px;
    padding: 1px 6px;
  }
  .widget-badge.widget-size-lg {
    font-size: 13px;
    padding: 3px 10px;
  }
  .widget-variant-solid {
    background: var(--widget-tone);
    color: var(--widget-on-solid);
  }
  .widget-variant-soft {
    background: var(--widget-soft);
    color: var(--widget-tone);
  }
  .widget-variant-outline {
    background: transparent;
    border-color: var(--widget-border);
    color: var(--widget-tone);
  }
  .widget-badge.widget-variant-outline {
    border-color: var(--widget-tone);
  }
  .widget-pill {
    border-radius: 999px;
  }
  .widget-listitem-action:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .widget-listitem-action:focus-visible,
  summary:focus-visible {
    outline: 2px solid var(--main-700);
    outline-offset: 3px;
  }
  .widget-error {
    padding: 16px;
    border: 1px solid var(--widget-border);
    border-radius: 12px;
    background: var(--widget-surface);
  }
  .widget-error p {
    color: var(--color-error-900);
    margin: 0 0 8px;
  }
  .widget-error pre {
    max-height: 240px;
    overflow: auto;
    white-space: pre-wrap;
  }
  @media (max-width: 480px) {
    .widget-card {
      padding: 16px;
    }
  }
}
:root.dark .yuxi-widget {
  --widget-field: var(--gray-50);
  --widget-hover: var(--color-bg-elevated);
  --widget-border: var(--gray-150);
  --widget-muted: var(--gray-500);
  --widget-on-solid: var(--gray-50);
  --widget-shadow: none;
  color-scheme: dark;
}
</style>
