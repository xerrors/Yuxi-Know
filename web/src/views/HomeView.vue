<template>
  <div class="welcome">
    <header class="glass-header">江南语析</header>
    <h1>{{ title }}</h1>
    <p>大模型驱动的知识库管理工具</p>
    <button class="home-btn" @click="goToChat">开始对话</button>
    <img src="/home.png" alt="Placeholder Image" />

    <div class="github-info">
      <a href="https://github.com/xerrors/Yuxi-Know" target="_blank">
        <svg height="24" width="24" viewBox="0 0 16 16" version="1.1">
          <path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
        </svg>
        <span class="stars-count">{{ isLoadingStars ? '加载中...' : githubStars }} ⭐</span>
      </a>
    </div>

    <footer>© 江南语析 2025 [WIP] v0.12.138</footer>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const title = ref('📢 Yuxi-Know ✨')
const router = useRouter()
const githubStars = ref(0)
const isLoadingStars = ref(false)

const goToChat = () => {
  router.push("/chat")
}

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

onMounted(() => {
  fetchGithubStars()
})

</script>


<style lang="less" scoped>
.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 100vh;
  color: #333;
  text-align: center;
  background: linear-gradient(168deg, #ffd6eb, #ffe7ca, #d3fffb, #dbebff, #ffd8ff);
  background-size: 1000% 1000%;
  animation: animateBackground 20s ease infinite;
}



header {
  font-size: 1.2rem;
  font-weight: bold;
  color: var(--main-color);
  width: 100%;
  padding: 1rem 0;
  backdrop-filter: blur(10px);
  width: 100%;
  background-color: rgba(255, 255, 255, 0.25);
  border-bottom: 2px solid var(--main-color);
}

h1 {
  font-size: 48px;
  font-weight: 600;
  margin-top: calc(20vh - 80px);
  margin-bottom: 0;
}

p {
  font-size: 18px;
  text-align: center;
}

button.home-btn {
  padding: 0.5rem 2rem;
  font-size: 24px;
  font-weight: bold;
  color: white;
  background-color: #333;
  border: none;
  border-radius: 3rem;
  cursor: pointer;
  transition: all 0.3s;
  margin-top: 20px;
  margin-bottom: calc(15vh - 80px);
  transition: all 0.3s;

  &:hover {
    background-color: #555;
    transform: translateY(-2px);
    box-shadow: 0px 5px 10px rgba(0, 0, 0, 0.1);
  }
}

img {
  width: 700px;
  height: auto;
  object-fit: cover;
  box-shadow: 0px 5px 10px rgba(0, 0, 0, 0.05);
  border-radius: 1rem;
  max-width: 90%;
}

.github-info {
  margin-top: 20px;

  a {
    display: flex;
    align-items: center;
    text-decoration: none;
    color: #333;
    padding: 8px 16px;
    border-radius: 20px;
    background-color: rgba(255, 255, 255, 0.5);
    transition: all 0.3s;

    &:hover {
      background-color: rgba(255, 255, 255, 0.8);
      transform: translateY(-2px);
      box-shadow: 0px 3px 8px rgba(0, 0, 0, 0.1);
    }

    svg {
      margin-right: 8px;
    }

    .stars-count {
      font-weight: 600;
      font-size: 16px;
    }
  }
}

footer {
  font-size: 1rem;
  color: #666;
  margin-top: auto;
  padding: 1rem 0;
}
/* 动态背景动画 */
@keyframes animateBackground {
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
</style>
