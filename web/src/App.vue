<script setup>
import { themeConfig } from '@/assets/theme'
import { useAgentStore } from '@/stores/agent'
import { onMounted } from 'vue'

const agentStore = useAgentStore();

onMounted(async () => {
  await agentStore.initialize();
})
</script>
<template>
  <a-config-provider :theme="themeConfig">
    <router-view />
  </a-config-provider>
</template>
