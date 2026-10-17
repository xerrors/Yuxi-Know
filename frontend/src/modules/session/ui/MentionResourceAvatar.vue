<template>
  <FallbackAvatar
    v-if="item.type === 'agent'"
    :src="item.icon"
    :name="item.label"
    :seed="item.value"
    kind="agent"
    :size="24"
    shape="rounded"
    decorative
  />
  <span v-else class="resource-avatar" :style="{ '--resource-color': color }" aria-hidden="true">
    <span v-if="item.type === 'mcp' && item.icon">{{ item.icon }}</span>
    <component v-else :is="icon" :size="15" />
  </span>
</template>

<script setup>
import { computed } from 'vue'
import FallbackAvatar from '@/shared/ui/FallbackAvatar.vue'
import { getExtensionIconColor } from '@/shared/lib/extensionIconColor'
import { getSkillIcon } from '@/shared/lib/skill_icon_utils'
import { getKbTypeIcon } from '@/modules/knowledge/model/kb_utils'
import { getMentionIconComponent } from '@/modules/session/model/mention_icon_utils'

const props = defineProps({ item: { type: Object, required: true } })
const color = computed(() => getExtensionIconColor(props.item.resourceId || props.item.value))
const icon = computed(() => {
  if (props.item.type === 'knowledge') return getKbTypeIcon(props.item.kbType || 'milvus')
  if (props.item.type === 'skill') return getSkillIcon(props.item.value)
  return getMentionIconComponent(props.item.type, props.item.value)
})
</script>

<style lang="less" scoped>
.resource-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 24px;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  color: var(--resource-color);
  background: color-mix(in srgb, var(--resource-color) 7%, var(--gray-0));
}
</style>
