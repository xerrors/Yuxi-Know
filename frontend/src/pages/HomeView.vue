<template>
  <div class="home-container">
    <!-- 加载中状态 -->
    <div v-if="isLoading" class="loading-container">
      <a-spin size="large" />
      <p class="loading-text">正在连接服务...</p>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-container">
      <a-result status="error" :title="error.title" :sub-title="error.message">
        <template #extra>
          <a-button type="primary" @click="retryLoad">重试</a-button>
          <a-button :href="docsUrl" target="_blank" rel="noopener noreferrer">常见问题</a-button>
        </template>
      </a-result>
    </div>

    <!-- 正常内容 -->
    <template v-else>
      <div class="ambient" aria-hidden="true"></div>
      <header class="site-header">
        <div class="logo">
          <img
            :src="infoStore.organization.logo"
            :alt="infoStore.organization.name"
            class="logo-img"
          />
          <span class="logo-text">{{ infoStore.organization.name }}</span>
        </div>
        <div class="header-actions">
          <a class="header-docs" :href="docsUrl" target="_blank" rel="noopener noreferrer">
            使用文档 <ArrowUpRight :size="14" aria-hidden="true" />
          </a>
          <a
            class="github-link"
            href="https://github.com/xerrors/Yuxi"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="GitHub"
          >
            <svg height="20" width="20" viewBox="0 0 16 16" version="1.1">
              <path
                fill-rule="evenodd"
                d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
              ></path>
            </svg>
          </a>
          <UserInfoComponent :show-button="true" />
        </div>
      </header>

      <main class="hero-section">
        <div class="hero-content">
          <h1 class="title">{{ infoStore.branding.title }}</h1>
          <div class="subtitle-wrap">
            <p
              v-for="subtitle in subtitleOptions"
              :key="subtitle"
              class="subtitle subtitle-measure"
              aria-hidden="true"
            >
              {{ subtitle }}
            </p>
            <Transition name="subtitle-switch">
              <p v-if="currentSubtitle" class="subtitle" :key="currentSubtitle">
                {{ currentSubtitle }}
              </p>
            </Transition>
          </div>
          <div class="hero-actions">
            <button class="button-base primary" @click="goToChat">
              <span>开始体验</span>
              <ArrowRight :size="16" aria-hidden="true" />
            </button>
            <a
              class="button-base secondary"
              :href="docsUrl"
              target="_blank"
              rel="noopener noreferrer"
            >
              <BookText :size="16" aria-hidden="true" />
              <span>查看文档</span>
            </a>
          </div>
        </div>
      </main>

      <footer class="footer">
        <div class="footer-content">
          <p class="copyright">
            {{ infoStore.footer?.copyright || '© 2025 All rights reserved' }}
          </p>
        </div>
      </footer>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/modules/identity/model/user'
import { useInfoStore } from '@/modules/settings/model/info'
import { healthApi } from '@/apis/system_api'
import UserInfoComponent from '@/modules/settings/ui/UserInfoComponent.vue'
import { ArrowRight, ArrowUpRight, BookText } from '@lucide/vue'

const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()
const docsUrl = 'https://xerrors.github.io/Yuxi/'

// 加载状态
const isLoading = ref(true)
const error = ref(null)
const subtitleIndex = ref(0)
let subtitleTimer = null

const subtitleOptions = computed(() => {
  const subtitles = infoStore.branding?.subtitles
  if (Array.isArray(subtitles)) {
    const list = subtitles
      .map((item) => (typeof item === 'string' ? item.trim() : ''))
      .filter(Boolean)
    if (list.length) {
      return list
    }
  }

  const fallback = (infoStore.branding?.subtitle || '').trim()
  return fallback ? [fallback] : []
})

const currentSubtitle = computed(() => subtitleOptions.value[subtitleIndex.value] || '')

const stopSubtitleCarousel = () => {
  if (subtitleTimer) {
    clearInterval(subtitleTimer)
    subtitleTimer = null
  }
}

const startSubtitleCarousel = () => {
  stopSubtitleCarousel()
  subtitleIndex.value = 0

  if (subtitleOptions.value.length <= 1) {
    return
  }

  subtitleTimer = setInterval(() => {
    subtitleIndex.value = (subtitleIndex.value + 1) % subtitleOptions.value.length
  }, 2800)
}

const checkHealth = async () => {
  try {
    const response = await healthApi.checkHealth()
    if (response.status !== 'ok') {
      throw new Error('服务不可用')
    }
  } catch (e) {
    error.value = {
      title: '服务连接失败',
      message: '后端服务无法响应，请检查服务是否正常运行'
    }
    throw e
  }
}

const loadData = async () => {
  isLoading.value = true
  error.value = null

  try {
    // 先检查健康状态
    await checkHealth()
    // 健康检查通过后加载配置
    await infoStore.loadInfoConfig()
    startSubtitleCarousel()
  } catch (e) {
    console.error('加载失败:', e)
    stopSubtitleCarousel()
  } finally {
    isLoading.value = false
  }
}

