<template>
  <div class="user-info-component">
    <a-dropdown :trigger="['click']" v-if="userStore.isLoggedIn">
      <div class="user-info-dropdown" :data-align="showRole ? 'left' : 'center'">
        <div class="user-avatar">
          <CircleUser />
          <!-- <div class="user-role-badge" :class="userRoleClass"></div> -->
        </div>
        <div v-if="showRole">{{ userStore.username }}</div>
      </div>
      <template #overlay>
          <a-menu>
          <a-menu-item key="username" disabled>
            <span class="user-menu-username">{{ userStore.username }}</span>
          </a-menu-item>
          <a-menu-item key="role" disabled>
            <span class="user-menu-role">{{ userRoleText }}</span>
          </a-menu-item>
          <a-menu-divider />
          <a-menu-item key="logout" @click="logout">
            <LogoutOutlined /> &nbsp;退出登录
          </a-menu-item>
        </a-menu>
      </template>
    </a-dropdown>
    <a-button v-else type="link" @click="goToLogin">
      <UserRoundCheck /> 登录
    </a-button>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useUserStore } from '@/stores/user';
import { UserOutlined, LogoutOutlined } from '@ant-design/icons-vue';
import { message } from 'ant-design-vue';
import { CircleUser, UserRoundCheck } from 'lucide-vue-next';

const router = useRouter();
const userStore = useUserStore();

const props = defineProps({
  showRole: {
    type: Boolean,
    default: false
  }
})

// 用户名首字母（用于显示在头像中）
const userInitial = computed(() => {
  if (!userStore.username) return '?';
  return userStore.username.charAt(0).toUpperCase();
});

// 用户角色显示文本
const userRoleText = computed(() => {
  switch (userStore.userRole) {
    case 'superadmin':
      return '超级管理员';
    case 'admin':
      return '管理员';
    case 'user':
      return '普通用户';
    default:
      return '未知角色';
  }
});

// 用户角色徽章样式类
const userRoleClass = computed(() => {
  return {
    'superadmin': userStore.userRole === 'superadmin',
    'admin': userStore.userRole === 'admin',
    'user': userStore.userRole === 'user'
  };
});

// 退出登录
const logout = () => {
  userStore.logout();
  message.success('已退出登录');
  // 跳转到首页
  router.push('/login');
};

// 前往登录页
const goToLogin = () => {
  router.push('/login');
};
</script>

<style lang="less" scoped>
.user-info-component {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--gray-800);
  // margin-bottom: 16px;
}

.user-info-dropdown {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;

  &[data-align="center"] {
    justify-content: center;
  }

  &[data-align="left"] {
    justify-content: flex-start;
  }
}

.user-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 18px;
  cursor: pointer;
  position: relative;

  &:hover {
    opacity: 0.9;
  }
}

.user-role-badge {
  position: absolute;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  right: 0;
  bottom: 0;
  border: 2px solid white;

  &.superadmin {
    background-color: #c1bd00; // 红色，超管
  }

  &.admin {
    background-color: #1890ff; // 蓝色，管理员
  }

  &.user {
    background-color: #52c41a; // 绿色，普通用户
  }
}

.user-menu-username {
  font-weight: bold;
}

.user-menu-role {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}
</style>