<script setup>
import { themeConfig } from '@/assets/theme'
</script>
<template>
  <a-config-provider :theme="themeConfig">
    <router-view />
  </a-config-provider>
</template>
