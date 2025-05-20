<script setup>
import { ref, reactive, KeepAlive, onMounted, computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  GithubOutlined,
  BugOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons-vue'
import { Bot, Waypoints, LibraryBig, MessageSquareMore, Settings } from 'lucide-vue-next';

import { useConfigStore } from '@/stores/config'
import { useDatabaseStore } from '@/stores/database'
import DebugComponent from '@/components/DebugComponent.vue'
import UserInfoComponent from '@/components/UserInfoComponent.vue'

const configStore = useConfigStore()
const databaseStore = useDatabaseStore()

const layoutSettings = reactive({
  showDebug: false,
  useTopBar: false, // 是否使用顶栏
})

// Add state for GitHub stars
const githubStars = ref(0)
const isLoadingStars = ref(false)

const getRemoteConfig = () => {
  configStore.refreshConfig()
}

const getRemoteDatabase = () => {
  if (!configStore.config.enable_knowledge_base) {
    return
  }
  databaseStore.refreshDatabase()
}

// Fetch GitHub stars count
const fetchGithubStars = async () => {
  try {
    isLoadingStars.value = true
    // 公共API，可以直接使用fetch
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
  getRemoteConfig()
  getRemoteDatabase()
  fetchGithubStars() // Fetch GitHub stars on mount
})

// 打印当前页面的路由信息，使用 vue3 的 setup composition API
const route = useRoute()
console.log(route)

// 下面是导航菜单部分，添加智能体项
const mainList = [{
    name: '对话',
    path: '/chat',
    icon: MessageSquareMore,
    activeIcon: MessageSquareMore,
  }, {
    name: '智能体',
    path: '/agent',
    icon: Bot,
    activeIcon: Bot,
  }, {
    name: '图谱',
    path: '/graph',
    icon: Waypoints,
    activeIcon: Waypoints,
    // hidden: !configStore.config.enable_knowledge_graph,
  }, {
    name: '知识库',
    path: '/database',
    icon: LibraryBig,
    activeIcon: LibraryBig,
    // hidden: !configStore.config.enable_knowledge_base,
  }
]
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
        <!-- 使用mainList渲染导航项 -->
        <RouterLink
          v-for="(item, index) in mainList"
          :key="index"
          :to="item.path"
          v-show="!item.hidden"
          class="nav-item"
          active-class="active">
          <component class="icon" :is="route.path.startsWith(item.path) ? item.activeIcon : item.icon" size="22"/>
          <span class="text">{{item.name}}</span>
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
        <a-tooltip placement="right">
          <template #title>欢迎 Star</template>
          <a href="https://github.com/xerrors/Yuxi-Know" target="_blank" class="github-link">
            <GithubOutlined class="icon" style="color: #222;"/>
            <span v-if="githubStars > 0" class="github-stars">
              <span class="star-count">{{ (githubStars / 1000).toFixed(1) }}k</span>
            </span>
          </a>
        </a-tooltip>
      </div>
      <!-- <div class="nav-item api-docs">
        <a-tooltip placement="right">
          <template #title>接口文档 {{ apiDocsUrl }}</template>
          <a :href="apiDocsUrl" target="_blank" class="github-link">
            <ApiOutlined class="icon" style="color: #222;"/>
          </a>
        </a-tooltip>
      </div> -->

      <!-- 用户信息组件 -->
      <div class="nav-item user-info">
        <a-tooltip placement="right">
          <template #title>用户信息</template>
          <UserInfoComponent />
        </a-tooltip>
      </div>

      <RouterLink class="nav-item setting" to="/setting" active-class="active">
        <a-tooltip placement="right">
          <template #title>设置</template>
          <Settings />
        </a-tooltip>
      </RouterLink>
    </div>
    <div class="header-mobile">
      <RouterLink to="/chat" class="nav-item" active-class="active">对话</RouterLink>
      <RouterLink to="/database" class="nav-item" active-class="active">知识</RouterLink>
      <RouterLink to="/setting" class="nav-item" active-class="active">设置</RouterLink>
    </div>
    <router-view v-slot="{ Component, route }" id="app-router-view">
      <keep-alive v-if="route.meta.keepAlive !== false">
        <component :is="Component" />
      </keep-alive>
      <component :is="Component" v-else />
    </router-view>
  </div>
</template>

<style lang="less" scoped>
@import '@/assets/main.css';

:root {
  --header-width: 60px;
}

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
  flex: 0 0 var(--header-width);
  justify-content: flex-start;
  align-items: center;
  background-color: var(--gray-100);
  height: 100%;
  width: var(--header-width);
  border-right: 1px solid var(--gray-300);

  .logo {
    width: 40px;
    height: 40px;
    margin: 14px 0 14px 0;

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
    margin: 0;
    text-decoration: none;
    cursor: pointer;

    &.github {
      padding: 10px 12px;
      &:hover {
        background-color: transparent;
        border: 1px solid transparent;
      }

      .github-link {
        display: flex;
        flex-direction: column;
        align-items: center;
        color: inherit;
      }

      .github-stars {
        display: flex;
        align-items: center;
        font-size: 12px;
        margin-top: 4px;

        .star-icon {
          color: #f0a742;
          font-size: 12px;
          margin-right: 2px;
        }

        .star-count {
          font-weight: 600;
        }
      }
    }

    &.api-docs {
      padding: 10px 12px;
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
    margin-bottom: 8px;
    padding: 16px 12px;

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

    .debug-panel {
      bottom: 10rem;
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
    height: 40px;

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
      border: none;
      outline: none;

      &:focus, &:active {
        border: none;
        outline: none;
      }
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
        align-items: center;
      }

      .github-stars {
        display: flex;
        align-items: center;
        margin-left: 6px;

        .star-icon {
          color: #f0a742;
          font-size: 14px;
          margin-right: 2px;
        }
      }
    }
  }
}
</style>