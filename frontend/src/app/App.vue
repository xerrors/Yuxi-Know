<script setup>
import { onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { setLucideProps } from '@lucide/vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import { useThemeStore } from '@/shared/model/theme'
import { renderEmpty } from '@/shared/ui/AntEmpty'

// 迁移后的行内图标沿用文字字号，显式 size 与组件样式仍可覆盖。
setLucideProps({ size: '1em' })
const themeStore = useThemeStore()
const router = useRouter()
const failedRoute = ref(null)
const loadingTooLong = ref(false)
let latestNavigation = null
const loadingTimer = setTimeout(() => { loadingTooLong.value = true }, 10000)
if (router.currentRoute.value.matched.length) clearTimeout(loadingTimer)

const removeBeforeEach = router.beforeEach((to) => {
  latestNavigation = to
  failedRoute.value = null
})
const removeErrorHandler = router.onError((error, to) => {
  if (latestNavigation && latestNavigation !== to) return
  console.error('页面路由加载失败:', to.fullPath, error)
  failedRoute.value = router.resolve(to).href
  clearTimeout(loadingTimer)
})
const removeAfterEach = router.afterEach((to, _from, failure) => {
  if (failure) return
  latestNavigation = to
  failedRoute.value = null
  loadingTooLong.value = false
  clearTimeout(loadingTimer)
})

/** 重新加载目标页面，使失败的模块请求可以重新发起。 */
const reloadPage = () => {
  if (failedRoute.value) window.location.assign(failedRoute.value)
  else window.location.reload()
}

onUnmounted(() => {
  clearTimeout(loadingTimer)
  removeBeforeEach()
  removeErrorHandler()
  removeAfterEach()
})
</script>
<template>
  <a-config-provider :theme="themeStore.currentTheme" :locale="zhCN" :render-empty="renderEmpty">
    <router-view v-slot="{ Component }">
      <component :is="Component" v-if="Component" />
      <main v-if="!Component && !failedRoute" class="route-loading">
        <div class="route-feedback route-feedback--loading" role="status" aria-live="polite">
          <a-spin />
          <p>正在打开页面…</p>
          <template v-if="loadingTooLong">
            <p class="route-description">加载时间较长，请检查网络连接后重试。</p>
            <a-button @click="reloadPage">重新加载</a-button>
          </template>
        </div>
      </main>
      <section v-if="failedRoute" class="route-error" :class="{ 'route-error--floating': Component }" role="alert">
        <div class="route-feedback">
          <h2>页面加载失败</h2>
          <p class="route-description">请检查网络连接，然后重新加载页面。</p>
          <a-button type="primary" @click="reloadPage">重新加载</a-button>
        </div>
      </section>
    </router-view>
  </a-config-provider>
</template>

<style scoped>
.route-loading,
.route-error {
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: var(--gray-0);
  color: var(--color-text);
}

.route-feedback {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  text-align: center;
  font-size: 14px;
}

.route-feedback--loading {
  animation: reveal-route-feedback 0s 150ms backwards;
}

.route-feedback p,
.route-feedback h2 {
  margin: 0;
}

.route-feedback h2 {
  font-size: 18px;
  font-weight: 600;
}

.route-description {
  color: var(--color-text-secondary);
}

.route-error--floating {
  position: fixed;
  z-index: 1000;
  inset: auto 24px 24px auto;
  min-height: auto;
  max-width: calc(100vw - 48px);
  border: 1px solid var(--gray-150);
  border-radius: 12px;
  box-shadow: var(--shadow-popover);
}

@keyframes reveal-route-feedback {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