const retryLoad = () => {
  loadData()
}

const goToChat = async () => {
  if (!userStore.isLoggedIn) {
    sessionStorage.setItem('redirect', '/')
    router.push('/login')
    return
  }

  router.push('/agent')
}

onMounted(() => {
  loadData()
})

onUnmounted(() => {
  stopSubtitleCarousel()
})
</script>

<style lang="less" scoped>
.home-container {
  position: relative;
  isolation: isolate;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  color: var(--gray-900);
  background: var(--gray-10);
}

.ambient {
  position: absolute;
  inset: 0;
  z-index: -1;
  overflow: hidden;
  pointer-events: none;
  background:
    radial-gradient(ellipse at 50% 32%, var(--gray-0) 0%, transparent 58%),
    radial-gradient(
      ellipse at 85% 65%,
      color-mix(in srgb, var(--main-50) 65%, transparent),
      transparent 60%
    ),
    radial-gradient(
      ellipse at 10% 95%,
      color-mix(in srgb, var(--second-50) 50%, transparent),
      transparent 50%
    );

  &::before,
  &::after {
    content: '';
    position: absolute;
    width: 160%;
    height: 85%;
    left: -30%;
    top: 76%;
    border: 1px solid color-mix(in srgb, var(--main-200) 28%, transparent);
    border-radius: 50%;
    transform: rotate(-12deg);
  }

  &::after {
    top: 82%;
    left: -24%;
    border-color: color-mix(in srgb, var(--main-200) 18%, transparent);
  }
}

.loading-container,
.error-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100dvh;
  padding: 24px;
}

.loading-container {
  flex-direction: column;
  gap: 16px;

  .loading-text {
    color: var(--gray-600);
    font-size: 14px;
  }
}

.site-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  width: min(1328px, 100%);
  margin: 0 auto;
  padding: 28px 48px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-shrink: 0;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.logo-img {
  width: 32px;
  height: 32px;
  object-fit: contain;
  flex-shrink: 0;
}

.logo-text {
  font-size: 20px;
  font-weight: 600;
  color: var(--main-900);
  overflow-wrap: anywhere;
}

.header-docs {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  text-decoration: none;
  color: var(--gray-600);

  &:hover {
    color: var(--main-700);
  }
}

.github-link {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  color: var(--gray-600);
  transition:
    color 0.2s,
    background 0.2s;

  &:hover {
    color: var(--main-700);
    background: var(--gray-100);
  }

  svg {
    fill: currentColor;
  }
}

.hero-section {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 72px 40px 144px;
}

.hero-content {
  width: 100%;
  max-width: 1160px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.title {
  margin: 0;
  font-size: 56px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--main-900);
  overflow-wrap: anywhere;
}

// 最长候选文案预留高度，轮播不改变按钮位置。
.subtitle-wrap {
  display: grid;
  width: 100%;
  max-width: 640px;
  margin-top: 24px;
}

.subtitle {
  grid-area: 1 / 1;
  margin: 0;
  font-size: 16px;
  font-weight: 400;
  color: var(--gray-600);
  line-height: 1.8;
  overflow-wrap: anywhere;
}

.subtitle-measure {
  visibility: hidden;
}

.subtitle-switch-enter-active,
.subtitle-switch-leave-active {
  transition: opacity 0.4s ease;
}

.subtitle-switch-enter-from,
.subtitle-switch-leave-to {
  opacity: 0;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 16px;
  margin-top: 40px;
}

.button-base {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  min-height: 48px;
  padding: 12px 26px;
  border: 1px solid transparent;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  transition:
    background 0.2s,
    border-color 0.2s,
    color 0.2s;
}

.button-base.primary {
  background: linear-gradient(180deg, var(--main-700), var(--main-800));
  border-color: var(--main-800);
  color: var(--color-on-primary);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--main-300) 30%, transparent);

  &:hover {
    background: var(--main-800);
  }
}

.button-base.secondary {
  background: color-mix(in srgb, var(--gray-0) 80%, transparent);
  color: var(--gray-700);
  border-color: var(--gray-200);

  &:hover {
    background: var(--gray-0);
    border-color: var(--gray-400);
    color: var(--gray-900);
  }
}

.button-base:focus-visible,
.github-link:focus-visible,
.header-docs:focus-visible {
  outline: 2px solid var(--main-700);
  outline-offset: 4px;
}

.footer-content {
  margin: 0 auto;
  padding: 24px;
  text-align: center;
}

.copyright {
  color: var(--gray-600);
  font-size: 11px;
  margin: 0;
}

@media (max-width: 1100px) {
  .title {
    font-size: 44px;
  }
}

@media (max-width: 800px) {
  .site-header {
    padding: 24px 32px;
  }

  .header-actions {
    gap: 16px;
  }

  .hero-section {
    padding: 64px 32px 112px;
  }

  .title {
    font-size: 40px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .subtitle-switch-enter-active,
  .subtitle-switch-leave-active,
  .button-base,
  .github-link {
    transition: none;
  }
}
</style>
