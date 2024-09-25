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
  ProjectFilled,
  ProjectOutlined,
  StarFilled,
  StarOutlined,
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
    <div class="debug-panel" >
      <a-float-button
        @click="showDebug=!showDebug"
        tooltip="调试面板"
        :style="{
          right: '12px',
        }"
      >
        <template #icon>
          <BugOutlined />
        </template>
      </a-float-button>
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
          <span class="text">对话</span>
        </RouterLink>
        <RouterLink to="/database" class="nav-item" active-class="active">
          <component class="icon" :is="route.path.startsWith('/database') ? DatabaseFilled : DatabaseOutlined" />
          <span class="text">知识</span>
        </RouterLink>
        <RouterLink to="/graph" class="nav-item" active-class="active">
          <component class="icon" :is="route.path.startsWith('/graph') ? ProjectFilled: ProjectOutlined" />
          <span class="text">图谱</span>
        </RouterLink>
        <RouterLink to="/tools" class="nav-item" active-class="active">
          <component class="icon" :is="route.path.startsWith('/tools') ? StarFilled: StarOutlined" />
          <span class="text">工具</span>
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
    <router-view v-slot="{ Component, route }" id="app-router-view">
      <keep-alive v-if="route.meta.keepAlive !== false">
        <component :is="Component" />
      </keep-alive>
      <component :is="Component" v-else />
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
    cursor: pointer;
  }
}

div.header, #app-router-view {
  height: 100%;
  max-width: 100%;
  user-select: none;
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
  background-color: var(--main-light-4);
  height: 100%;
  width: 74px;
  border-right: 1px solid var(--main-light-3);

  .logo {
    width: 40px;
    height: 40px;
    margin: 18px 0 18px 0;

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
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 52px;
    padding: 4px;
    padding-top: 10px;
    border: 1px solid transparent;
    border-radius: 8px;
    background-color: transparent;
    color: #222;
    font-size: 20px;
    transition: background-color 0.2s ease-in-out;
    margin: 0 10px;
    text-decoration: none;
    cursor: pointer;

    &.github {
      padding: 10px 12px;
    }

    &.setting {
      padding: 16px 12px;
      width: 56px;
    }

    &.active {
      font-weight: bold;
      color: var(--main-600);
      background-color: rgba(255, 255, 255, 0.8);
      backdrop-filter: blur(10px);
      border: 1px solid white;
    }

    &:hover {
      background-color: rgba(255, 255, 255, 0.8);
      backdrop-filter: blur(10px);
    }

    .text {
      font-size: 12px;
      margin-top: 4px;
      text-align: center;
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
      color: var(--gray-900);
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
