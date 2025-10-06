<template>
  <div class="status-bar">
    <div class="status-bar-content">
      <!-- 左侧：系统信息 -->
      <div class="status-left">
        <div class="system-info">
          <div class="system-details">
            <div class="system-name">{{ branding.name }}</div>
            <div class="system-subtitle">{{ branding.subtitle }}</div>
          </div>
        </div>
      </div>

      <!-- 右侧：时间和用户信息 -->
      <div class="status-right">
        <div class="time-info">
          <Clock class="icon" />
          <span class="current-time">{{ currentTime }}</span>
        </div>
        <div class="user-info">
          <User class="icon" />
          <span class="user-greeting">{{ greeting }}</span>
        </div>
        <div class="status-indicator" :class="systemStatus">
          <div class="status-dot"></div>
          <span class="status-text">{{ statusText }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useInfoStore } from '@/stores/info'
import { useUserStore } from '@/stores/user'
import { Clock, User } from 'lucide-vue-next'

// 使用 stores
const infoStore = useInfoStore()
const userStore = useUserStore()

// 响应式数据
const currentTime = ref('')
const systemStatus = ref('online')

// 计算属性
const organization = computed(() => infoStore.organization)
const branding = computed(() => infoStore.branding)

// 用户名计算属性
const currentUser = computed(() => {
  return userStore.username || '游客'
})

// 问候语计算属性
const greeting = computed(() => {
  const hour = new Date().getHours()
  let greetingText = ''

  if (hour >= 5 && hour < 12) {
    greetingText = '早上好'
  } else if (hour >= 12 && hour < 14) {
    greetingText = '中午好'
  } else if (hour >= 14 && hour < 18) {
    greetingText = '下午好'
  } else if (hour >= 18 && hour < 22) {
    greetingText = '晚上好'
  } else {
    greetingText = '夜深了'
  }

  return `${greetingText}！${currentUser.value}`
})

const statusText = computed(() => {
  switch (systemStatus.value) {
    case 'online':
      return '在线'
    case 'offline':
      return '离线'
    case 'maintenance':
      return '维护中'
    default:
      return '未知'
  }
})

// 更新时间
const updateTime = () => {
  const now = new Date()
  currentTime.value = now.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// 定时器
let timeInterval = null

onMounted(async () => {
  updateTime()
  timeInterval = setInterval(updateTime, 1000)

  // 获取用户信息
  try {
    await userStore.getCurrentUser()
  } catch (error) {
    console.error('获取用户信息失败:', error)
  }
})

onUnmounted(() => {
  if (timeInterval) {
    clearInterval(timeInterval)
  }
})
</script>

<style scoped lang="less">
.status-bar {
  // background: white;
  // backdrop-filter: blur(10px);
  // height: 60px;
  display: flex;
  align-items: center;
  // position: sticky;
  top: 0;
  z-index: 100;
}

.status-bar-content {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  // padding-bottom: 0;
}

.status-left {
  display: flex;
  align-items: center;
}

.system-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.system-details {
  .system-name {
    font-size: 20px;
    font-weight: 600;
    color: #111827;
    line-height: 1.4;
  }

  .system-subtitle {
    font-size: 13px;
    color: #6b7280;
    line-height: 1.2;
  }
}

.status-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.time-info,
.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #6b7280;

  .icon {
    width: 14px;
    height: 14px;
  }
}

.current-time,
.user-greeting {
  font-weight: 500;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;

  &.online {
    background-color: #f0fdf4;
    color: #16a34a;

    .status-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background-color: #16a34a;
    }
  }

  &.offline {
    background-color: #fef2f2;
    color: #dc2626;

    .status-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background-color: #dc2626;
    }
  }

  &.maintenance {
    background-color: #fffbeb;
    color: #d97706;

    .status-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background-color: #d97706;
    }
  }
}

// 响应式设计
@media (max-width: 768px) {
  .status-bar {
    height: 44px;
  }

  .status-bar-content {
    padding: 0 16px;
  }

  .system-details {
    .system-name {
      font-size: 13px;
    }

    .system-subtitle {
      font-size: 10px;
    }
  }

  .status-right {
    gap: 12px;
  }

  .time-info,
  .user-info {
    font-size: 11px;

    .icon {
      width: 12px;
      height: 12px;
    }
  }

  .current-time {
    display: none; // 在小屏幕上隐藏时间
  }
}
</style>
