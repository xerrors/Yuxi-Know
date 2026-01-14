<template>
  <div class="home-container">
    <div class="hero-section">
      <div class="glass-header">
        <div class="logo">
          <img
            :src="infoStore.organization.logo"
            :alt="infoStore.organization.name"
            class="logo-img"
          />
          <span class="logo-text">{{ infoStore.organization.name }}</span>
        </div>
        <nav class="nav-links">
          <router-link
            to="/agent"
            class="nav-link"
            v-if="userStore.isLoggedIn && userStore.isAdmin"
          >
            <span>智能体</span>
          </router-link>
          <router-link
            to="/graph"
            class="nav-link"
            v-if="userStore.isLoggedIn && userStore.isAdmin"
          >
            <span>知识图谱</span>
          </router-link>
          <router-link
            to="/database"
            class="nav-link"
            v-if="userStore.isLoggedIn && userStore.isAdmin"
          >
            <span>知识库</span>
          </router-link>
        </nav>
        <div class="header-actions">
          <div class="github-link">
            <a href="https://github.com/xerrors/Yuxi-Know" target="_blank">
              <svg height="20" width="20" viewBox="0 0 16 16" version="1.1">
                <path
                  fill-rule="evenodd"
                  d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
                ></path>
              </svg>
            </a>
          </div>
          <UserInfoComponent :show-button="true" />
        </div>
      </div>

      <div class="hero-layout">
        <div class="hero-content">
          <h1 class="title">{{ infoStore.branding.title }}</h1>
          <p class="subtitle">{{ infoStore.branding.subtitle }}</p>
          <!-- <p class="description">{{ infoStore.branding.description }}</p> -->
          <div class="hero-actions">
            <button class="button-base primary" @click="goToChat">开始对话</button>
            <a
              class="button-base secondary"
              href="https://xerrors.github.io/Yuxi-Know/"
              target="_blank"
              >查看文档</a
            >
          </div>
        </div>
        <div class="insight-panel" v-if="featureCards.length">
          <div class="stat-card" v-for="card in featureCards" :key="card.label">
            <div class="stat-headline">
              <span class="stat-icon" v-if="card.icon">
                <component :is="card.icon" />
              </span>
              <p class="stat-value">{{ card.value }}</p>
            </div>
            <p class="stat-label">{{ card.label }}</p>
            <p class="stat-description">{{ card.description }}</p>
          </div>
        </div>
      </div>
    </div>

    <div class="section action-section" v-if="actionLinks.length">
      <div class="action-grid">
        <a
          v-for="action in actionLinks"
          :key="action.name"
          class="action-card"
          :href="action.url"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span class="action-icon" v-if="action.icon">
            <component :is="action.icon" />
          </span>
          <div class="action-meta">
            <p class="action-title">{{ action.name }}</p>
            <p class="action-url">{{ action.url }}</p>
          </div>
        </a>
      </div>
    </div>

    <ProjectOverview />

    <footer class="footer">
      <div class="footer-content">
        <p class="copyright">{{ infoStore.footer?.copyright || '© 2025 All rights reserved' }}</p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { useAgentStore } from '@/stores/agent'
import { useThemeStore } from '@/stores/theme'
import UserInfoComponent from '@/components/UserInfoComponent.vue'
import ProjectOverview from '@/components/ProjectOverview.vue'
import {
  BookText,
  Bug,
  Video,
  Route,
  Github,
  Star,
  CheckCircle2,
  GitCommit,
  ShieldCheck
} from 'lucide-vue-next'

const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()
const agentStore = useAgentStore()
const themeStore = useThemeStore()

