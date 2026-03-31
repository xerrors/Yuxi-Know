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
            <a-button type="primary" @click="goToLogin">
              返回登录页
            </a-button>
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
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useAgentStore } from '@/stores/agent'
import { message } from 'ant-design-vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const agentStore = useAgentStore()

// 状态
const loading = ref(true)
const error = ref(false)
const errorTitle = ref('登录失败')
const errorMessage = ref('处理登录请求时发生错误')

// 返回登录页
const goToLogin = () => {
  router.push('/login')
}

// 处理 OIDC 回调 - 从 URL 参数中获取 token 数据
const handleCallback = () => {
  try {
    // 从 URL 参数中获取 token 数据（由后端直接重定向传递）
    const token = route.query.token
    const userId = route.query.user_id
    const username = route.query.username
    const userIdLogin = route.query.user_id_login
    const phoneNumber = route.query.phone_number
    const avatar = route.query.avatar
    const role = route.query.role
    const departmentId = route.query.department_id
    const departmentName = route.query.department_name

    // 检查必要的参数
    if (!token || !userId || !username) {
      loading.value = false
      error.value = true
      errorTitle.value = '参数错误'
      errorMessage.value = '缺少必要的登录信息，请重新登录'
      return
    }

    // 更新用户状态
    userStore.token = token
    userStore.userId = parseInt(userId)
    userStore.username = username
    userStore.userIdLogin = userIdLogin || ''
    userStore.phoneNumber = phoneNumber || ''
    userStore.avatar = avatar || ''
    userStore.userRole = role || 'user'
    userStore.departmentId = departmentId ? parseInt(departmentId) : null
    userStore.departmentName = departmentName || ''

    // 保存 token 到 localStorage
    localStorage.setItem('user_token', token)

    // 显示成功消息
    message.success('登录成功')

    // 获取重定向路径
    const redirectPath = sessionStorage.getItem('oidc_redirect') || '/'
    sessionStorage.removeItem('oidc_redirect')

    loading.value = false

    // 延迟跳转，让用户看到成功提示
    setTimeout(async () => {
      // 跳转
      if (redirectPath === '/') {
        try {
          await agentStore.initialize()
          router.push('/agent')
        } catch (err) {
          console.error('获取智能体信息失败:', err)
          router.push('/agent')
        }
      } else {
        router.push(redirectPath)
      }
    }, 500)

  } catch (err) {
    console.error('OIDC 回调处理失败:', err)
    loading.value = false
    error.value = true
    errorTitle.value = '登录失败'
    errorMessage.value = err.message || '处理登录请求时发生错误，请重试'
  }
}

// 组件挂载时处理回调
onMounted(() => {
  // 如果已登录，跳转到首页
  if (userStore.isLoggedIn) {
    router.push('/')
    return
  }

  handleCallback()
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
