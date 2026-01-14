<template>
  <div class="login-view" :class="{ 'has-alert': serverStatus === 'error' }">
    <!-- 服务状态提示 -->
    <div v-if="serverStatus === 'error'" class="server-status-alert">
      <div class="alert-content">
        <exclamation-circle-outlined class="alert-icon" />
        <div class="alert-text">
          <div class="alert-title">服务端连接失败</div>
          <div class="alert-message">{{ serverError }}</div>
        </div>
        <a-button type="link" size="small" @click="checkServerHealth" :loading="healthChecking">
          重试
        </a-button>
      </div>
    </div>

    <div class="login-top-action">
      <a-button type="text" size="small" class="back-home-btn" @click="goHome"> 返回首页 </a-button>
    </div>

    <div class="login-layout">
      <!-- 左侧图片区域 -->
      <div class="login-image-section">
        <img :src="loginBgImage" alt="登录背景" class="login-bg-image" />
      </div>

      <!-- 右侧登录表单区域 -->
      <div class="login-form-section">
        <div class="login-container">
          <header class="login-header">
            <p class="login-title">欢迎登录</p>
            <h1 class="login-brand">{{ brandName }}</h1>
            <p v-if="!isFirstRun && brandSubtitle" class="login-subtitle">{{ brandSubtitle }}</p>
          </header>

          <div class="login-content" :class="{ 'is-initializing': isFirstRun }">
            <!-- 初始化管理员表单 -->
            <div v-if="isFirstRun" class="login-form login-form--init">
              <h2>系统初始化，请创建超级管理员</h2>
              <a-form :model="adminForm" @finish="handleInitialize" layout="vertical">
                <a-form-item
                  label="用户ID"
                  name="user_id"
                  :rules="[
                    { required: true, message: '请输入用户ID' },
                    {
                      pattern: /^[a-zA-Z0-9_]+$/,
                      message: '用户ID只能包含字母、数字和下划线'
                    },
                    {
                      min: 3,
                      max: 20,
                      message: '用户ID长度必须在3-20个字符之间'
                    }
                  ]"
                >
                  <a-input
                    v-model:value="adminForm.user_id"
                    placeholder="请输入用户ID（3-20个字符）"
                    :maxlength="20"
                  />
                </a-form-item>

                <a-form-item
                  label="手机号（可选）"
                  name="phone_number"
                  :rules="[
                    {
                      validator: async (rule, value) => {
                        if (!value || value.trim() === '') {
                          return // 空值允许
                        }
                        const phoneRegex = /^1[3-9]\d{9}$/
                        if (!phoneRegex.test(value)) {
                          throw new Error('请输入正确的手机号格式')
                        }
                      }
                    }
                  ]"
                >
                  <a-input
                    v-model:value="adminForm.phone_number"
                    placeholder="可用于登录，可不填写"
                    :max-length="11"
                  />
                </a-form-item>

                <a-form-item
                  label="密码"
                  name="password"
                  :rules="[{ required: true, message: '请输入密码' }]"
                >
                  <a-input-password v-model:value="adminForm.password" prefix-icon="lock" />
                </a-form-item>

                <a-form-item
                  label="确认密码"
                  name="confirmPassword"
                  :rules="[
                    { required: true, message: '请确认密码' },
                    { validator: validateConfirmPassword }
                  ]"
                >
                  <a-input-password v-model:value="adminForm.confirmPassword" prefix-icon="lock" />
                </a-form-item>

                <a-form-item>
                  <a-button type="primary" html-type="submit" :loading="loading" block
                    >创建管理员账户</a-button
                  >
                </a-form-item>
              </a-form>
            </div>

            <!-- 登录表单 -->
            <div v-else class="login-form">
              <a-form :model="loginForm" @finish="handleLogin" layout="vertical">
                <a-form-item
                  label="登录账号"
                  name="loginId"
                  :rules="[{ required: true, message: '请输入用户ID或手机号' }]"
                >
                  <a-input v-model:value="loginForm.loginId" placeholder="用户ID或手机号">
                    <template #prefix>
                      <user-outlined />
                    </template>
                  </a-input>
                </a-form-item>

                <a-form-item
                  label="密码"
                  name="password"
                  :rules="[{ required: true, message: '请输入密码' }]"
                >
                  <a-input-password v-model:value="loginForm.password">
                    <template #prefix>
                      <lock-outlined />
                    </template>
                  </a-input-password>
                </a-form-item>

                <a-form-item>
                  <div class="login-options">
                    <a-checkbox v-model:checked="rememberMe" @click="showDevMessage"
                      >记住我</a-checkbox
                    >
                    <a class="forgot-password" @click="showDevMessage">忘记密码?</a>
                  </div>
                </a-form-item>

                <a-form-item>
                  <a-button
                    type="primary"
                    html-type="submit"
                    :loading="loading"
                    :disabled="isLocked"
                    block
                  >
                    <span v-if="isLocked">账户已锁定 {{ formatTime(lockRemainingTime) }}</span>
                    <span v-else>登录</span>
                  </a-button>
                </a-form-item>

                <!-- 第三方登录选项 -->
                <div class="third-party-login">
                  <div class="divider">
                    <span>其他登录方式</span>
                  </div>
                  <div class="login-icons">
                    <a-tooltip title="微信登录">
                      <a-button shape="circle" class="login-icon" @click="showDevMessage">
                        <template #icon><wechat-outlined /></template>
                      </a-button>
                    </a-tooltip>
                    <a-tooltip title="企业微信登录">
                      <a-button shape="circle" class="login-icon" @click="showDevMessage">
                        <template #icon><qrcode-outlined /></template>
                      </a-button>
                    </a-tooltip>
                    <a-tooltip title="飞书登录">
                      <a-button shape="circle" class="login-icon" @click="showDevMessage">
                        <template #icon><thunderbolt-outlined /></template>
                      </a-button>
                    </a-tooltip>
                  </div>
                </div>
              </a-form>
            </div>

            <!-- 错误提示 -->
            <div v-if="errorMessage" class="error-message">
              {{ errorMessage }}
            </div>
          </div>

          <!-- 页脚 -->
          <div class="login-footer">
            <a href="https://github.com/xerrors" target="_blank">联系我们</a>
            <a href="https://github.com/xerrors/Yuxi-Know" target="_blank">使用帮助</a>
            <a href="https://github.com/xerrors/Yuxi-Know/blob/main/LICENSE" target="_blank"
              >隐私政策</a
            >
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { useAgentStore } from '@/stores/agent'
import { message } from 'ant-design-vue'
import { healthApi } from '@/apis/system_api'
import {
  UserOutlined,
  LockOutlined,
  WechatOutlined,
  QrcodeOutlined,
  ThunderboltOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons-vue'
const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()
const agentStore = useAgentStore()

// 品牌展示数据
const loginBgImage = computed(() => {
  return infoStore.organization?.login_bg || '/login-bg.jpg'
})
const brandName = computed(() => {
  const rawName = infoStore.branding?.name ?? ''
  const trimmed = rawName.trim()
  return trimmed || 'Yuxi-Know'
})
const brandSubtitle = computed(() => {
  const rawSubtitle = infoStore.branding?.subtitle ?? ''
  const trimmed = rawSubtitle.trim()
  return trimmed || '大模型驱动的知识库管理工具'
})
const brandDescription = computed(() => {
  const rawDescription = infoStore.branding?.description ?? ''
  const trimmed = rawDescription.trim()
  return trimmed || '结合知识库与知识图谱，提供更准确、更全面的回答'
})

// 状态
const isFirstRun = ref(false)
const loading = ref(false)
const errorMessage = ref('')
const rememberMe = ref(false)
const serverStatus = ref('loading')
const serverError = ref('')
const healthChecking = ref(false)

// 登录锁定相关状态
const isLocked = ref(false)
const lockRemainingTime = ref(0)
const lockCountdown = ref(null)

// 登录表单
const loginForm = reactive({
  loginId: '', // 支持user_id或phone_number登录
  password: ''
})

// 管理员初始化表单
const adminForm = reactive({
  user_id: '', // 改为直接输入user_id
  password: '',
  confirmPassword: '',
  phone_number: '' // 手机号字段（可选）
})

// 开发中功能提示
const showDevMessage = () => {
  message.info('该功能正在开发中，敬请期待！')
}

const goHome = () => {
  router.push('/')
}

// 清理倒计时器
const clearLockCountdown = () => {
  if (lockCountdown.value) {
    clearInterval(lockCountdown.value)
    lockCountdown.value = null
  }
}

// 启动锁定倒计时
const startLockCountdown = (remainingSeconds) => {
  clearLockCountdown()
  isLocked.value = true
  lockRemainingTime.value = remainingSeconds

  lockCountdown.value = setInterval(() => {
    lockRemainingTime.value--
    if (lockRemainingTime.value <= 0) {
      clearLockCountdown()
      isLocked.value = false
      errorMessage.value = ''
    }
  }, 1000)
}

// 格式化时间显示
const formatTime = (seconds) => {
  if (seconds < 60) {
    return `${seconds}秒`
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}分${remainingSeconds}秒`
  } else if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}小时${minutes}分钟`
  } else {
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    return `${days}天${hours}小时`
  }
}