const goToChat = async () => {
  // 检查用户是否登录
  if (!userStore.isLoggedIn) {
    // 登录后应该跳转到默认智能体而不是/agent
    sessionStorage.setItem('redirect', '/') // 设置为首页，登录后会通过路由守卫处理重定向
    router.push('/login')
    return
  }

  // 根据用户角色进行跳转
  if (userStore.isAdmin) {
    // 管理员用户跳转到聊天页面
    router.push('/agent')
    return
  }

  // 普通用户跳转到默认智能体
  try {
    // 获取默认智能体
    const defaultAgent = agentStore.defaultAgent
    if (defaultAgent?.id) {
      router.push(`/agent/${defaultAgent.id}`)
    } else {
      router.push('/agent')
    }
  } catch (error) {
    console.error('跳转到智能体页面失败:', error)
    router.push('/')
  }
}

onMounted(async () => {
  // 加载信息配置
  await infoStore.loadInfoConfig()
})

const iconKey = (value) => (typeof value === 'string' ? value.toLowerCase() : '')

// region icon_mapping
const featureIconMap = {
  stars: Star,
  issues: CheckCircle2,
  resolved: CheckCircle2,
  commits: GitCommit,
  license: ShieldCheck,
  default: Star
}

const actionIconMap = {
  doc: BookText,
  docs: BookText,
  document: BookText,
  issue: Bug,
  bug: Bug,
  roadmap: Route,
  plan: Route,
  demo: Video,
  video: Video,
  github: Github,
  default: Github
}
// endregion icon_mapping

const featureCards = computed(() => {
  const list = Array.isArray(infoStore.features) ? infoStore.features : []
  return list
    .map((item) => {
      if (typeof item === 'string') {
        return {
          label: item,
          value: '',
          description: '',
          icon: featureIconMap.default
        }
      }

      const key = iconKey(item.icon || item.type)
      return {
        label: item.label || item.name || '',
        value: item.value || '',
        description: item.description || '',
        icon: featureIconMap[key] || featureIconMap.default
      }
    })
    .filter((item) => item.label || item.value || item.description)
})

const actionLinks = computed(() => {
  const actions = infoStore.actions
  if (!Array.isArray(actions)) {
    return []
  }

  return actions
    .map((item) => {
      const key = iconKey(item?.icon || item?.type)
      return {
        name: item?.name || item?.label || '',
        url: item?.url || item?.link || '',
        icon: actionIconMap[key] || actionIconMap.default
      }
    })
    .filter((item) => item.name && item.url)
})
</script>

