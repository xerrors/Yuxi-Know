<script setup>
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'
import { onMounted } from 'vue'
import { theme } from 'ant-design-vue'

const agentStore = useAgentStore();
const userStore = useUserStore();
const themeStore = useThemeStore();

onMounted(async () => {
  if (userStore.isLoggedIn) {
    await agentStore.initialize();
  }
})
</script>
<template>
  <a-config-provider 
    :theme="themeStore.currentTheme"
    :algorithm="themeStore.isDark ? theme.darkAlgorithm : theme.defaultAlgorithm"
  >
    <router-view />
  </a-config-provider>
</template>