// 密码确认验证
const validateConfirmPassword = async (rule, value) => {
  if (value === '') {
    throw new Error('请确认密码')
  }
  if (value !== adminForm.password) {
    throw new Error('两次输入的密码不一致')
  }
}

// 处理登录
const handleLogin = async () => {
  // 如果当前被锁定，不允许登录
  if (isLocked.value) {
    message.warning(`账户被锁定，请等待 ${formatTime(lockRemainingTime.value)}`)
    return
  }

  try {
    loading.value = true
    errorMessage.value = ''
    clearLockCountdown()

    await userStore.login({
      loginId: loginForm.loginId,
      password: loginForm.password
    })

    message.success('登录成功')

    // 获取重定向路径
    const redirectPath = sessionStorage.getItem('redirect') || '/'
    sessionStorage.removeItem('redirect') // 清除重定向信息

    // 根据用户角色决定重定向目标
    if (redirectPath === '/') {
      // 如果是管理员，直接跳转到/chat页面
      if (userStore.isAdmin) {
        router.push('/agent')
        return
      }

      // 普通用户跳转到默认智能体
      try {
        // 初始化agentStore并获取智能体信息
        await agentStore.initialize()

        // 尝试获取默认智能体
        if (agentStore.defaultAgentId) {
          // 如果存在默认智能体，直接跳转
          router.push(`/agent/${agentStore.defaultAgentId}`)
          return
        }

        // 没有默认智能体，获取第一个可用智能体
        const agentIds = Object.keys(agentStore.agents)
        if (agentIds.length > 0) {
          router.push(`/agent/${agentIds[0]}`)
          return
        }

        // 没有可用智能体，回退到首页
        router.push('/')
      } catch (error) {
        console.error('获取智能体信息失败:', error)
        router.push('/')
      }
    } else {
      // 跳转到其他预设的路径
      router.push(redirectPath)
    }
  } catch (error) {
    console.error('登录失败:', error)

    // 检查是否是锁定错误（HTTP 423）
    if (error.status === 423) {
      // 尝试从响应头中获取剩余时间
      let remainingTime = 0
      if (error.headers && error.headers.get) {
        const lockRemainingHeader = error.headers.get('X-Lock-Remaining')
        if (lockRemainingHeader) {
          remainingTime = parseInt(lockRemainingHeader)
        }
      }

      // 如果没有从头中获取到，尝试从错误消息中解析
      if (remainingTime === 0) {
        const lockTimeMatch = error.message.match(/(\d+)\s*秒/)
        if (lockTimeMatch) {
          remainingTime = parseInt(lockTimeMatch[1])
        }
      }

      if (remainingTime > 0) {
        startLockCountdown(remainingTime)
        errorMessage.value = `由于多次登录失败，账户已被锁定 ${formatTime(remainingTime)}`
      } else {
        errorMessage.value = error.message || '账户被锁定，请稍后再试'
      }
    } else {
      errorMessage.value = error.message || '登录失败，请检查用户名和密码'
    }
  } finally {
    loading.value = false
  }
}

