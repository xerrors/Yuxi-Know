<script setup>
import { KeepAlive } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  MessageOutlined,
  MessageFilled,
  SettingOutlined,
  SettingFilled,
  BookOutlined,
  BookFilled
} from '@ant-design/icons-vue'

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
          <component :is="route.path === '/chat' ? MessageFilled : MessageOutlined" />
        </RouterLink>
        <RouterLink to="/knowledge" class="nav-item" active-class="active">
          <component :is="route.path === '/knowledge' ? BookFilled : BookOutlined" />
        </RouterLink>
      </div>
      <div class="fill" style="flex-grow: 1;"></div>
      <RouterLink to="/setting" class="setting" active-class="active">
        <component :is="route.path === '/setting' ? SettingFilled : SettingOutlined" />
      </RouterLink>
    </div>
    <router-view v-slot="{ Component }" id="app-router-view">
      <keep-alive>
        <component :is="Component" />
      </keep-alive>
    </router-view>
  </div>
</template>

<style lang="less" scoped>
@import '@/assets/main.css';

.app-layout {
  display: flex;
  flex-direction: row;
  align-items: center;
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
  background-color: #F9F9F9;
  height: 100%;
  width: 80px;

  & .logo {
    width: 50px;
    height: 50px;
    margin: 20px 0;

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

.header .nav .nav-item {
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
    color: var(--main-color);
    background-color: #e2eef3;
  }

  &:hover {
    background-color: #e2eef3;
    cursor: pointer;
  }
}

.header .setting {
  font-size: 20px;
  color: #333;
  margin: 20px 0;

  &:hover {
    cursor: pointer;
  }
}

@media (max-width: 768px) {
  .app-layout {
    flex-direction: column;
  }

  .app-layout div.header {
    flex-direction: row;
    width: 100%;
    height: 60px;
    padding: 0 20px;
    justify-content: space-between;
    align-items: center;
  }

  .app-layout .nav {
    flex-direction: row;
    height: 100%;
    width: 100%;
    justify-content: center;
    gap: 0;

    .nav-item:hover {
      background-color: transparent;
    }

    .nav-item.active {
      background-color: transparent;
    }
  }
}
</style>
