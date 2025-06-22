import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'

import Antd from 'ant-design-vue';
import 'ant-design-vue/dist/reset.css';
import './assets/main.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(Antd)

// 预加载信息配置
import { useInfoStore } from '@/stores/info'
const infoStore = useInfoStore()
infoStore.loadInfoConfig().then(() => {
  console.log('应用信息配置预加载完成')
})

app.mount('#app')