// 处理初始化管理员
const handleInitialize = async () => {
  try {
    loading.value = true
    errorMessage.value = ''

    if (adminForm.password !== adminForm.confirmPassword) {
      errorMessage.value = '两次输入的密码不一致'
      return
    }

    await userStore.initialize({
      user_id: adminForm.user_id,
      password: adminForm.password,
      phone_number: adminForm.phone_number || null // 空字符串转为null
    })

    message.success('管理员账户创建成功')
    router.push('/')
  } catch (error) {
    console.error('初始化失败:', error)
    errorMessage.value = error.message || '初始化失败，请重试'
  } finally {
    loading.value = false
  }
}

// 检查是否是首次运行
const checkFirstRunStatus = async () => {
  try {
    loading.value = true
    const isFirst = await userStore.checkFirstRun()
    isFirstRun.value = isFirst
  } catch (error) {
    console.error('检查首次运行状态失败:', error)
    errorMessage.value = '系统出错，请稍后重试'
  } finally {
    loading.value = false
  }
}

// 检查服务器健康状态
const checkServerHealth = async () => {
  try {
    healthChecking.value = true
    const response = await healthApi.checkHealth()
    if (response.status === 'ok') {
      serverStatus.value = 'ok'
    } else {
      serverStatus.value = 'error'
      serverError.value = response.message || '服务端状态异常'
    }
  } catch (error) {
    console.error('检查服务器健康状态失败:', error)
    serverStatus.value = 'error'
    serverError.value = error.message || '无法连接到服务端，请检查网络连接'
  } finally {
    healthChecking.value = false
  }
}

