<template>
  <div class="welcome">
    <header class="glass-header">江南语析</header>
    <h1>{{ title }}</h1>
    <p>大模型驱动的知识库管理工具</p>
    <button class="home-btn" @click="goToChat">开始对话</button>
    <img src="/home.png" alt="Placeholder Image" />
    <footer>© 江南语析 2025 [WIP] v0.12.138</footer>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

const title = ref('📢 Yuxi-Know ✨')
const router = useRouter()

const goToChat = () => {
  router.push("/chat")
}

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
