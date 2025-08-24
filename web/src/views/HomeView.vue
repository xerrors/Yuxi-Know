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
        <nav class="nav-links">
          <router-link to="/agent" class="nav-link" v-if="userStore.isLoggedIn && userStore.isAdmin">
            <span>智能体</span>
          </router-link>
          <router-link to="/graph" class="nav-link" v-if="userStore.isLoggedIn && userStore.isAdmin">
            <span>知识图谱</span>
          </router-link>
          <router-link to="/database" class="nav-link" v-if="userStore.isLoggedIn && userStore.isAdmin">
            <span>知识库</span>
          </router-link>
          <router-link to="/setting" class="nav-link" v-if="userStore.isLoggedIn && userStore.isAdmin">
            <span>设置</span>
          </router-link>
        </nav>
        <div class="header-actions">
          <div class="github-link">
            <a href="https://github.com/xerrors/Yuxi-Know" target="_blank">
              <svg height="20" width="20" viewBox="0 0 16 16" version="1.1">
                <path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
              </svg>
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

    <!-- 底部版权信息 -->
    <footer class="footer">
      <div class="footer-content">
        <p class="copyright">{{ infoStore.footer?.copyright || '© 2025 All rights reserved' }}</p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { useAgentStore } from '@/stores/agent'
import UserInfoComponent from '@/components/UserInfoComponent.vue'

const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()
const agentStore = useAgentStore()

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
    const defaultAgent = agentStore.defaultAgent;
    router.push(`/agent/${defaultAgent.id}`);
  } catch (error) {
    console.error('跳转到智能体页面失败:', error);
    router.push("/");
  }
};

onMounted(async () => {
  // 加载信息配置
  await infoStore.loadInfoConfig()
})
</script>

<style lang="less" scoped>
.home-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  color: var(--main-800);
  background: linear-gradient(135deg, var(--main-30) 0%, var(--main-20) 25%, var(--main-10) 50%, var(--main-5) 75%, var(--main-1) 100%);
  background-size: 400% 400%;
  animation: gradientBackground 25s ease infinite;
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
  background: radial-gradient(circle at 15% 25%, rgba(161, 196, 253, 0.12) 0%, transparent 30%),
              radial-gradient(circle at 85% 75%, rgba(194, 233, 251, 0.12) 0%, transparent 30%),
              radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.08) 0%, transparent 35%),
              radial-gradient(circle at 25% 75%, rgba(147, 197, 253, 0.06) 0%, transparent 25%),
              radial-gradient(circle at 75% 25%, rgba(219, 234, 254, 0.06) 0%, transparent 25%);
  z-index: 0;
  animation: backgroundShift 30s ease-in-out infinite;
}

@keyframes backgroundShift {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.8;
  }
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
  padding: 0.5rem 2rem;
  background-color: rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.25);
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  box-shadow: 0 2px 25px rgba(0, 0, 0, 0.01);
  transition: all 0.3s ease;
}

.glass-header:hover {
  background-color: rgba(255, 255, 255, 1);
}

.glass-header:hover .nav-link {
  color: #333;
}

.glass-header:hover .github-link a {
  color: #333;
}

.glass-header:hover .logo {
  color: #333;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 1rem;
  text-decoration: none;
  color: #555;
  font-weight: 500;
  font-size: 0.95rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;

  &:hover {
    color: #333;

    svg {
      transform: scale(1.1);
    }
  }

  &.router-link-active {
      background: linear-gradient(135deg, var(--main-600), var(--main-500));
      color: white;
      border-radius: 1.5rem;

      &:hover {
        background: linear-gradient(135deg, var(--main-700), var(--main-600));
      }
    }

  svg {
    transition: transform 0.3s ease;
    flex-shrink: 0;
  }

  span {
    white-space: nowrap;
  }
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
  color: #555;
  padding: 0.6rem 1rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  font-size: 0.9rem;
  font-weight: 500;

  &:hover {
    color: #333;

    svg {
      transform: scale(1.1);
    }
  }

  svg {
    margin-right: 6px;
    transition: transform 0.3s ease;
  }

  .stars-count {
    font-weight: 600;
  }
}

