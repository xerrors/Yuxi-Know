<template>
  <div class="home-container">
    <div class="background-elements">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
      <div class="circle circle-3"></div>
      <div class="circle circle-4"></div>
    </div>
    <div class="hero-section">
      <div class="glass-header">
        <div class="logo">
          <img :src="infoStore.organization.logo" :alt="infoStore.organization.name" class="logo-img" />
          <span style="font-size: 1.3rem; font-weight: bold;">{{ infoStore.organization.name }}</span>
        </div>
        <div class="header-actions">
          <div class="github-link">
            <a href="https://github.com/xerrors/Yuxi-Know" target="_blank">
              <svg height="24" width="24" viewBox="0 0 16 16" version="1.1">
                <path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
              </svg>
              <span class="stars-count">{{ isLoadingStars ? '加载中...' : githubStars }} ⭐</span>
            </a>
          </div>
          <UserInfoComponent :show-button="true" />
        </div>
      </div>

      <div class="hero-content">
        <h1 class="title">{{ infoStore.branding.title }}</h1>
        <div class="description">
          <p class="subtitle">{{ infoStore.branding.subtitle }}</p>
          <p class="features">
            <span v-for="feature in infoStore.features" :key="feature">{{ feature }}</span>
          </p>
        </div>
        <button class="start-button" @click="goToChat">开始对话</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { chatApi } from '@/apis/auth_api'
import UserInfoComponent from '@/components/UserInfoComponent.vue'

const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()
const githubStars = ref(0)
const isLoadingStars = ref(false)

const goToChat = async () => {
  // 检查用户是否登录
  if (!userStore.isLoggedIn) {
    // 登录后应该跳转到默认智能体而不是/agent
    sessionStorage.setItem('redirect', '/');  // 设置为首页，登录后会通过路由守卫处理重定向
    router.push('/login');
    return;
  }

  // 根据用户角色进行跳转
  if (userStore.isAdmin) {
    // 管理员用户跳转到聊天页面
    router.push('/agent');
    return;
  }

  // 普通用户跳转到默认智能体
  try {
    // 获取默认智能体
    const data = await chatApi.getDefaultAgent();
    if (data.default_agent_id) {
      // 使用后端设置的默认智能体
      router.push(`/agent/${data.default_agent_id}`);
    } else {
      // 如果没有设置默认智能体，则获取智能体列表选择第一个
      const agentData = await chatApi.getAgents();
      if (agentData.agents && agentData.agents.length > 0) {
        router.push(`/agent/${agentData.agents[0].id}`);
      } else {
        // 没有可用智能体，回退到chat页面
        router.push("/chat");
}
    }
  } catch (error) {
    console.error('跳转到智能体页面失败:', error);
    router.push("/chat");
  }
};

// 获取GitHub stars数量
const fetchGithubStars = async () => {
  try {
    isLoadingStars.value = true
    const response = await fetch('https://api.github.com/repos/xerrors/Yuxi-Know')
    const data = await response.json()
    githubStars.value = data.stargazers_count
  } catch (error) {
    console.error('获取GitHub stars失败:', error)
  } finally {
    isLoadingStars.value = false
  }
}

onMounted(async () => {
  // 加载信息配置
  await infoStore.loadInfoConfig()
  // 获取GitHub stars
  fetchGithubStars()
})
</script>

<style lang="less" scoped>
.home-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  color: #333;
  background: linear-gradient(135deg, #f0f7ff 0%, #f8fcff 50%, #f5faff 100%);
  background-size: 400% 400%;
  animation: gradientBackground 20s ease infinite;
  position: relative;
  overflow: hidden;
}

.home-container::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: radial-gradient(circle at 15% 25%, rgba(161, 196, 253, 0.08) 0%, transparent 25%),
              radial-gradient(circle at 85% 75%, rgba(194, 233, 251, 0.08) 0%, transparent 25%),
              radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.05) 0%, transparent 30%);
  z-index: 0;
}

@keyframes gradientBackground {
  0% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0% 50%;
  }
}

.glass-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 1.2rem 2rem;
  background-color: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(15px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.2);
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  box-shadow: 0 2px 20px rgba(0, 0, 0, 0.03);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.background-elements {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  z-index: 0;
}

.circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  animation: float 18s infinite ease-in-out;
  box-shadow: 0 0 30px rgba(161, 196, 253, 0.1);
}

