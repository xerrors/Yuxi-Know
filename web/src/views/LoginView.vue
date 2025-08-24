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

    <div class="login-layout">
      <!-- 左侧图片区域 -->
      <div class="login-image-section">
        <img :src="loginBgImage" alt="登录背景" class="login-bg-image" />
        <div class="image-overlay">
          <div class="brand-info">
             <h1 class="brand-title">{{ infoStore.branding?.name || 'Yuxi-Know' }}</h1>
             <p class="brand-subtitle">{{ infoStore.branding?.subtitle || '大模型驱动的知识库管理工具' }}</p>
             <p class="brand-description">{{ infoStore.branding?.description || '结合知识库与知识图谱，提供更准确、更全面的回答' }}</p>
           </div>
          <div class="brand-copyright">
            <p>{{ infoStore.footer?.copyright || 'Yuxi-Know' }}. {{ infoStore.branding?.copyright || '版权所有' }}</p>
          </div>
        </div>
      </div>

      <!-- 右侧登录表单区域 -->
      <div class="login-form-section">
        <div class="login-container">
      <div class="login-logo">
        <h1>欢迎登录 {{ infoStore.branding.name }}</h1>
      </div>

      <!-- 初始化管理员表单 -->
      <div v-if="isFirstRun" class="login-form">
        <h2>系统初始化</h2>
        <p class="init-desc">系统首次运行，请创建超级管理员账户：</p>

        <a-form
          :model="adminForm"
          @finish="handleInitialize"
          layout="vertical"
        >
          <a-form-item
            label="用户名"
            name="username"
            :rules="[{ required: true, message: '请输入用户名' }]"
          >
            <a-input v-model:value="adminForm.username" prefix-icon="user" />
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
            <a-button type="primary" html-type="submit" :loading="loading" block>创建管理员账户</a-button>
          </a-form-item>
        </a-form>
      </div>

      <!-- 登录表单 -->
      <div v-else class="login-form">
        <a-form
          :model="loginForm"
          @finish="handleLogin"
          layout="vertical"
        >
          <a-form-item
            label="用户名"
            name="username"
            :rules="[{ required: true, message: '请输入用户名' }]"
          >
            <a-input v-model:value="loginForm.username">
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
              <a-checkbox v-model:checked="rememberMe" @click="showDevMessage">记住我</a-checkbox>
              <a class="forgot-password" @click="showDevMessage">忘记密码?</a>
            </div>
          </a-form-item>

          <a-form-item>
            <a-button type="primary" html-type="submit" :loading="loading" block>登录</a-button>
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

          <!-- 页脚 -->
          <div class="login-footer">
            <a href="https://github.com/xerrors" target="_blank">联系我们</a>
            <a href="https://github.com/xerrors/Yuxi-Know" target="_blank">使用帮助</a>
            <a href="https://github.com/xerrors/Yuxi-Know/blob/main/LICENSE" target="_blank">隐私政策</a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useUserStore } from '@/stores/user';
import { useInfoStore } from '@/stores/info';
import { useAgentStore } from '@/stores/agent';
import { message } from 'ant-design-vue';
import { healthApi } from '@/apis/system_api';
import { UserOutlined, LockOutlined, WechatOutlined, QrcodeOutlined, ThunderboltOutlined, ExclamationCircleOutlined } from '@ant-design/icons-vue';
const router = useRouter();
const userStore = useUserStore();
const infoStore = useInfoStore();
const agentStore = useAgentStore();

// 从infoStore获取登录背景图片
const loginBgImage = computed(() => {
  return infoStore.organization?.login_bg || '/login-bg.jpg';
});

// 状态
const isFirstRun = ref(false);
const loading = ref(false);
const errorMessage = ref('');
const rememberMe = ref(false);
const serverStatus = ref('loading');
const serverError = ref('');
const healthChecking = ref(false);

// 登录表单
const loginForm = reactive({
  username: '',
  password: ''
});

// 管理员初始化表单
const adminForm = reactive({
  username: '',
  password: '',
  confirmPassword: ''
});

// 开发中功能提示
const showDevMessage = () => {
  message.info('该功能正在开发中，敬请期待！');
};

// 密码确认验证
const validateConfirmPassword = (rule, value) => {
  if (value === '') {
    return Promise.reject('请确认密码');
  }
  if (value !== adminForm.password) {
    return Promise.reject('两次输入的密码不一致');
  }
  return Promise.resolve();
};

// 处理登录
const handleLogin = async () => {
  try {
    loading.value = true;
    errorMessage.value = '';

    await userStore.login({
      username: loginForm.username,
      password: loginForm.password
    });

    message.success('登录成功');

    // 获取重定向路径
    const redirectPath = sessionStorage.getItem('redirect') || '/';
    sessionStorage.removeItem('redirect'); // 清除重定向信息

    // 根据用户角色决定重定向目标
    if (redirectPath === '/') {
      // 如果是管理员，直接跳转到/chat页面
      if (userStore.isAdmin) {
        router.push('/agent');
        return;
      }

      // 普通用户跳转到默认智能体
      try {
        // 初始化agentStore并获取智能体信息
        await agentStore.initialize();
        
        // 尝试获取默认智能体
        if (agentStore.defaultAgentId) {
          // 如果存在默认智能体，直接跳转
          router.push(`/agent/${agentStore.defaultAgentId}`);
          return;
        }

        // 没有默认智能体，获取第一个可用智能体
        const agentIds = Object.keys(agentStore.agents);
        if (agentIds.length > 0) {
          router.push(`/agent/${agentIds[0]}`);
          return;
        }

        // 没有可用智能体，回退到首页
        router.push('/');
      } catch (error) {
        console.error('获取智能体信息失败:', error);
        router.push('/');
      }
    } else {
      // 跳转到其他预设的路径
      router.push(redirectPath);
    }
  } catch (error) {
    console.error('登录失败:', error);
    errorMessage.value = error.message || '登录失败，请检查用户名和密码';
  } finally {
    loading.value = false;
  }
};