// 组件挂载时
onMounted(async () => {
  // 如果已登录，跳转到首页
  if (userStore.isLoggedIn) {
    router.push('/')
    return
  }

  // 首先检查服务器健康状态
  await checkServerHealth()

  // 检查是否是首次运行
  await checkFirstRunStatus()
})

// 组件卸载时清理定时器
onUnmounted(() => {
  clearLockCountdown()
})
</script>

<style lang="less" scoped>
.login-view {
  height: 100vh;
  width: 100%;
  position: relative;
  padding-top: 0;

  &.has-alert {
    padding-top: 60px;
  }
}

.login-top-action {
  position: absolute;
  top: 24px;
  right: 24px;
  z-index: 10;
}

.back-home-btn {
  color: var(--gray-600);
  font-size: 14px;
  padding: 0 8px;

  &:hover,
  &:focus {
    color: var(--main-color);
    background-color: transparent;
  }
}

.login-layout {
  display: flex;
  min-height: 100%;
  width: 100%;
  background: var(--gray-10);
}

.login-image-section {
  flex: 0 0 52%;
  position: relative;
  overflow: hidden;
  max-height: 100vh;

  .login-bg-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center;
  }
}

.login-form-section {
  flex: 1;
  min-width: 420px;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 64px 72px;
  background: var(--main-20);
}

.login-container {
  width: 100%;
  max-width: 460px;
  padding: 40px;
  background: var(--gray-0);
  border-radius: 24px;
  border: 1px solid var(--gray-150);
  box-shadow: 0 18px 36px var(--shadow-1);
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.login-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
}

.login-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--gray-600);
  text-transform: uppercase;
}

.login-brand {
  margin: 0;
  font-size: 30px;
  font-weight: 600;
  color: var(--main-color);
  line-height: 1.25;
}

