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
      <WidgetNode :node="parsed.node" :disabled="disabled" @action="handleAction" />
      <p v-if="feedback" class="widget-notice" role="status">{{ feedback }}</p>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import WidgetNode from '@/shared/ui/WidgetNode.vue'
import { parseWidget } from '@/shared/lib/chatWidgets'
const props = defineProps({
  source: { type: String, required: true },
  closed: Boolean,
  disabled: Boolean,
  actionable: Boolean
})
const emit = defineEmits(['action'])
const feedback = ref('')
const parsed = computed(() => {
  if (!props.closed) return {}
  try {
    return { node: parseWidget(props.source) }
  } catch (error) {
    return { error: error.message }
  }
})

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
  .widget-form,
  .widget-listviewitem {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .widget-form {
    gap: 16px;
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
  .widget-tone-primary {
    --widget-tone: var(--main-700);
    --widget-soft: var(--main-50);
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
  .widget-button {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    min-height: 40px;
    max-width: 100%;
    padding: 8px 14px;
    font: inherit;
    font-weight: 500;
    line-height: 1.4;
    border: 1px solid transparent;
    border-radius: 8px;
    cursor: pointer;
    white-space: normal;
    transition:
      background-color 120ms,
      border-color 120ms;
  }
  .widget-button svg {
    flex-shrink: 0;
  }
  .widget-button.widget-size-sm {
    min-height: 32px;
    padding: 6px 10px;
    font-size: 12px;
  }
  .widget-button.widget-size-lg {
    min-height: 48px;
    padding: 12px 18px;
    font-size: 16px;
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
  .widget-variant-ghost {
    background: transparent;
    color: var(--widget-tone);
  }
  .widget-button:hover:not(:disabled) {
    background: var(--widget-soft);
  }
  .widget-button.widget-variant-solid:hover:not(:disabled) {
    background: var(--gray-700);
  }
  .widget-button.widget-tone-primary.widget-variant-solid:hover:not(:disabled) {
    background: var(--main-800);
  }
  .widget-button.widget-variant-outline:hover:not(:disabled) {
    border-color: var(--widget-tone);
  }
  .widget-pill {
    border-radius: 999px;
  }
  .widget-block {
    width: 100%;
    align-self: stretch;
  }
  .widget-button:disabled,
  .widget-listitem-action:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .widget-field {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }
  .widget-field > span {
    font-size: 13px;
    font-weight: 500;
  }
  .widget-required {
    font-size: 12px;
    font-weight: 400;
    color: var(--widget-muted);
  }
  .widget-field input,
  .widget-field textarea,
  .widget-field select {
    width: 100%;
    min-width: 0;
    min-height: 40px;
    padding: 10px 12px;
    font: inherit;
    line-height: 1.5;
    border: 1px solid var(--widget-border);
    border-radius: 8px;
    color: inherit;
    background: var(--widget-field);
    box-sizing: border-box;
    transition: border-color 120ms;
  }
  .widget-field textarea {
    resize: vertical;
  }
  .widget-field input::placeholder,
  .widget-field textarea::placeholder {
    color: var(--widget-muted);
  }
  .widget-field :is(input, textarea, select):hover:not(:disabled) {
    border-color: var(--gray-400);
  }
  .widget-field :is(input, textarea, select):disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .widget-button:focus-visible,
  .widget-listitem-action:focus-visible,
  .widget-field :is(input, textarea, select):focus-visible,
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
  @media (prefers-reduced-motion: reduce) {
    .widget-button,
    .widget-field :is(input, textarea, select) {
      transition: none;
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
