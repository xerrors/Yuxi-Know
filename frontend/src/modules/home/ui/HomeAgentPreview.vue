<template>
  <div class="agent-preview" aria-label="智能体预览">
    <Transition name="agent-preview" mode="out-in">
      <span :key="current.name" class="agent-preview-item">
        <FallbackAvatar
          kind="agent"
          :name="current.name"
          :seed="current.seed"
          :size="28"
          decorative
        />
        <span>{{ current.name }}</span>
      </span>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import FallbackAvatar from '@/shared/ui/FallbackAvatar.vue'

const props = defineProps({ paused: Boolean })
const agents = [
  { name: '智能助手', seed: 'home-assistant' },
  { name: '深度研究', seed: 'home-research' },
  { name: '代码助手', seed: 'home-code' },
  { name: '写作助手', seed: 'home-writing' },
  { name: '数据分析', seed: 'home-data' },
  { name: '知识检索', seed: 'home-knowledge' },
  { name: '创意搭档', seed: 'home-creative' }
]
const index = ref(0)
const current = computed(() => agents[index.value])
let active = true
let timer = null
let motion

/** 仅在空闲、可见且允许动效时轮播示例智能体。 */
function syncRotation() {
  clearInterval(timer)
  timer = null
  if (!motion || !active || props.paused || motion.matches || document.hidden) return
  timer = setInterval(() => {
    index.value = (index.value + 1) % agents.length
  }, 5000)
}

watch(() => props.paused, syncRotation)
onMounted(() => {
  motion = window.matchMedia('(prefers-reduced-motion: reduce)')
  motion.addEventListener('change', syncRotation)
  document.addEventListener('visibilitychange', syncRotation)
  syncRotation()
})
onActivated(() => {
  active = true
  syncRotation()
})
onDeactivated(() => {
  active = false
  syncRotation()
})
onUnmounted(() => {
  clearInterval(timer)
  motion?.removeEventListener('change', syncRotation)
  document.removeEventListener('visibilitychange', syncRotation)
})
</script>

<style scoped>
.agent-preview {
  min-width: 122px;
  height: 32px;
  display: flex;
  align-items: center;
  color: var(--gray-600);
  font-size: 14px;
}
.agent-preview-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.agent-preview-enter-active,
.agent-preview-leave-active {
  transition:
    opacity 180ms ease,
    transform 180ms ease;
}
.agent-preview-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.agent-preview-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
@media (prefers-reduced-motion: reduce) {
  .agent-preview-enter-active,
  .agent-preview-leave-active {
    transition: none;
  }
}
</style>
