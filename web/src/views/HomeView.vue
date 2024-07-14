<template>
  <div class="welcome">
    <header>江南大学人工智能与计算机学院</header>
    <h1>{{ title }}</h1>
    <button class="home-btn" @click="goToChat">开始对话</button>
    <img src="/home.png" alt="Placeholder Image" />
    <footer>© 江南语析 2024</footer>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

const title = ref('Athena ✨')
const router = useRouter()

const goToChat = () => {
  router.push("/chat")
}

</script>

<style scoped>
.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  /* margin-top: 50px; */
  color: #333;
  text-align: center;
}

header {
  background-color: var(--main-color);
  font-size: 1.2rem;
  font-weight: bold;
  color: aliceblue;
  width: 100%;
  padding: 1rem 0;
}

h1 {
  font-size: 48px;
  font-weight: bold;
  margin-top: calc(20vh - 80px);
}

p {
  font-size: 24px;
  text-align: center;
}

img {
  width: 700px;
  height: auto;
  object-fit: cover;
  box-shadow: 0px 5px 10px rgba(0, 0, 0, 0.05);
  border-radius: 1rem;
  max-width: 90%;
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
  margin-bottom: calc(15vh - 80px);
}

footer {
  font-size: 1rem;
  color: #666;
  margin-top: 20px;
}
</style>
