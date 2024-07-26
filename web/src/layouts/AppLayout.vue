<script setup>
import { KeepAlive, onMounted } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  MessageOutlined,
  MessageFilled,
  SettingOutlined,
  SettingFilled,
  BookOutlined,
  BookFilled
} from '@ant-design/icons-vue'
import { themeConfig } from '@/assets/theme'
import { useConfigStore } from '@/stores/counter'

const configStore = useConfigStore()

const getRemoteConfig = () => {
  fetch('/api/config').then(res => res.json()).then(data => {
    console.log(data)
    configStore.setConfig(data)
  })
}

onMounted(() => {
  getRemoteConfig()
})

// 打印当前页面的路由信息，使用 vue3 的 setup composition API
const route = useRoute()
console.log(route)
</script>

<template>
  <div class="app-layout">
    <div class="header">
      <div class="logo">
        <router-link to="/"><img src="/jnu.png"> </router-link>
      </div>
      <div class="nav">
        <RouterLink to="/chat" class="nav-item" active-class="active">
          <component class="icon" :is="route.path === '/chat' ? MessageFilled : MessageOutlined" />
          <span class="text">对话</span>
        </RouterLink>
        <RouterLink to="/database" class="nav-item" active-class="active">
          <component class="icon" :is="route.path.startsWith('/database') ? BookFilled : BookOutlined" />
          <span class="text">知识</span>
        </RouterLink>
      </div>
      <div class="fill" style="flex-grow: 1;"></div>
      <RouterLink  class="nav-item setting" to="/setting" active-class="active">
        <component class="icon" :is="route.path === '/setting' ? SettingFilled : SettingOutlined" />
      </RouterLink>
    </div>
    <a-config-provider :theme="themeConfig">
    <router-view v-slot="{ Component }" id="app-router-view">
      <keep-alive>
        <component :is="Component" />
      </keep-alive>
    </router-view>
    </a-config-provider>
  </div>
</template>

<style lang="less" scoped>
@import '@/assets/main.css';

.app-layout {
  display: flex;
  flex-direction: row;
  width: 100%;
  height: 100vh;
  min-width: var(--min-width);
}

div.header, #app-router-view {
  height: 100%;
  max-width: 100%;
}

#app-router-view {
  flex: 1 1 auto;
  overflow-y: auto;
}

.header {
  display: flex;
  flex-direction: column;
  flex: 0 0 80px;
  justify-content: flex-start;
  align-items: center;
  background-color: var(--main-light-4);
  height: 100%;
  width: 80px;
  border-right: 1px solid var(--main-light-2);

  .logo {
    width: 40px;
    height: 40px;
    margin: 30px 0;

    img {
      width: 100%;
      height: 100%;
      border-radius: 50%;
    }

    & > a {
      text-decoration: none;
      font-size: 24px;
      font-weight: bold;
      color: #333;
    }
  }

  .setting {
    width: auto;
    font-size: 20px;
    color: #333;
    margin: 20px 0;

    &:hover {
      cursor: pointer;
    }
  }
}

.header .nav {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: center;
  position: relative;
  height: 45px;
  gap: 16px;

  .nav-item {
    padding: 8px 16px;
    border: none;
    border-radius: 8px;
    background-color: transparent;
    color: #222;
    font-size: 20px;
    transition: background-color 0.2s ease-in-out;
    margin: 0 10px;

    .text {
      display: none;
    }

    &.active {
      font-weight: bold;
      color: var(--main-color);
      background-color: var(--main-light-2);
    }

    &:hover {
      background-color: var(--main-light-2);
      cursor: pointer;
    }
  }
}

@media (max-width: 520px) {
  .app-layout {
    flex-direction: column-reverse;
  }

  .app-layout div.header {
    flex-direction: row;
    width: 100%;
    height: 40px;
    padding: 0 20px;
    justify-content: space-between;
    align-items: center;
    flex: 0 0 60px;
    border-right: none;
    border-top: 1px solid var(--main-light-2);

    .logo {
      display: none;
      flex-shrink: 0;
      width: 40px;
      height: 40px;
      margin: 0;
    }

    .setting {
      margin: 0;
      width: 60px;
    }
  }



  .app-layout .nav {
    flex-direction: row;
    height: 100%;
    width: 100%;
    justify-content: center;
    gap: 0;

    .nav-item {
      text-decoration: none;

      span.text {
        display: block;
        color: #333;
      }
      span.icon {
        display: none;
      }
    }

    .nav-item:hover {
      background-color: transparent;
    }

    .nav-item.active {
      font-weight: bold;
      background-color: transparent;

      span.text {
        font-weight: bold;
      }
    }
  }
  .app-layout .chat-box::webkit-scrollbar {
    width: 0;
  }
}
</style>