.hero-section {
  flex: 1;
  width: 100vw;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 0 2rem;
  position: relative;
  z-index: 1;
  min-height: 0;
}

.hero-content {
  max-width: 800px;
}

.title {
  font-size: 4.5rem;
  font-weight: 800;
  margin-bottom: 1.5rem;
  background: linear-gradient(135deg, var(--main-800) 0%, var(--main-600) 50%, var(--main-500) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  letter-spacing: -0.02em;
  line-height: 1.1;
  animation: titleGlow 2s ease-in-out infinite alternate;
}

@keyframes titleGlow {
  0% {
    text-shadow: 0 0 20px rgba(57, 150, 174, 0.1), 0 0 30px rgba(57, 150, 174, 0.2), 0 0 40px rgba(57, 150, 174, 0.1);
  }
  100% {
    text-shadow: 0 0 30px rgba(57, 150, 174, 0.2), 0 0 40px rgba(57, 150, 174, 0.3), 0 0 50px rgba(57, 150, 174, 0.2);
  }
}

.description {
  margin-bottom: 2.5rem;
}

.subtitle {
  font-size: 1.6rem;
  font-weight: 500;
  margin-bottom: 2rem;
  color: #64748b;
  line-height: 1.4;
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;
}

.features {
  display: flex;
  justify-content: center;
  gap: 1rem;
  font-size: 1rem;
  margin-bottom: 1rem;

  span {
    padding: 0.7rem 1.2rem;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.4), rgba(255, 255, 255, 0.2));
    border-radius: 2rem;
    border: 1px solid rgba(255, 255, 255, 0.5);
    backdrop-filter: blur(15px);
    font-weight: 500;
    color: #475569;
    transition: all 0.3s ease;

    &:hover {
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.5), rgba(255, 255, 255, 0.3));
    }
  }
}

.start-button {
  padding: 1rem 3.5rem;
  font-size: 1.3rem;
  font-weight: 600;
  color: white;
  background: linear-gradient(135deg, var(--main-600), var(--main-500));
  border: none;
  border-radius: 3rem;
  cursor: pointer;
  transition: all 0.3s ease;
  margin-top: 1rem;

  &:hover {
    background: linear-gradient(135deg, var(--main-700), var(--main-600));
  }

  &:active {
    opacity: 0.9;
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

.footer {
  margin-top: auto;
  background: var(--main-10);
  backdrop-filter: blur(10px);
  border-top: 1px solid var(--main-30);
  position: relative;
  z-index: 10;
}

.footer-content {
  text-align: center;
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.copyright {
  color: var(--main-700);
  font-size: 0.9rem;
  font-weight: 500;
  margin: 0;
  opacity: 0.8;
  transition: opacity 0.3s ease;
}

.footer:hover .copyright {
  opacity: 1;
}

@media (max-width: 768px) {
  .glass-header {
    padding: 0.8rem 1rem;
    flex-wrap: wrap;
    gap: 1rem;
  }

  .nav-links {
    order: 3;
    width: 100%;
    justify-content: center;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .nav-link {
    padding: 0.5rem 0.8rem;
    font-size: 0.85rem;

    span {
      display: none;
    }
  }

  .logo {
    font-size: 1.1rem;
  }

  .title {
    font-size: 2.8rem;
    margin-bottom: 1rem;
  }

  .subtitle {
    font-size: 1.3rem;
    margin-bottom: 1.5rem;
    padding: 0 1rem;
  }

  .features {
    flex-direction: column;
    gap: 0.8rem;
    padding: 0 1rem;

    span {
      padding: 0.6rem 1rem;
    }
  }

  .start-button {
    padding: 1rem 2.5rem;
    font-size: 1.1rem;
  }

  .hero-content {
    padding: 0 1rem;
  }

  .github-link a {
    padding: 0.5rem 0.8rem;
    font-size: 0.85rem;

    .stars-count {
      display: none;
    }
  }
}
</style>