<style lang="less" scoped>
.home-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  color: var(--main-900);
  background: radial-gradient(circle at top right, var(--main-50), transparent 60%), var(--main-5);
  position: relative;
  overflow-x: hidden;
}
.glass-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 0.75rem 2.5rem;
  background-color: var(--color-trans-light);
  backdrop-filter: blur(20px);
  // border-bottom: 1px solid var(--main-30);
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  box-shadow: 0 6px 25px rgba(3, 80, 101, 0.02);
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
  color: var(--gray-800);
  font-weight: 500;
  font-size: 0.95rem;
  transition: color 0.2s ease;
  position: relative;
  overflow: hidden;

  &:hover {
    color: var(--gray-900);

    svg {
      transform: scale(1.1);
    }
  }

  &.router-link-active {
    background: linear-gradient(135deg, var(--main-600), var(--main-500));
    color: var(--gray-0);
    border-radius: 1.5rem;

    &:hover {
      background: linear-gradient(135deg, var(--main-700), var(--main-600));
    }
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

.logo {
  display: flex;
  align-items: center;
  font-size: 1.4rem;
  font-weight: bold;
  color: var(--main-800);

  .logo-img {
    height: 2rem;
    margin-right: 0.6rem;
  }
}

.logo-text {
  font-size: 1.3rem;
  font-weight: 600;
}

.github-link a {
  display: flex;
  align-items: center;
  text-decoration: none;
  color: var(--gray-600);
  padding: 0.6rem 1rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  font-size: 0.9rem;
  font-weight: 500;

  &:hover {
    color: var(--gray-700);

    svg {
      transform: scale(1.1);
    }
  }

  svg {
    margin-right: 6px;
    transition: transform 0.3s ease;
    fill: currentColor;
  }

  .stars-count {
    font-weight: 600;
  }

  // 暗色模式样式
  :global(.dark) & {
    color: var(--gray-400);

    &:hover {
      color: var(--gray-300);
    }
  }
}

.hero-section {
  flex: 1;
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 5rem 2rem 2rem;
}

.hero-layout {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 2.5rem;
  align-items: center;
  max-width: 1200px;
  margin: 0 auto;
  padding-top: 4rem;
}

.hero-content {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.title {
  font-size: clamp(2.5rem, 4vw, 4rem);
  font-weight: 800;
  margin: 0;
  background: linear-gradient(135deg, var(--main-900), var(--main-600));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  letter-spacing: -0.02em;
  line-height: 1.1;
}

.hero-eyebrow {
  color: var(--main-600);
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 0.85rem;
}

.subtitle {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--gray-700);
  line-height: 1.4;
}

.description {
  color: var(--gray-600);
  line-height: 1.6;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
}

.button-base {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.5rem 2.75rem;
  border-radius: 999px;
  font-size: 1.05rem;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
  text-decoration: none;
  transition: all 0.25s ease;
  min-height: 52px;
}

.button-base.primary {
  background: linear-gradient(135deg, var(--main-600), var(--main-500));
  color: var(--gray-0);
  border-color: transparent;

  &:hover {
    background: linear-gradient(135deg, var(--main-700), var(--main-600));
  }
}

.button-base.secondary {
  background: rgba(2, 57, 68, 0.06);
  color: var(--main-700);
  border-color: var(--gray-100);

  &:hover {
    border-color: var(--main-200);
    background: var(--gray-50);
  }
}

.insight-panel {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  background: var(--main-0);
  border-radius: 1.5rem;
  padding: 1.5rem;
  border: 1px solid var(--main-40);
  box-shadow: 0 15px 35px rgba(3, 80, 101, 0.08);
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.stat-headline {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--gray-25);
  display: inline-flex;
  align-items: center;
  justify-content: center;

  :deep(svg) {
    width: 24px;
    height: 24px;
    color: var(--main-700);
  }
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--main-800);
  margin: 0;
}

.stat-label {
  margin: 0;
  color: var(--gray-700);
  font-weight: 600;
}

.stat-description {
  margin: 0;
  color: var(--gray-600);
  font-size: 0.9rem;
}

.section {
  width: 100%;
  max-width: 1200px;
  margin: 50px auto 0px auto;
  padding: 2rem 0;
}

.section-header {
  margin-bottom: 1.5rem;

  h2 {
    margin: 0 0 0.5rem;
    font-size: 1.8rem;
    color: var(--main-800);
  }

  p {
    margin: 0;
    color: var(--gray-600);
  }
}

.action-section {
  padding-bottom: 3rem;
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
}

.action-card {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  padding: 1rem 1.25rem;
  border-radius: 1rem;
  text-decoration: none;
  color: inherit;
  border: 1px solid var(--gray-50);
  background: var(--gray-0);
  transition:
    transform 0.2s ease,
    background 0.2s ease;

  &:hover {
    background: var(--gray-0);
    transform: translateY(-2px);
  }
}

.action-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--gray-50);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  :deep(svg) {
    width: 22px;
    height: 22px;
    color: var(--main-700);
  }
}

.action-meta {
  flex: 1;
  overflow: hidden;
}

.action-title {
  margin: 0;
  font-weight: 600;
  color: var(--main-800);
}

.action-url {
  margin: 0.25rem 0 0;
  font-size: 0.9rem;
  color: var(--gray-600);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
      color: var(--gray-0);

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
  background: var(--main-0);
  border-top: 1px solid var(--main-20);
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
    padding: 0.8rem 1.25rem;
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
    font-size: 2.4rem;
  }

  .subtitle {
    font-size: 1.2rem;
  }

  .start-button {
    width: 100%;
    text-align: center;
  }

  .hero-content {
    padding: 0;
  }

  .github-link a {
    padding: 0.5rem 0.8rem;
    font-size: 0.85rem;

    .stars-count {
      display: none;
    }
  }

  .hero-layout {
    padding: 0 0.5rem;
  }
}
</style>