// 处理初始化管理员
const handleInitialize = async () => {
  try {
    loading.value = true;
    errorMessage.value = '';

    if (adminForm.password !== adminForm.confirmPassword) {
      errorMessage.value = '两次输入的密码不一致';
      return;
    }

    await userStore.initialize({
      username: adminForm.username,
      password: adminForm.password
    });

    message.success('管理员账户创建成功');
    router.push('/');
  } catch (error) {
    console.error('初始化失败:', error);
    errorMessage.value = error.message || '初始化失败，请重试';
  } finally {
    loading.value = false;
  }
};

// 检查是否是首次运行
const checkFirstRunStatus = async () => {
  try {
    loading.value = true;
    const isFirst = await userStore.checkFirstRun();
    isFirstRun.value = isFirst;
  } catch (error) {
    console.error('检查首次运行状态失败:', error);
    errorMessage.value = '系统出错，请稍后重试';
  } finally {
    loading.value = false;
  }
};

// 检查服务器健康状态
const checkServerHealth = async () => {
  try {
    healthChecking.value = true;
    const response = await healthApi.checkHealth();
    if (response.status === 'ok') {
      serverStatus.value = 'ok';
    } else {
      serverStatus.value = 'error';
      serverError.value = response.message || '服务端状态异常';
    }
  } catch (error) {
    console.error('检查服务器健康状态失败:', error);
    serverStatus.value = 'error';
    serverError.value = error.message || '无法连接到服务端，请检查网络连接';
  } finally {
    healthChecking.value = false;
  }
};

// 组件挂载时
onMounted(async () => {
  // 如果已登录，跳转到首页
  if (userStore.isLoggedIn) {
    router.push('/');
    return;
  }

  // 首先检查服务器健康状态
  await checkServerHealth();

  // 检查是否是首次运行
  await checkFirstRunStatus();
});
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

.login-layout {
  display: flex;
  height: 100%;
  width: 100%;
}

.login-image-section {
  flex: 0 0 55%;
  position: relative;
  overflow: hidden;

  .login-bg-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center;
  }

  .image-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 80px 60px 40px 60px;
}

  .brand-info {
     text-align: left;
     color: white;
     max-width: 600px;

     .brand-title {
       font-size: 64px;
       font-weight: 800;
       margin-bottom: 24px;
       text-shadow: 0 3px 6px rgba(0, 0, 0, 0.4);
       letter-spacing: -1px;
     }

     .brand-subtitle {
       font-size: 28px;
       font-weight: 500;
       margin-bottom: 32px;
       opacity: 0.95;
       text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
       line-height: 1.3;
     }

     .brand-description {
       font-size: 20px;
       line-height: 1.6;
       margin-bottom: 0;
       opacity: 0.85;
       text-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
     }
   }

  .brand-copyright {
    align-self: flex-start;

    p {
      margin: 0;
      font-size: 14px;
      color: rgba(255, 255, 255, 0.7);
      text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
      font-weight: 400;
    }
  }
}

.login-form-section {
  flex: 1;
  min-width: 400px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #ffffff;
  padding: 40px;
}

.login-container {
  width: 100%;
  max-width: 420px;
  padding: 0;
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  backdrop-filter: none;
  border: none;
}

.login-logo {
  text-align: center;
  margin-bottom: 30px;

  img {
    height: 70px;
    margin-bottom: 16px;
  }

  h1 {
    font-size: 28px;
    font-weight: 600;
    color: var(--main-color);
    margin: 0;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  }
}

.login-form {
  h2 {
    text-align: center;
    margin-bottom: 30px;
    font-size: 22px;
    font-weight: 500;
    color: #333;
  }

  :deep(.ant-form-item) {
    margin-bottom: 20px;
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

.login-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;

  .forgot-password {
    color: #1890ff;
    font-size: 14px;

    &:hover {
      color: #40a9ff;
    }
  }
}

.init-desc {
  margin-bottom: 24px;
  color: #666;
  text-align: center;
}

.error-message {
  margin-top: 16px;
  padding: 10px 12px;
  background-color: #fff2f0;
  border: 1px solid #ffccc7;
  border-radius: 4px;
  color: #ff4d4f;
  font-size: 14px;
}

.third-party-login {
  margin-top: 20px;

  .divider {
    position: relative;
    text-align: center;
    margin: 16px 0;

    &::before, &::after {
      content: '';
      position: absolute;
      top: 50%;
      width: calc(50% - 60px);
      height: 1px;
      background-color: #e8e8e8;
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
      background-color: #fff;
      position: relative;
      color: #999;
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
      color: #666;
      border: 1px solid var(--gray-300);
      transition: all 0.3s;

      &:hover {
        color: var(--main-color);
        border-color: var(--main-color);
      }
    }
  }
}

.login-footer {
  margin-top: 24px;
  text-align: center;
  font-size: 13px;

  a {
    color: #666;
    margin: 0 8px;
    cursor: pointer;

    &:hover {
      color: var(--main-color);
    }
  }
}

.server-status-alert {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  padding: 12px 20px;
  background: linear-gradient(135deg, #ff4d4f, #ff7875);
  color: white;
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(255, 77, 79, 0.3);

  .alert-content {
    display: flex;
    align-items: center;
    max-width: 1200px;
    margin: 0 auto;

    .alert-icon {
      font-size: 20px;
      margin-right: 12px;
      color: white;
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
      color: white;
      border-color: white;

      &:hover {
        color: white;
        background-color: rgba(255, 255, 255, 0.1);
      }
    }
  }
}
</style>