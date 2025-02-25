<script setup>
import { ref, reactive, KeepAlive, onMounted } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  MessageOutlined,
  MessageFilled,
  SettingOutlined,
  SettingFilled,
  BookOutlined,
  BookFilled,
  GithubOutlined,
  FolderOutlined,
  FolderFilled,
  GoldOutlined,
  GoldFilled,
  ToolFilled,
  ToolOutlined,
  BugOutlined,
  ProjectFilled,
  ProjectOutlined,
  StarFilled,
  StarOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons-vue'
import { themeConfig } from '@/assets/theme'
import { useConfigStore } from '@/stores/config'
import { useDatabaseStore } from '@/stores/database'
import DebugComponent from '@/components/DebugComponent.vue'

const configStore = useConfigStore()
const databaseStore = useDatabaseStore()

const layoutSettings = reactive({
  showDebug: false,
  useTopBar: false, // 是否使用顶栏
})

const getRemoteConfig = () => {
  configStore.refreshConfig()
}

const getRemoteDatabase = () => {
  if (!configStore.config.enable_knowledge_base) {
    return
  }
  databaseStore.refreshDatabase()
}

onMounted(() => {
  getRemoteConfig()
  getRemoteDatabase()
})

// 打印当前页面的路由信息，使用 vue3 的 setup composition API
const route = useRoute()
console.log(route)
</script>

<template>
  <div class="app-layout" :class="{ 'use-top-bar': layoutSettings.useTopBar }">
    <div class="debug-panel" >
      <a-float-button
        @click="layoutSettings.showDebug = !layoutSettings.showDebug"
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
        v-model:open="layoutSettings.showDebug"
        title="调试面板"
        width="800"
        :contentWrapperStyle="{ maxWidth: '100%'}"
        placement="right"
      >
        <DebugComponent />
      </a-drawer>
    </div>
    <div class="header" :class="{ 'top-bar': layoutSettings.useTopBar }">
      <div class="logo circle">
        <router-link to="/">
          <img src="/avatar.jpg">
          <span class="logo-text">语析</span>
        </router-link>
      </div>
      <div class="nav">
        <RouterLink to="/chat" class="nav-item" active-class="active">
          <component class="icon" :is="route.path === '/chat' ? MessageFilled : MessageOutlined" />
          <span class="text">对话</span>
        </RouterLink>
        <RouterLink to="/database" class="nav-item" active-class="active">
          <component class="icon" :is="route.path.startsWith('/database') ? FolderFilled : FolderOutlined" />
          <span class="text">知识</span>
        </RouterLink>
        <RouterLink to="/graph" class="nav-item" active-class="active">
          <component class="icon" :is="route.path.startsWith('/graph') ? ProjectFilled: ProjectOutlined" />
          <span class="text">图谱</span>
        </RouterLink>
        <RouterLink to="/tools" class="nav-item" active-class="active">
          <component class="icon" :is="route.path.startsWith('/tools') ? ToolFilled: ToolOutlined" />
          <span class="text">工具</span>
        </RouterLink>
        <a-tooltip placement="right">
          <template #title>后端疑似没有正常启动或者正在繁忙中，请刷新一下或者检查 docker logs api-dev</template>
          <div class="nav-item warning" v-if="!configStore.config._config_items">
            <component class="icon" :is="ExclamationCircleOutlined" />
            <span class="text">警告</span>
          </div>
        </a-tooltip>
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
  background-color: var(--gray-100);
  height: 100%;
  width: 74px;
  border-right: 1px solid var(--gray-300);

  .logo {
    width: 40px;
    height: 40px;
    margin: 18px 0 18px 0;

    img {
      width: 100%;
      height: 100%;
      border-radius: 4px;  // 50% for circle
    }

    .logo-text {
      display: none;
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
      &:hover {
        background-color: transparent;
        border: 1px solid transparent;
      }
    }

    &.setting {
      padding: 16px 12px;
      width: 56px;
    }

    &.active {
      font-weight: bold;
      color: var(--main-600);
      background-color: white;
      border: 1px solid white;
    }

    &.warning {
      color: red;
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

.app-layout.use-top-bar {
  flex-direction: column;
}

.header.top-bar {
  flex-direction: row;
  flex: 0 0 50px;
  width: 100%;
  height: 50px;
  border-right: none;
  border-bottom: 1px solid var(--main-light-2);
  background-color: var(--main-light-3);
  padding: 0 20px;
  gap: 24px;

  .logo {
    width: fit-content;
    height: 28px;
    margin-right: 16px;
    display: flex;
    align-items: center;

    a {
      display: flex;
      align-items: center;
      text-decoration: none;
      color: inherit;
    }

    img {
      width: 28px;
      height: 28px;
      margin-right: 8px;
    }

    .logo-text {
      display: block;
      font-size: 16px;
      font-weight: 600;
      letter-spacing: 0.5px;
      color: var(--main-600);
      white-space: nowrap;
    }
  }

  .nav {
    flex-direction: row;
    height: auto;
    gap: 20px;
  }

  .nav-item {
    flex-direction: row;
    width: auto;
    padding: 4px 16px;
    margin: 0;

    .icon {
      margin-right: 8px;
      font-size: 15px; // 减小图标大小
    }

    .text {
      margin-top: 0;
      font-size: 15px;
    }


    &.github, &.setting {
      padding: 8px 12px;

      .icon {
        margin-right: 0;
        font-size: 18px;
      }

      &.active {
        color: var(--main-600);
      }
    }

    &.github {
      a {
        display: flex;
        justify-content: center;
        align-items: center;
      }
    }
  }
}

</style>
