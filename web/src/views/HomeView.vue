<template>
  <div class="welcome">
    <h1>{{ title }}</h1>
    <p>{{ description }}</p>
    <img src="/home.png" alt="Placeholder Image" />
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'

const title = ref('Project: Athena ✨')
const description = ref('代号：雅典娜！')
const image = ref('/home.png')
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

h1 {
  font-size: 48px;
  font-weight: bold;
  margin-bottom: 0;
  margin-top: calc(10vh - 80px);
}

p {
  font-size: 24px;
  text-align: center;
  margin-bottom: calc(15vh - 80px);
}

img {
  width: 700px;
  height: auto;
  object-fit: cover;
  box-shadow: 0px 5px 10px rgba(0, 0, 0, 0.05);
  border-radius: 1rem;
}
</style>
