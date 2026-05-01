import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { threadApi } from '@/apis'
import { handleChatError } from '@/utils/errorHandler'

const PAGE_SIZE = 100

export const useChatThreadsStore = defineStore('chatThreads', () => {
  const threads = ref([])
  const currentThreadId = ref(null)
  const hasMoreThreads = ref(true)
  const isLoadingThreads = ref(false)
  const isLoadingMoreThreads = ref(false)
  const isCreatingThread = ref(false)
  const isDeletingThread = ref(false)
  const isRenamingThread = ref(false)

  const currentThread = computed(() => {
    if (!currentThreadId.value) return null
    return threads.value.find((thread) => thread.id === currentThreadId.value) || null
  })

  const setCurrentThreadId = (threadId) => {
    currentThreadId.value = threadId || null
  }

  const clearThreads = () => {
    threads.value = []
    currentThreadId.value = null
    hasMoreThreads.value = true
  }

  const loadThreads = async (agentId = null) => {
    isLoadingThreads.value = true
    try {
      const fetchedThreads = await threadApi.getThreads(agentId, PAGE_SIZE, 0)
      threads.value = fetchedThreads || []
      hasMoreThreads.value = Boolean(fetchedThreads && fetchedThreads.length >= PAGE_SIZE)
      if (
        currentThreadId.value &&
        !threads.value.find((thread) => thread.id === currentThreadId.value)
      ) {
        currentThreadId.value = null
      }
      return threads.value
    } catch (error) {
      console.error('Failed to fetch threads:', error)
      handleChatError(error, 'fetch')
      throw error
    } finally {
      isLoadingThreads.value = false
    }
  }

  const loadMoreThreads = async (agentId = null) => {
    if (isLoadingMoreThreads.value || !hasMoreThreads.value) return

    isLoadingMoreThreads.value = true
    try {
      const fetchedThreads = await threadApi.getThreads(agentId, PAGE_SIZE, threads.value.length)
      if (fetchedThreads && fetchedThreads.length > 0) {
        // 后端分页会重复返回置顶项，这里只追加列表中尚不存在的线程。
        const existingIds = new Set(threads.value.map((thread) => thread.id))
        const newThreads = fetchedThreads.filter((thread) => !existingIds.has(thread.id))
        threads.value = [...threads.value, ...newThreads]
        hasMoreThreads.value = newThreads.length >= PAGE_SIZE
      } else {
        hasMoreThreads.value = false
      }
    } catch (error) {
      console.error('Failed to load more chats:', error)
      handleChatError(error, 'fetch')
    } finally {
      isLoadingMoreThreads.value = false
    }
  }

  const createThread = async (agentId, title = '新的对话') => {
    if (!agentId) return null

    isCreatingThread.value = true
    try {
      const thread = await threadApi.createThread(agentId, title)
      if (thread) {
        threads.value = [thread, ...threads.value.filter((item) => item.id !== thread.id)]
      }
      return thread
    } catch (error) {
      console.error('Failed to create thread:', error)
      handleChatError(error, 'create')
      throw error
    } finally {
      isCreatingThread.value = false
    }
  }

  const deleteThread = async (threadId) => {
    if (!threadId) return

    isDeletingThread.value = true
    try {
      await threadApi.deleteThread(threadId)
      threads.value = threads.value.filter((thread) => thread.id !== threadId)
      if (currentThreadId.value === threadId) {
        currentThreadId.value = null
      }
    } catch (error) {
      console.error('Failed to delete thread:', error)
      handleChatError(error, 'delete')
      throw error
    } finally {
      isDeletingThread.value = false
    }
  }

  const updateThread = async (threadId, title, isPinned) => {
    if (!threadId) return

    if (title) {
      const normalizedTitle = String(title).replace(/\s+/g, ' ').trim().slice(0, 255)
      if (!normalizedTitle) return

      isRenamingThread.value = true
      try {
        await threadApi.updateThread(threadId, normalizedTitle, isPinned)
        const thread = threads.value.find((item) => item.id === threadId)
        if (thread) {
          thread.title = normalizedTitle
          if (isPinned !== undefined) {
            thread.is_pinned = isPinned
          }
        }
      } catch (error) {
        console.error('Failed to update thread:', error)
        handleChatError(error, 'update')
        throw error
      } finally {
        isRenamingThread.value = false
      }
      return
    }

    if (isPinned !== undefined) {
      try {
        await threadApi.updateThread(threadId, null, isPinned)
        const thread = threads.value.find((item) => item.id === threadId)
        if (thread) {
          thread.is_pinned = isPinned
        }
      } catch (error) {
        console.error('Failed to update thread pin status:', error)
        handleChatError(error, 'update')
        throw error
      }
    }
  }

  return {
    threads,
    currentThreadId,
    currentThread,
    hasMoreThreads,
    isLoadingThreads,
    isLoadingMoreThreads,
    isCreatingThread,
    isDeletingThread,
    isRenamingThread,
    setCurrentThreadId,
    clearThreads,
    loadThreads,
    loadMoreThreads,
    createThread,
    deleteThread,
    updateThread
  }
})
