<template>
  <a-tooltip :title="themeStore.isDark ? '切换到浅色模式' : '切换到深色模式'">
    <a-button type="text" @click="themeStore.toggleTheme" class="theme-toggle-btn">
      <template #icon>
        <component :is="themeStore.isDark ? SunIcon : MoonIcon" :size="18" />
      </template>
    </a-button>
  </a-tooltip>
</template>

<script setup>
import { useThemeStore } from '@/stores/theme'
import { Sun as SunIcon, Moon as MoonIcon } from 'lucide-vue-next'

const themeStore = useThemeStore()
</script>

<style scoped>
.theme-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
}

.theme-toggle-btn:hover {
  transform: rotate(20deg);
}
</style>