.circle-1 {
  width: 150px;
  height: 150px;
  top: 10%;
  left: 5%;
  animation-delay: 0s;
}

.circle-2 {
  width: 100px;
  height: 100px;
  top: 70%;
  left: 20%;
  animation-delay: -5s;
}

.circle-3 {
  width: 80px;
  height: 80px;
  top: 20%;
  right: 10%;
  animation-delay: -10s;
}

.circle-4 {
  width: 120px;
  height: 120px;
  bottom: 15%;
  right: 15%;
  animation-delay: -7s;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0);
  }
  25% {
    transform: translate(20px, 20px);
  }
  50% {
    transform: translate(40px, 0);
  }
  75% {
    transform: translate(20px, -20px);
  }
}

.logo {
  display: flex;
  align-items: center;
  font-size: 1.4rem;
  font-weight: bold;
  color: var(--main-color, #333);

  .logo-img {
    height: 2rem;
    margin-right: 0.6rem;
  }
}

.github-link a {
  display: flex;
  align-items: center;
  text-decoration: none;
  color: #333;
  padding: 0.6rem 1.2rem;
  border-radius: 2rem;
  background-color: rgba(255, 255, 255, 0.25);
  transition: all 0.3s ease;
  border: 1px solid rgba(255, 255, 255, 0.3);

  &:hover {
    background-color: rgba(255, 255, 255, 0.4);
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.06);
  }

  svg {
    margin-right: 8px;
  }

  .stars-count {
    font-weight: 600;
  }
}

.hero-section {
  height: 100vh;
  width: 100vw;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 0 2rem;
  position: relative;
  z-index: 1;
}

.hero-content {
  max-width: 800px;
}

.title {
  font-size: 4rem;
  font-weight: 700;
  margin-bottom: 1.5rem;
  background: linear-gradient(45deg, #333, #555);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
}

.description {
  margin-bottom: 2.5rem;
}

.subtitle {
  font-size: 1.5rem;
  font-weight: 500;
  margin-bottom: 1.5rem;
  color: #555;
}

.features {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  font-size: 1.1rem;

  span {
    padding: 0.5rem 1rem;
    background-color: rgba(255, 255, 255, 0.3);
    border-radius: 2rem;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.4);
    backdrop-filter: blur(10px);
  }
}

.start-button {
  padding: 1rem 3rem;
  font-size: 1.2rem;
  font-weight: 600;
  color: white;
  background: linear-gradient(135deg, var(--main-500), var(--main-color));
  border: none;
  border-radius: 3rem;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);

  &:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
    background: linear-gradient(135deg, var(--main-color), var(--main-700));
  }

  &:active {
    transform: translateY(-1px);
  }
}

.preview-section {
  padding: 5rem 2rem;
  display: flex;
  justify-content: center;
}

.preview-container {
  position: relative;
  max-width: 1000px;
  overflow: hidden;
  border-radius: 1rem;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;

  &:hover {
    transform: translateY(-5px);
    box-shadow: 0 25px 50px rgba(0, 0, 0, 0.15);

    .preview-overlay {
      opacity: 1;
    }
  }

  img {
    width: 100%;
    height: auto;
    display: block;
    transition: transform 0.5s ease;
  }

  .preview-overlay {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: linear-gradient(to top, rgba(0, 0, 0, 0.7), transparent);
    padding: 2rem;
    opacity: 0.8;
    transition: opacity 0.3s ease;

    .overlay-content {
      color: white;

      h3 {
        font-size: 1.5rem;
        margin-bottom: 0.5rem;
      }

      p {
        font-size: 1rem;
        opacity: 0.9;
      }
    }
  }
}

footer {
  margin-top: auto;
  text-align: center;
  padding: 2rem;
  color: #666;
  font-size: 0.9rem;
}

@media (max-width: 768px) {
  .glass-header {
    padding: 1rem;
  }

  .logo {
    font-size: 1.2rem;
  }

  .title {
    font-size: 2.5rem;
  }

  .subtitle {
    font-size: 1.2rem;
  }

  .features {
    flex-direction: column;
    gap: 0.8rem;
  }

  .start-button {
    padding: 0.8rem 2rem;
    font-size: 1rem;
  }

  .preview-section {
    padding: 3rem 1rem;
  }
}
</style>