.login-subtitle {
  margin: 0;
  font-size: 16px;
  color: var(--gray-600);
  line-height: 1.6;
}

.login-content {
  display: flex;
  flex-direction: column;
  gap: 24px;

  &.is-initializing {
    gap: 28px;
  }
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;

  :deep(.ant-form) {
    width: 100%;
  }

  :deep(.ant-form-item) {
    margin-bottom: 18px;
  }

  :deep(.ant-input-affix-wrapper) {
    padding: 10px 11px;
    height: auto;
  }

  :deep(.ant-btn) {
    font-size: 16px;
    padding: 0.5rem;
    height: auto;
  }
}

.login-form--init {
  padding: 24px;
  border-radius: 18px;
  background: var(--main-30);
  border: 1px solid var(--main-200);

  h2 {
    margin-bottom: 16px;
    font-size: 22px;
    font-weight: 600;
    color: var(--main-color);
    text-align: left;
  }
}

.login-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  gap: 12px;
  flex-wrap: wrap;

  .forgot-password {
    color: var(--main-color);
    font-size: 14px;

    &:hover {
      color: var(--main-bright);
    }
  }
}

.init-tips {
  background: var(--main-20);
  border: 1px solid var(--main-200);
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 20px;
  text-align: left;

  p {
    margin: 4px 0;
    font-size: 13px;
    color: var(--main-700);
    line-height: 1.45;

    &:first-child {
      margin-top: 0;
    }

    &:last-child {
      margin-bottom: 0;
    }
  }
}

.error-message {
  margin-top: 16px;
  padding: 10px 12px;
  background-color: var(--color-error-50);
  border: 1px solid color-mix(in srgb, var(--color-error-500) 25%, transparent);
  border-radius: 8px;
  color: var(--color-error-700);
  font-size: 14px;
}

.third-party-login {
  margin-top: 20px;

  .divider {
    position: relative;
    text-align: center;
    margin: 16px 0;

    &::before,
    &::after {
      content: '';
      position: absolute;
      top: 50%;
      width: calc(50% - 60px);
      height: 1px;
      background-color: var(--gray-200);
    }

    &::before {
      left: 0;
    }

    &::after {
      right: 0;
    }

    span {
      display: inline-block;
      padding: 0 12px;
      background-color: var(--gray-0);
      position: relative;
      color: var(--gray-600);
      font-size: 14px;
    }
  }

  .login-icons {
    display: flex;
    justify-content: center;
    margin-top: 16px;

    .login-icon {
      margin: 0 12px;
      width: 42px;
      height: 42px;
      color: var(--gray-600);
      border: 1px solid var(--gray-300);
      transition:
        color 0.2s ease,
        border-color 0.2s ease,
        background-color 0.2s ease;

      &:hover {
        color: var(--main-color);
        border-color: var(--main-color);
        background-color: var(--main-20);
      }
    }
  }
}

.login-footer {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--gray-150);
  display: flex;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;

  a {
    color: var(--gray-600);
    cursor: pointer;

    &:hover {
      color: var(--main-color);
    }
  }
}

.server-status-alert {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 12px 20px;
  background: linear-gradient(135deg, var(--color-error-500), var(--color-error-100));
  color: var(--gray-0);
  z-index: 1000;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--color-error-500) 30%, transparent);

  .alert-content {
    display: flex;
    align-items: center;
    max-width: 1200px;
    margin: 0 auto;

    .alert-icon {
      font-size: 20px;
      margin-right: 12px;
      color: var(--gray-0);
    }

    .alert-text {
      flex: 1;

      .alert-title {
        font-weight: 600;
        font-size: 16px;
        margin-bottom: 2px;
      }

      .alert-message {
        font-size: 14px;
        opacity: 0.9;
      }
    }

    :deep(.ant-btn-link) {
      color: var(--gray-0);
      border-color: var(--gray-0);

      &:hover {
        color: var(--gray-0);
        background-color: color-mix(in srgb, var(--gray-0) 10%, transparent);
      }
    }
  }
}
</style>
