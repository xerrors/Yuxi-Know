<template>
  <a-modal
    v-model:open="visible"
    title="系统设置"
    width="90%"
    :style="{ maxWidth: '1200px', minWidth: '320px', top: '3%' }"
    :footer="null"
    @cancel="handleClose"
    class="settings-modal"
    :destroyOnClose="true"
    :bodyStyle="{ padding: 0 }"
  >
    <div class="settings-container">
      <!-- 侧边栏 (Desktop) -->
      <div class="settings-sider" v-if="!isMobile">
        <div
          class="sider-item"
          :class="{ activesec: activeTab === 'base' }"
          @click="activeTab = 'base'"
          v-if="userStore.isSuperAdmin"
        >
          <SettingOutlined class="icon" />
          <span>基本设置</span>
        </div>
        <div
          class="sider-item"
          :class="{ activesec: activeTab === 'model' }"
          @click="activeTab = 'model'"
          v-if="userStore.isSuperAdmin"
        >
          <CodeOutlined class="icon" />
          <span>模型配置</span>
        </div>
        <div
          class="sider-item"
          :class="{ activesec: activeTab === 'user' }"
          @click="activeTab = 'user'"
          v-if="userStore.isAdmin"
        >
          <UserOutlined class="icon" />
          <span>用户管理</span>
        </div>
      </div>

      <!-- 顶部导航 (Mobile) -->
      <div class="settings-mobile-nav" v-else>
        <div
          class="nav-item"
          :class="{ active: activeTab === 'base' }"
          @click="activeTab = 'base'"
          v-if="userStore.isSuperAdmin"
        >
          基本设置
        </div>
        <div
          class="nav-item"
          :class="{ active: activeTab === 'model' }"
          @click="activeTab = 'model'"
          v-if="userStore.isSuperAdmin"
        >
          模型配置
        </div>
        <div
          class="nav-item"
          :class="{ active: activeTab === 'user' }"
          @click="activeTab = 'user'"
          v-if="userStore.isAdmin"
        >
          用户管理
        </div>
      </div>

      <!-- 内容区域 -->
      <div class="settings-content-wrapper">
        <div class="settings-content">
          <div v-show="activeTab === 'base'" v-if="userStore.isSuperAdmin">
            <BasicSettingsSection />
          </div>

          <div v-show="activeTab === 'model'" v-if="userStore.isSuperAdmin">
            <ModelProvidersComponent />
          </div>

          <div v-show="activeTab === 'user'" v-if="userStore.isAdmin">
            <UserManagementComponent />
          </div>
        </div>
      </div>
    </div>
  </a-modal>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useUserStore } from '@/stores/user'
import {
  SettingOutlined,
  CodeOutlined,
  UserOutlined
} from '@ant-design/icons-vue'
import BasicSettingsSection from '@/components/BasicSettingsSection.vue'
import ModelProvidersComponent from '@/components/ModelProvidersComponent.vue'
import UserManagementComponent from '@/components/UserManagementComponent.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'close'])

const userStore = useUserStore()
const activeTab = ref('base')
const windowWidth = ref(window?.innerWidth || 0)

const isMobile = computed(() => windowWidth.value <= 768)

const visible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value)
})

const handleClose = () => {
  emit('close')
}

const updateWindowWidth = () => {
  windowWidth.value = window?.innerWidth || 0
}

onMounted(() => {
  window.addEventListener('resize', updateWindowWidth)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateWindowWidth)
})

// 根据用户权限设置默认标签页
watch(() => props.visible, (newVal) => {
  if (newVal) {
    if (userStore.isSuperAdmin) {
      activeTab.value = 'base'
    } else if (userStore.isAdmin) {
      activeTab.value = 'user'
    }
  }
})
</script>

<style lang="less">
.settings-modal {
  :deep(.ant-modal-header) {
    padding: 16px 24px;
    border-bottom: 1px solid var(--gray-150);

    .ant-modal-title {
      font-size: 18px;
      font-weight: 600;
      color: var(--gray-900);
    }
  }

  :deep(.ant-modal-content) {
    border-radius: 8px;
    display: flex;
    flex-direction: column;
  }
}

.settings-container {
  display: flex;
  height: 100%;
  width: 100%;
}

/* Sidebar Styles - Matching SettingView.vue style */
.settings-sider {
  width: 140px;
  height: 100%;
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;

  .sider-item {
    width: 100%;
    padding: 6px 16px; /* Matches SettingView .sider > * */
    cursor: pointer;
    transition: all 0.1s; /* Matches SettingView */
    text-align: left;
    font-size: 15px; /* Matches SettingView */
    border-radius: 8px;
    color: var(--gray-700);
    display: flex;
    align-items: center;
    gap: 10px;

    .icon {
      font-size: 14px; /* Slightly adjusted to align better, SettingView uses h() icon defaults */
    }

    &:hover {
      background: var(--gray-50);
    }

    &.activesec {
      background: var(--gray-100);
      color: var(--main-700);
    }
  }
}

/* Content Area */
.settings-content-wrapper {
  flex: 1;
  height: 100%;
  /* background-color: #fff; SettingView seems to use default background */

  .settings-content {
    padding: 0 20px; /* Matches SettingView .setting padding */
    // margin-bottom: 40px; /* Matches SettingView .setting margin-bottom */
    overflow-y: scroll;
    height: 80vh;

    h3 {
      font-size: 18px;
      font-weight: 600;
      color: var(--gray-900);
      margin-bottom: 0.5em;
    }

    /* BasicSettingsSection has its own h3 styles which might conflict slightly but are mostly self-contained */
  }
}

/* Mobile Styles */
.settings-mobile-nav {
  display: flex;
  overflow-x: auto;
  border-bottom: 1px solid var(--gray-150);
  background: var(--gray-0);
  padding: 0 16px;
  flex-shrink: 0;

  .nav-item {
    padding: 12px 16px;
    white-space: nowrap;
    cursor: pointer;
    color: var(--gray-600);
    font-weight: 500;
    border-bottom: 2px solid transparent;
    transition: all 0.2s;

    &.active {
      color: var(--main-color);
      border-bottom-color: var(--main-color);
    }
  }
}
</style>