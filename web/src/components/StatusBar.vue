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
        <div class="task-center-entry" @click="openTaskCenter">
          <a-badge :count="activeTaskCount" :overflow-count="99" class="task-center-badge">
            <span class="task-center-button">
              <ClipboardList class="icon" />
              <span class="task-center-label">任务中心</span>
            </span>
          </a-badge>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useInfoStore } from '@/stores/info'
import { useUserStore } from '@/stores/user'
import { Clock, User, ClipboardList } from 'lucide-vue-next'
import { useTaskerStore } from '@/stores/tasker'
import { storeToRefs } from 'pinia'
import dayjs from '@/utils/time'

// 使用 stores
const infoStore = useInfoStore()
const userStore = useUserStore()
const taskerStore = useTaskerStore()
const { activeCount: activeCountRef } = storeToRefs(taskerStore)

// 响应式数据
const currentTime = ref('')

// 计算属性
const organization = computed(() => infoStore.organization)
const branding = computed(() => infoStore.branding)

// 用户名计算属性
const currentUser = computed(() => {
  return userStore.username || '游客'
})

// 问候语计算属性
const greeting = computed(() => {
  const hour = dayjs().tz('Asia/Shanghai').hour()
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

const activeTaskCount = computed(() => activeCountRef.value || 0)

const openTaskCenter = () => {
  taskerStore.openDrawer()
}

// 更新时间
const updateTime = () => {
  const now = dayjs().tz('Asia/Shanghai')
  currentTime.value = now.format('YYYY年MM月DD日 HH:mm:ss')
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
  // background: var(--gray-0);
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
    color: var(--gray-900, #111827);
    line-height: 1.4;
  }

  .system-subtitle {
    font-size: 13px;
    color: var(--gray-600, #6b7280);
    line-height: 1.2;
  }
}

.status-right {
  display: flex;
  align-items: center;
  gap: 18px;
  font-size: 13px;
}

.task-center-entry {
  display: flex;
  align-items: center;
  cursor: pointer;
  user-select: none;
}

.task-center-badge {
  display: flex;
  align-items: center;
}

.task-center-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 999px;
  background-color: transparent;
  color: var(--main-600, #2563eb);
  font-size: 13px;
  font-weight: 500;
  border: 1px solid rgba(37, 99, 235, 0.3);
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease;
}

.task-center-button .icon {
  width: 15px;
  height: 15px;
  color: inherit;
}

.task-center-label {
  letter-spacing: 0.2px;
}

.task-center-entry:hover .task-center-button {
  background-color: rgba(37, 99, 235, 0.08);
  color: var(--main-700, #1d4ed8);
  border-color: rgba(37, 99, 235, 0.5);
}

.task-center-badge :deep(.ant-badge-count) {
  background-color: var(--main-color, #1d4ed8);
}

.time-info,
.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  line-height: 1.3;
  color: var(--gray-600, #4b5563);

  .icon {
    width: 15px;
    height: 15px;
    color: var(--gray-600, #6b7280);
  }
}

.current-time,
.user-greeting {
  font-weight: 500;
  color: var(--gray-900, #111827);
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
