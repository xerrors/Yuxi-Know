<script setup>
import { ref, KeepAlive, onMounted } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  MessageOutlined,
  MessageFilled,
  SettingOutlined,
  SettingFilled,
  BookOutlined,
  BookFilled,
  GithubOutlined,
  DatabaseOutlined,
  DatabaseFilled,
  GoldOutlined,
  GoldFilled,
  BugOutlined,
} from '@ant-design/icons-vue'
import { themeConfig } from '@/assets/theme'
import { useConfigStore } from '@/stores/config'
import { useDatabaseStore } from '@/stores/database'
import DebugComponent from '@/components/DebugComponent.vue'

const configStore = useConfigStore()
const databaseStore = useDatabaseStore()

const showDebug = ref(false)

const getRemoteConfig = () => {
  fetch('/api/config').then(res => res.json()).then(data => {
    console.log(data)
    configStore.setConfig(data)
  })
}

const getRemoteDatabase = () => {
  if (!configStore.config.enable_knowledge_base) {
    return
  }
  fetch('/api/database').then(res => res.json()).then(data => {
    console.log("database", data)
    databaseStore.setDatabase(data.databases)
  })
}

onMounted(() => {
  getRemoteDatabase()
  getRemoteConfig()
})

// 打印当前页面的路由信息，使用 vue3 的 setup composition API
const route = useRoute()
console.log(route)
</script>

<template>
  <div class="app-layout">
    <div class="debug-panel">
      <div class="shown-btn" @click="showDebug=!showDebug"><BugOutlined /></div>
      <a-drawer
        v-model:open="showDebug"
        title="调试面板"
        width="800"
        :contentWrapperStyle="{ maxWidth: '100%'}"
        placement="right"
      >
        <DebugComponent />
      </a-drawer>
    </div>
    <div class="header">
      <div class="logo">
        <router-link to="/"><img src="/jnu.png"> </router-link>
      </div>
      <div class="nav">
        <RouterLink to="/chat" class="nav-item" active-class="active">
          <component class="icon" :is="route.path === '/chat' ? MessageFilled : MessageOutlined" />
        </RouterLink>
        <RouterLink to="/database" class="nav-item" active-class="active">
          <component class="icon" :is="route.path.startsWith('/database') ? DatabaseFilled : DatabaseOutlined" />
        </RouterLink>
        <RouterLink to="/graph" class="nav-item" active-class="active">
          <component class="icon" :is="route.path.startsWith('/graph') ? GoldFilled: GoldOutlined" />
        </RouterLink>
      </div>
      <div class="fill" style="flex-grow: 1;"></div>
      <div class="github nav-item">
        <a href="https://github.com/xerrors/ProjectAthena" target="_blank">
          <GithubOutlined  class="icon" style="color: #222;"/>
        </a>
      </div>
      <RouterLink  class="nav-item setting" to="/setting" active-class="active">
        <component class="icon" :is="route.path === '/setting' ? SettingFilled : SettingOutlined" />
      </RouterLink>
    </div>
    <div class="header-mobile">
      <RouterLink to="/chat" class="nav-item" active-class="active">对话</RouterLink>
      <RouterLink to="/database" class="nav-item" active-class="active">知识</RouterLink>
      <RouterLink to="/setting" class="nav-item" active-class="active">设置</RouterLink>
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

  .header-mobile {
    display: none;
  }

  .debug-panel {
    position: absolute;
    z-index: 100;
    right: 0;
    bottom: 50px;
    border-radius: 20px 0 0 20px;
    background-color: var(--main-light-4);
    padding: 6px;
    padding-left: 12px;
    box-shadow: 0 0 10px 5px rgba(0, 0, 0, 0.05);
    border: 1px solid var(--c-black-soft);
    transition: right 0.3s ease-in-out;
    cursor: pointer;
  }
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
  flex: 0 0 70px;
  justify-content: flex-start;
  align-items: center;
  background-color: var(--main-light-3);
  height: 100%;
  width: 70px;
  border-right: 1px solid var(--main-light-3);

  .logo {
    width: 40px;
    height: 40px;
    margin: 18px 0 35px 0;

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

  .nav-item {
    padding: 8px 16px;
    border: none;
    border-radius: 8px;
    background-color: transparent;
    color: #222;
    font-size: 20px;
    transition: background-color 0.2s ease-in-out;
    margin: 0 10px;

    &.active {
      font-weight: bold;
      color: var(--main-600);
      background-color: rgba(  0,  93, 125, 0.1);
    }

    &:hover {
      background-color: rgba(  0,  93, 125, 0.1);
      cursor: pointer;
    }
  }

  .setting {
    width: auto;
    font-size: 20px;
    color: #333;
    margin-bottom: 20px;
    margin-top: 10px;

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
}

@media (max-width: 520px) {
  .app-layout {
    flex-direction: column-reverse;

    div.header {
      display: none;
    }
  }

  .app-layout div.header-mobile {
    display: flex;
    flex-direction: row;
    width: 100%;
    padding: 0 20px;
    justify-content: space-around;
    align-items: center;
    flex: 0 0 60px;
    border-right: none;

    .nav-item {
      text-decoration: none;
      width: 40px;
      color: var(--c-black-soft);
      font-size: 1rem;
      font-weight: bold;
      transition: color 0.1s ease-in-out, font-size 0.1s ease-in-out;

      &.active {
        color: black;
        font-size: 1.1rem;
      }
    }
  }
  .app-layout .chat-box::webkit-scrollbar {
    width: 0;
  }
}
</style>
