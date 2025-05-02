<template>
  <div class="login-view">
    <div class="login-container">
      <div class="login-logo">
        <img src="@/assets/logo.png" alt="Logo" v-if="false" />
        <h1>知识库管理系统</h1>
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
            <a-input v-model:value="adminForm.username" />
          </a-form-item>

          <a-form-item
            label="密码"
            name="password"
            :rules="[{ required: true, message: '请输入密码' }]"
          >
            <a-input-password v-model:value="adminForm.password" />
          </a-form-item>

          <a-form-item
            label="确认密码"
            name="confirmPassword"
            :rules="[
              { required: true, message: '请确认密码' },
              { validator: validateConfirmPassword }
            ]"
          >
            <a-input-password v-model:value="adminForm.confirmPassword" />
          </a-form-item>

          <a-form-item>
            <a-button type="primary" html-type="submit" :loading="loading" block>创建管理员账户</a-button>
          </a-form-item>
        </a-form>
      </div>

      <!-- 登录表单 -->
      <div v-else class="login-form">
        <h2>用户登录</h2>

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
            <a-input v-model:value="loginForm.username" />
          </a-form-item>

          <a-form-item
            label="密码"
            name="password"
            :rules="[{ required: true, message: '请输入密码' }]"
          >
            <a-input-password v-model:value="loginForm.password" />
          </a-form-item>

          <a-form-item>
            <a-button type="primary" html-type="submit" :loading="loading" block>登录</a-button>
          </a-form-item>
        </a-form>
      </div>

      <!-- 错误提示 -->
      <div v-if="errorMessage" class="error-message">
        {{ errorMessage }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useUserStore } from '@/stores/user';
import { message } from 'ant-design-vue';
import { chatApi } from '@/apis/auth_api';
import { authApi } from '@/apis/public_api';

const router = useRouter();
const userStore = useUserStore();

// 状态
const isFirstRun = ref(false);
const loading = ref(false);
const errorMessage = ref('');

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
        router.push('/chat');
        return;
      }
      
      // 普通用户跳转到默认智能体
      try {
        // 尝试获取默认智能体
        const data = await chatApi.getDefaultAgent();
        if (data.default_agent_id) {
          // 如果存在默认智能体，直接跳转
          router.push(`/agent/${data.default_agent_id}`);
          return;
        }
        
        // 没有默认智能体，获取第一个可用智能体
        const agentData = await chatApi.getAgents();
        if (agentData.agents && agentData.agents.length > 0) {
          router.push(`/agent/${agentData.agents[0].name}`);
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

// 组件挂载时
onMounted(async () => {
  // 如果已登录，跳转到首页
  if (userStore.isLoggedIn) {
    router.push('/');
    return;
  }

  // 检查是否是首次运行
  await checkFirstRunStatus();
});
</script>

<style lang="less" scoped>
.login-view {
  height: 100vh;
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #f5f5f5;
}

.login-container {
  width: 400px;
  padding: 40px;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.login-logo {
  text-align: center;
  margin-bottom: 30px;

  img {
    height: 60px;
    margin-bottom: 16px;
  }

  h1 {
    font-size: 24px;
    font-weight: 600;
    color: #333;
    margin: 0;
  }
}

.login-form {
  h2 {
    text-align: center;
    margin-bottom: 24px;
    font-size: 20px;
    font-weight: 500;
  }
}

.init-desc {
  margin-bottom: 24px;
  color: #666;
  text-align: center;
}

.error-message {
  margin-top: 16px;
  padding: 8px 12px;
  background-color: #fff2f0;
  border: 1px solid #ffccc7;
  border-radius: 4px;
  color: #ff4d4f;
  font-size: 14px;
}
</style>