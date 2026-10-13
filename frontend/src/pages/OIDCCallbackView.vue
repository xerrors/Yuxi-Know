<template>
  <div class="oidc-callback-view">
    <div class="callback-container">
      <div v-if="loading" class="loading-section">
        <a-spin size="large" />
        <p class="loading-text">正在处理登录...</p>
      </div>

      <div v-else-if="error" class="error-section">
        <a-result status="error" :title="errorTitle" :sub-title="errorMessage">
          <template #extra>
            <a-button type="primary" @click="goToLogin"> 返回登录页 </a-button>
          </template>
        </a-result>
      </div>

      <div v-else class="success-section">
        <a-result status="success" title="登录成功" sub-title="正在跳转...">
          <template #icon>
            <a-spin />
          </template>
        </a-result>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/modules/identity/model/user'
import { authApi } from '@/apis/auth_api'
import { clearAutoStartAttempt } from '@/modules/identity/model/oidcAutoStart'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const loading = ref(true)
const error = ref(false)
const errorTitle = ref('登录失败')
const errorMessage = ref('请返回登录页重试')
let active = true
onUnmounted(() => {
  active = false
})
const goToLogin = () => router.replace('/login')

onMounted(async () => {
  const originalToken = userStore.token
  const code = route.query.code
  await router.replace({ path: route.path, query: {} })
  if (!active) return
  try {
    if (originalToken) {
      await router.replace('/agent')
      return
    }
    if (typeof code !== 'string' || !code) throw new Error('缺少有效的登录 code，请重新登录')
    const response = await authApi.exchangeOIDCCode(code)
    if (!active || userStore.token !== originalToken) return
    userStore.applySession(response)
    const redirect = sessionStorage.getItem('oidc_redirect') || '/agent'
    sessionStorage.removeItem('oidc_redirect')
    clearAutoStartAttempt()
    const target =
      redirect.startsWith('/') &&
      !redirect.startsWith('//') &&
      !redirect.includes('\\') &&
      ![...redirect].some((char) => char.charCodeAt(0) < 32)
        ? redirect
        : '/agent'
    await router.replace(target === '/' ? '/agent' : target)
  } catch (err) {
    if (active) {
      error.value = true
      errorMessage.value = err.message || '登录失败，请重试'
    }
  } finally {
    loading.value = false
  }
})
</script>

<style lang="less" scoped>
.oidc-callback-view {
  min-height: 100vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--gray-10);
  background-image: radial-gradient(var(--gray-200) 1px, transparent 1px);
  background-size: 24px 24px;
}

.callback-container {
  width: 100%;
  max-width: 500px;
  padding: 40px;
  background: var(--gray-0);
  border-radius: 16px;
  box-shadow: 0 4px 20px var(--shadow-1);
}

.loading-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;

  .loading-text {
    font-size: 16px;
    color: var(--gray-600);
    margin: 0;
  }
}

.error-section,
.success-section {
  :deep(.ant-result) {
    padding: 0;

    .ant-result-title {
      font-size: 20px;
      color: var(--gray-800);
    }

    .ant-result-subtitle {
      font-size: 14px;
      color: var(--gray-500);
    }
  }
}

@media (max-width: 576px) {
  .callback-container {
    margin: 20px;
    padding: 30px 20px;
  }
}
</style>
