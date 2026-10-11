<template>
  <a-modal
    :open="open && entry.editing && !!entry.record"
    title="补充反馈"
    :width="520"
    :wrap-props="{ 'aria-modal': 'true' }"
    :mask-closable="false"
    :keyboard="!entry.pending"
    :closable="!entry.pending"
    :confirm-loading="entry.pending"
    :ok-button-props="{ disabled: reason.length > 2000 }"
    :cancel-button-props="{ disabled: entry.pending }"
    ok-text="提交反馈"
    cancel-text="关闭"
    @ok="emit('save', reason)"
    @cancel="emit('close')"
    :after-close="() => emit('afterClose')"
  >
    <div class="feedback-dialog">
      <div class="rating-context">
        <span class="rating-icon" :class="{ negative: entry.record?.rating === 'dislike' }" aria-hidden="true">
          <ThumbsUp v-if="entry.record?.rating === 'like'" :size="18" />
          <ThumbsDown v-else :size="18" />
        </span>
        <div>
          <strong>{{ entry.record?.rating === 'like' ? '已点赞' : '已点踩' }}</strong>
        </div>
      </div>

      <fieldset ref="presetGroup" class="feedback-presets" :disabled="entry.pending">
        <legend>{{ entry.record?.rating === 'like' ? '哪些方面做得好？' : '哪些方面需要改进？' }}</legend>
        <div class="preset-options">
          <button v-for="option in options" :key="option" type="button" class="preset-option"
            :class="{ selected: selected.includes(option) }" :aria-pressed="selected.includes(option)"
            @click="toggleReason(option)">
            <Check v-if="selected.includes(option)" :size="14" aria-hidden="true" />
            <Plus v-else :size="14" aria-hidden="true" />
            {{ option }}
          </button>
        </div>
      </fieldset>
      <div class="feedback-field">
        <label :for="`feedback-${runId}`">补充说明 <span>选填</span></label>
        <a-textarea
          :id="`feedback-${runId}`"
          :value="entry.draft"
          @update:value="emit('updateDraft', $event)"
          :maxlength="2000"
          :auto-size="{ minRows: 4, maxRows: 8 }"
          :disabled="entry.pending"
          :placeholder="entry.record?.rating === 'like' ? '哪些步骤或结果对你有帮助？' : '哪里不符合预期？你希望如何改进？'"
        />
        <div class="field-hint">
          <span>{{ reason.length }}/2000</span>
        </div>
      </div>

      <p v-if="reason.length > 2000" class="reason-limit" role="alert">所选原因与文字合计超过 2000 字，请减少选项或缩短说明。</p>
      <div v-if="entry.error" ref="errorNotice" class="feedback-save-error" role="alert" tabindex="-1">
        <AlertCircle :size="16" aria-hidden="true" />
        <span>{{ entry.error }}。草稿已保留，请重试保存。</span>
      </div>
    </div>
  </a-modal>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { AlertCircle, Check, Plus, ThumbsDown, ThumbsUp } from '@lucide/vue'

const props = defineProps({
  open: { type: Boolean, required: true },
  entry: { type: Object, required: true },
  runId: { type: String, required: true }
})
const emit = defineEmits(['save', 'close', 'afterClose', 'updateDraft'])
const selected = ref([])
const presets = {
  like: ['解决了我的问题', '遵循了我的指示', '内容准确清晰', '代码或输出质量好', '快速高效', '有帮助的主动行为'],
  dislike: ['不正确或不完整', '没有遵循我的指示', '偏题或超出范围', '丢失上下文', '代码或执行有问题', '速度慢或有故障']
}
const options = computed(() => presets[props.entry.record?.rating] || [])
const reason = computed(() => [selected.value.join('；'), props.entry.draft.trim()].filter(Boolean).join('\n\n'))
/** 切换可多选的常见原因，文字说明独立保留。 */
function toggleReason(option) {
  selected.value = selected.value.includes(option)
    ? selected.value.filter(item => item !== option) : [...selected.value, option]
}
const presetGroup = ref(null)
const errorNotice = ref(null)

watch(() => props.open && props.entry.editing, async (open) => {
  if (!open) return
  selected.value = []
  await nextTick()
  presetGroup.value?.querySelector('button')?.focus()
})
watch(() => props.entry.error, async (error) => {
  if (!error || !props.open || !props.entry.editing) return
  await nextTick()
  errorNotice.value?.focus()
})
</script>

<style scoped lang="less">
.feedback-dialog { padding-top: 8px; }
.rating-context {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  strong { color: var(--gray-900); font-size: 14px; }
  p { margin: 4px 0 0; font-size: 13px; color: var(--gray-600); }
}
.rating-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 40px;
  height: 40px;
  border-radius: 8px;
  color: var(--main-700);
  background: var(--main-50);
  &.negative { color: var(--color-warning-900); background: var(--color-warning-50); }
}
.feedback-presets {
  border: 0;
  padding: 0;
  margin: 0 0 20px;
  legend { margin-bottom: 10px; color: var(--gray-900); font-size: 13px; font-weight: 500; }
}
.preset-options { display: flex; flex-wrap: wrap; gap: 8px; }
.preset-option {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border: 1px solid var(--gray-200);
  border-radius: 18px;
  background: transparent;
  color: var(--gray-700);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  &:hover { background: var(--gray-50); }
  &.selected { color: var(--main-700); background: var(--main-50); border-color: var(--main-500); }
  &:focus-visible { outline: 2px solid var(--main-color); outline-offset: 2px; }
}
.feedback-presets:disabled .preset-option { opacity: 0.5; cursor: wait; }
.reason-limit { color: var(--color-error-700); font-size: 12px; }
.feedback-field {
  display: grid;
  gap: 8px;
  label { color: var(--gray-900); font-size: 14px; font-weight: 500; }
  label span { margin-left: 4px; color: var(--gray-600); font-size: 12px; font-weight: 400; }
}
.field-hint { display: flex; justify-content: flex-end; font-size: 12px; color: var(--gray-600); }
.feedback-save-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 16px;
  padding: 12px;
  border-radius: 6px;
  background: var(--color-error-50);
  color: var(--color-error-700);
  font-size: 13px;
  svg { flex-shrink: 0; margin-top: 2px; }
  &:focus-visible { outline: 2px solid var(--color-error-700); outline-offset: 2px; }
}
</style>
