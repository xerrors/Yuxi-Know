<script setup>
import { setLucideProps } from '@lucide/vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import { useThemeStore } from '@/shared/model/theme'
import { renderEmpty } from '@/shared/ui/AntEmpty'

// 迁移后的行内图标沿用文字字号，显式 size 与组件样式仍可覆盖。
setLucideProps({ size: '1em' })
const themeStore = useThemeStore()
</script>
<template>
  <a-config-provider :theme="themeStore.currentTheme" :locale="zhCN" :render-empty="renderEmpty">
    <router-view v-slot="{ Component }">
      <component :is="Component" v-if="Component" />
      <main v-else class="route-loading" role="status" aria-label="正在加载页面">
        <a-skeleton active :paragraph="{ rows: 4 }" />
        <span>正在加载页面…</span>
      </main>
    </router-view>
  </a-config-provider>
</template>

<style scoped>
.route-loading {
  min-height: 100vh;
  padding: 48px 24px;
  background: var(--gray-0);
  color: var(--color-text-secondary);
}
</style>
