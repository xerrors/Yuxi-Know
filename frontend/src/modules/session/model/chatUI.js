import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useChatUIStore = defineStore(
  'chatUI',
  () => {
    // ==================== 聊天界面 UI 状态 ====================
    // 加载状态
    const isLoadingMessages = ref(false)

    // 应用侧边栏折叠态
    const sidebarCollapsed = ref(false)

    /**
     * 重置所有 UI 状态（不包括持久化状态）
     */
    function reset() {
      isLoadingMessages.value = false
    }

    return {
      // 状态
      isLoadingMessages,
      sidebarCollapsed,

      // 方法
      reset
    }
  },
  {
    persist: {
      key: 'chat-ui-store',
      storage: typeof localStorage === 'undefined' ? undefined : localStorage,
      pick: ['sidebarCollapsed']
    }
  }
)
