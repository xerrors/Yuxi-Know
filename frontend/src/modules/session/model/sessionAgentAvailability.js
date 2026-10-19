import { computed, ref } from 'vue'

/** 详情可执行性独立于历史读取，过期请求不能覆盖当前对话。 */
export function useSessionAgentAvailability(currentThreadId, loadAgent) {
  const state = ref({ threadId: null, status: 'loading' })
  let requestVersion = 0
  const status = computed(() => state.value.threadId === currentThreadId.value ? state.value.status : 'loading')

  async function refresh(threadId, agentId) {
    const version = ++requestVersion
    state.value = { threadId, status: 'loading' }
    let next
    try {
      const agent = await loadAgent(agentId)
      next = agent && agent.can_run !== false ? 'ready' : 'unavailable'
    } catch (error) {
      next = [403, 404].includes(error.status) ? 'unavailable' : 'error'
    }
    if (version === requestVersion && currentThreadId.value === threadId) {
      state.value = { threadId, status: next }
    }
  }

  return { status, refresh }
}
