<template>
  <div class="not-found">
    <h1>404 - 页面还没做</h1>
    <p>Sorry, Yemian has not been zuoed.</p>
    <a-button @click="sendRestart" :loading="state.loading">重载</a-button>
    <p>{{ configStore.config }}</p>
  </div>
</template>

<script setup>
import { message } from 'ant-design-vue';
import { reactive, ref } from 'vue'
import { useConfigStore } from '@/stores/counter';

const configStore = useConfigStore()
const state = reactive({
  loading: false,
})

const sendRestart = () => {
  console.log('Restarting...')
  state.loading = true
  fetch('/api/restart', {
    method: 'POST',
  }).then(() => {
    console.log('Restarted')
    state.loading = false
    message.success('重载成功')
    setTimeout(() => {
      window.location.reload()
    }, 1000)
  })
}
</script>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 80vh;
  text-align: center;
}

.not-found h1 {
  font-size: 2rem;
  margin-bottom: 1rem;
}

.not-found p {
  font-size: 1.5rem;
  margin-bottom: 2rem;
}

</style>
