<template>
  <component
    v-if="containers[node.type]"
    :is="containers[node.type]"
    :class="[
      'widget-node',
      `widget-${node.type.toLowerCase()}`,
      `widget-size-${node.size || 'md'}`
    ]"
    :style="nodeStyle"
    :role="node.type === 'ImageGroup' ? 'group' : undefined"
    :aria-label="node.type === 'ImageGroup' ? '图片组' : undefined"
    @submit.prevent="submitForm"
  >
    <button
      v-if="node.type === 'ListViewItem' && node.onClickAction"
      type="button"
      class="widget-listitem-action"
      :disabled="disabled"
      @click="clickButton"
    >
      <WidgetNode
        v-for="(child, index) in node.children"
        :key="index"
        :node="child"
        :disabled="disabled"
        :previewable="false"
      />
    </button>
    <template v-else>
      <WidgetNode
        v-for="(child, index) in node.children"
        :key="index"
        :node="child"
        :disabled="disabled"
        :thumbnail="node.type === 'ImageGroup' || thumbnail"
        :previewable="previewable"
        @preview="previewImage($event, index)"
        @action="emit('action', $event)"
      />
    </template>
  </component>
  <WidgetChart v-else-if="node.type === 'Chart'" :node="node" :disabled="disabled" />
  <WidgetImage
    v-else-if="node.type === 'Image'"
    :node="node"
    :thumbnail="thumbnail"
    :previewable="previewable"
    @preview="emit('preview', { images: [node], index: 0 })"
  />
  <component
    v-else-if="textTags[node.type]"
    :is="textTags[node.type]"
    :class="[`widget-${node.type.toLowerCase()}`, `widget-color-${node.color || 'default'}`]"
    :style="nodeStyle"
    >{{ node.value }}</component
  >
  <component
    v-else-if="node.type === 'Icon'"
    :is="icons[node.name]"
    :class="['widget-icon', `widget-color-${node.color || 'secondary'}`]"
    :size="iconSizes[node.size || 'md']"
    aria-hidden="true"
  />
  <span
    v-else-if="node.type === 'Badge'"
    :class="[
      'widget-badge',
      `widget-tone-${node.color || 'secondary'}`,
      `widget-variant-${node.variant || 'soft'}`,
      `widget-size-${node.size || 'md'}`,
      { 'widget-pill': node.pill }
    ]"
    >{{ node.label }}</span
  >
  <hr v-else-if="node.type === 'Divider'" class="widget-divider" />
  <div v-else-if="node.type === 'Spacer'" class="widget-spacer" aria-hidden="true"></div>
  <button
    v-else-if="node.type === 'Button'"
    :type="node.submit ? 'submit' : 'button'"
    :class="[
      'widget-button',
      `widget-tone-${buttonColor}`,
      `widget-variant-${node.variant || (buttonColor === 'primary' ? 'solid' : 'outline')}`,
      `widget-size-${node.size || 'md'}`,
      { 'widget-pill': node.pill, 'widget-block': node.block }
    ]"
    :disabled="disabled"
    @click="clickButton"
  >
    <component v-if="node.iconStart" :is="icons[node.iconStart]" :size="16" aria-hidden="true" />
    {{ node.label }}
    <component v-if="node.iconEnd" :is="icons[node.iconEnd]" :size="16" aria-hidden="true" />
  </button>
  <label v-else-if="['Input', 'Textarea', 'Select'].includes(node.type)" class="widget-field">
    <span>{{ node.label }}<span v-if="node.required" class="widget-required">（必填）</span></span>
    <input
      v-if="node.type === 'Input'"
      :name="node.name"
      v-model="fieldValue"
      :placeholder="node.placeholder"
      :required="node.required"
      :disabled="disabled"
      maxlength="4000"
    />
    <textarea
      v-else-if="node.type === 'Textarea'"
      :name="node.name"
      v-model="fieldValue"
      :placeholder="node.placeholder"
      :required="node.required"
      :disabled="disabled"
      maxlength="4000"
      rows="3"
    ></textarea>
    <select
      v-else
      :name="node.name"
      v-model="fieldValue"
      :required="node.required"
      :disabled="disabled"
    >
      <option value="" disabled>{{ node.placeholder || '请选择' }}</option>
      <option v-for="option in node.options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
  </label>
