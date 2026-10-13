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
  >
    <button
      v-if="node.type === 'ListViewItem' && node.onClickAction"
      type="button"
      class="widget-listitem-action"
      :disabled="disabled"
      @click="selectItem"
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
</template>

<script setup>
import { computed } from 'vue'
import { BookOpen, FileText, Lightbulb, Info, Check, Plus, Search, ChevronRight } from '@lucide/vue'
import WidgetChart from '@/shared/ui/WidgetChart.vue'
import WidgetImage from '@/shared/ui/WidgetImage.vue'
const props = defineProps({
  node: { type: Object, required: true },
  disabled: Boolean,
  thumbnail: Boolean,
  previewable: { type: Boolean, default: true }
})
const emit = defineEmits(['action', 'preview'])
const containers = {
  Card: 'section',
  Row: 'div',
  Col: 'div',
  ListView: 'ul',
  ImageGroup: 'div',
  ListViewItem: 'li'
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

/** 将推荐项的续聊内容交给消息草稿。 */
function selectItem() {
  if (!props.disabled) emit('action', props.node.onClickAction.text)
}
</script>
