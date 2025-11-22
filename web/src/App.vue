<script setup>
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'
import { onMounted } from 'vue'

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
  >
    <router-view />
  </a-config-provider>
</template>