</template>

<script setup>
import { computed, ref } from 'vue'
import { BookOpen, FileText, Lightbulb, Info, Check, Plus, Search, ChevronRight } from '@lucide/vue'
import { composeWidgetMessage } from '@/shared/lib/chatWidgets'
import WidgetChart from '@/shared/ui/WidgetChart.vue'
import WidgetImage from '@/shared/ui/WidgetImage.vue'
const props = defineProps({
  node: { type: Object, required: true },
  disabled: Boolean,
  thumbnail: Boolean,
  previewable: { type: Boolean, default: true }
})
const emit = defineEmits(['action', 'preview'])
const fieldValue = ref(props.node.defaultValue || '')
const containers = {
  Card: 'section',
  Row: 'div',
  Col: 'div',
  ListView: 'ul',
  ImageGroup: 'div',
  ListViewItem: 'li',
  Form: 'form'
}
const textTags = { Title: 'h3', Text: 'p', Caption: 'p' }
const icons = {
  'book-open': BookOpen,
  document: FileText,
  lightbulb: Lightbulb,
  info: Info,
  check: Check,
  plus: Plus,
  search: Search,
  'chevron-right': ChevronRight
}
const iconSizes = { xs: 14, sm: 16, md: 20, lg: 24, xl: 32 }
const buttonColor = computed(
  () => props.node.color || (props.node.style === 'primary' ? 'primary' : 'secondary')
)
const nodeStyle = computed(() => {
  const node = props.node
  const style = {}
  if (node.gap !== undefined) style.gap = `${node.gap * 4}px`
  if (node.padding !== undefined) style.padding = `${node.padding * 4}px`
  if (node.align)
    style.alignItems = { start: 'flex-start', end: 'flex-end' }[node.align] || node.align
  if (node.justify)
    style.justifyContent =
      {
        start: 'flex-start',
        end: 'flex-end',
        between: 'space-between',
        around: 'space-around',
        evenly: 'space-evenly'
      }[node.justify] || node.justify
  if (node.flex !== undefined) style.flex = node.flex === 'auto' ? '1 1 auto' : `${node.flex} 1 0%`
  if (textTags[node.type]) {
    const sizes = {
      Title: { xs: 16, sm: 18, md: 20, lg: 24, xl: 28, '2xl': 32 },
      Text: { xs: 12, sm: 13, md: 14, lg: 16, xl: 18 },
      Caption: { sm: 11, md: 12, lg: 13 }
    }[node.type]
    if (node.size) style.fontSize = `${sizes[node.size]}px`
    if (node.weight)
      style.fontWeight = { normal: 400, medium: 500, semibold: 600, bold: 700 }[node.weight]
    if (node.textAlign) style.textAlign = node.textAlign
  }
  return style
})

/** 图片组保留完整顺序，其他容器透传图片自身的预览。 */
function previewImage(preview, index) {
  emit('preview', props.node.type === 'ImageGroup' ? { images: props.node.children, index } : preview)
}

/** 表单值仅写入可审阅草稿，提交前使用浏览器原生校验。 */
function submitForm(event) {
  if (props.disabled || props.node.type !== 'Form') return
  if (!event.target.reportValidity()) return
  emit('action', composeWidgetMessage(props.node.onSubmitAction, collectFields(event.target)))
}

/** 收集原生控件当前可见值，不把选择器占位文字当成用户选择。 */
function collectFields(form) {
  if (!form) return []
  return [...form.querySelectorAll('input, textarea, select')].map((field) => {
    let value = field.value
    if (field.tagName === 'SELECT' && value) value = field.selectedOptions[0]?.textContent || ''
    return {
      label: field.closest('label').querySelector('span').textContent.replace('（必填）', ''),
      value
    }
  })
}

/** 表单内普通动作也携带当前字段，所有动作仅产生草稿事件。 */
function clickButton(event) {
  if (!props.disabled && !props.node.submit)
    emit(
      'action',
      composeWidgetMessage(
        props.node.onClickAction,
        collectFields(event.currentTarget.closest('form'))
      )
    )
}
</script>
