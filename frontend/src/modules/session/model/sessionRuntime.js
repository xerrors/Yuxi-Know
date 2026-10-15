import { reactive, ref, onScopeDispose } from 'vue'
import { defineStore } from 'pinia'
import { agentApi } from '@/apis'
import { handleChatError } from '@/shared/lib/errorHandler'
import { useChatThreadsStore } from './chatThreads'
import { useAgentThreadState } from './useAgentThreadState'
import { useAgentRunStream } from './useAgentRunStream'
import { useAgentInputQueue } from './useAgentInputQueue'
import { useAgentStreamHandler } from './useAgentStreamHandler'
import { useStreamSmoother } from './useStreamSmoother'
import { createItemState, itemsToMessages, mergeItemSnapshot, syncHistoricalItemEvent } from './agentItems'
import { bindMessageInputRun } from './messageDebug'
import { extractPendingInterrupt, pendingInterruptFromWaitpoint } from './useApproval'
import { useSessionFeedbackStore } from './sessionFeedback'

/** 每个 Thread 共享运行数据和订阅，视图仅注册展示回调。 */
export const useSessionRuntimeStore = defineStore('sessionRuntime', () => {
  const chatThreads = useChatThreadsStore()
  const feedback = useSessionFeedbackStore()
  const chatState = reactive({ threadStates: {} })
  const threadMessages = ref({})
  const threadRuns = ref({})
  const historyPages = reactive({})
  const pendingSends = reactive({})
  const historyItems = new Map()
  const observers = new Map()
  const requests = new Map()
  const streamSmoother = useStreamSmoother({
    getThreadState: (id) => chatState.threadStates[id] || null
  })
  const { getThreadState, cleanupThreadState, resetOngoingRunGroup } = useAgentThreadState({
    chatState,
    onBeforeResetThread: streamSmoother.resetThread,
    onBeforeCleanupThread: streamSmoother.resetThread
  })

  /** 同一类在途读取共用 Promise，释放视图后旧结果不能写回新状态。 */
  const once = (key, action) => {
    if (requests.has(key)) return requests.get(key)
    const request = Promise.resolve()
      .then(action)
      .finally(() => {
        if (requests.get(key) === request) requests.delete(key)
      })
    requests.set(key, request)
    return request
  }
  const notify = (name, payload) => {
    for (const observer of observers.get(payload.threadId) || []) observer[name]?.(payload)
  }
  const isCurrent = (threadId, state) => chatState.threadStates[threadId] === state

  const fetchThreadMessages = async ({ threadId, fresh = false, more = false, turnId = null }) => {
    if (!threadId || !observers.has(threadId)) return
    const state = getThreadState(threadId)
    if (fresh && requests.has(`history:${threadId}`)) {
      // 终态必须读取发生在完成事件之后的快照，不能共用更早的在途历史。
      try {
        await requests.get(`history:${threadId}`)
      } catch {
        /* 新请求负责重试。 */
      }
      if (!observers.has(threadId) || !isCurrent(threadId, state)) return
    }
    return once(`history:${threadId}`, async () => {
      if (!observers.has(threadId)) return
      const state = getThreadState(threadId)
      try {
        const projection = historyItems.get(threadId) || createItemState()
        const previousIds = new Set(Object.keys(projection.items))
        const paging = historyPages[threadId] ||= { after: null, hasMore: false, loading: false }
        paging.loading = true
        let after = more ? paging.after : undefined
        let pagesRead = 0
        const [session, initialPage] = await Promise.all([
          agentApi.getPublicThread(threadId),
          agentApi.getSessionItems(threadId, { after, turnId, limit: 100 })
        ])
        if (!isCurrent(threadId, state)) return
        let page = initialPage
        const runs = new Map((threadRuns.value[threadId] || []).map((run) => [run.id, run]))
        while (true) {
          if (!isCurrent(threadId, state)) return
          mergeItemSnapshot(projection, page.data)
          mergeItemSnapshot(state.ongoingRunGroup, page.data)
          for (const run of page.yuxi.runs) runs.set(run.id, run)
          after = page.last_id
          pagesRead++
          // 恢复目标轮次读取完整页；Session 刷新读到已加载区域即可。
          const recoverGap = !more && previousIds.size && !page.data.some((item) => previousIds.has(item.id))
          if (!page.has_more || (!turnId && !recoverGap && pagesRead >= 3)) break
          page = await agentApi.getSessionItems(threadId, { after, turnId, limit: 100 })
        }
        const target = turnId || session.yuxi.current_turn?.id
        if (target && !more) {
          const turn = await agentApi.getThreadTurn(threadId, target)
          if (!isCurrent(threadId, state)) return
          mergeItemSnapshot(projection, turn.yuxi.output)
          mergeItemSnapshot(state.ongoingRunGroup, turn.yuxi.output)
          for (const run of turn.yuxi.runs || []) runs.set(run.id, run)
        }
        if (!turnId && (more || !paging.after || !page.has_more)) {
          paging.after = page.last_id
          paging.hasMore = page.has_more
        }
        historyItems.set(threadId, projection)
        streamSmoother.flushThread(threadId)
        threadMessages.value[threadId] = itemsToMessages(Object.values(projection.items))
        void feedback.load(threadId, threadMessages.value[threadId]
          .filter((message) => message.phase === 'final_answer' && message.execution_status === 'completed')
          .map((message) => message.run_id), fresh)
        threadRuns.value[threadId] = [...runs.values()]
        if (!state.isStreaming) state.turnStatus = session.yuxi.current_turn?.status || null
        chatThreads.upsertThread(session)
      } catch (error) {
        handleChatError(error, 'load')
        throw error
      } finally {
        if (isCurrent(threadId, state) && historyPages[threadId]) historyPages[threadId].loading = false
      }
    })
  }

  const fetchAgentState = async (_agentId, threadId, { required = false } = {}) => {
    const success = await once(`state:${threadId}`, async () => {
      if (!threadId) return false
      const state = getThreadState(threadId)
      const runVersion = state.runStateVersion
      const version = (state.agentStateRequestVersion || 0) + 1
      state.agentStateRequestVersion = version
      try {
        const response = await agentApi.getAgentState(threadId, { includeRelations: false })
        if (
          !isCurrent(threadId, state) ||
          state.agentStateRequestVersion !== version ||
          state.runStateVersion !== runVersion
        )
          return false
        state.agentState = response.agent_state || null
        const interrupt = extractPendingInterrupt(response.interrupt, threadId)
        if (
          interrupt &&
          !state.isStreaming &&
          (!interrupt.interruptedRunId ||
            !state.activeRunId ||
            interrupt.interruptedRunId === state.activeRunId)
        ) {
          state.pendingInterrupt = interrupt
          notify('onInterruptDetected', { threadId })
        }
        return true
      } catch (error) {
        if (required) throw error
        return false
      }
    })
    if (required && (!success || !getThreadState(threadId)?.pendingInterrupt)) {
      throw new Error('checkpoint 中没有可恢复的审批状态')
    }
    return success
  }

  const { handlePublicEvent } = useAgentStreamHandler({
    getThreadState,
    streamSmoother,
    processApprovalInStream: (event, threadId) => {
      const state = getThreadState(threadId)
      state.pendingInterrupt = pendingInterruptFromWaitpoint(event.waitpoint, threadId)
      notify('onInterruptDetected', { threadId })
      return Boolean(state.pendingInterrupt)
    }
  })
  const stream = useAgentRunStream({
    getThreadState,
    isThreadActive: (threadId) => observers.has(threadId),
    handlePublicEvent: (event, threadId) => {
      const result = handlePublicEvent(event, threadId)
      const history = historyItems.get(threadId)
      if (history && syncHistoricalItemEvent(history, event)) {
        threadMessages.value[threadId] = itemsToMessages(Object.values(history.items))
      }
      if (event.turn && event.session_id === threadId) {
        chatThreads.upsertThread({ id: threadId, status: event.turn.status === 'queued' ? 'in_progress' : event.turn.status })
      }
      return result
    },
    fetchThreadMessages,
    fetchAgentState,
    resetOngoingRunGroup,
    streamSmoother,
    onScrollToBottom: (threadId) => notify('onScrollToBottom', { threadId }),
    onInterruptDetected: ({ threadId, turn }) => {
      void (async () => {
        const state = getThreadState(threadId)
        const turnId = state.currentTurnId
        const version = state.runStateVersion
        const waiting = turn || (turnId && (await agentApi.getThreadTurn(threadId, turnId)))
        if (
          !isCurrent(threadId, state) ||
          state.currentTurnId !== turnId ||
          state.runStateVersion !== version ||
          waiting?.status !== 'requires_action'
        )
          return
        state.pendingInterrupt = pendingInterruptFromWaitpoint(waiting.yuxi.waitpoint, threadId)
        notify('onInterruptDetected', { threadId })
      })().catch((error) => console.warn('Failed to restore Turn waitpoint:', error))
      void resumeQueuedInputs(threadId)
    },
    onTerminalDetected: (payload) => {
      void resumeQueuedInputs(payload.threadId)
      notify('onTerminalDetected', payload)
    },
    onRunStarted: ({ threadId, runId, inputId }) => {
      const chunks = getThreadState(threadId)?.ongoingRunGroup?.optimisticMessages || {}
      bindMessageInputRun(Object.values(chunks).flat(), inputId, runId)
      bindMessageInputRun(threadMessages.value[threadId], inputId, runId)
      chatThreads.upsertThread({ id: threadId, status: 'in_progress' })
    }
  })
  const queue = useAgentInputQueue({
    getThreadState,
    isThreadActive: (threadId) => observers.has(threadId),
    resetOngoingRunGroup,
    startRunStream: stream.startRunStream
  })
  const resumeQueuedInputs = (threadId) =>
    once(`queue:${threadId}`, () => queue.resumeQueuedInputs(threadId))
  const resumeActiveRunForThread = (threadId) =>
    once(`resume:${threadId}`, () => stream.resumeActiveRunForThread(threadId))

  /** 最后一个视图释放时才终止观察；隐藏视图仍保有运行状态。 */
  const observeThread = (threadId, observer) => {
    if (!threadId) return () => {}
    if (!observers.has(threadId)) observers.set(threadId, new Set())
    const listeners = observers.get(threadId)
    listeners.add(observer)
    getThreadState(threadId)
    return () => {
      listeners.delete(observer)
      if (listeners.size || observers.get(threadId) !== listeners) return
      observers.delete(threadId)
      cleanupThreadState(threadId)
      delete threadMessages.value[threadId]
      delete threadRuns.value[threadId]
      delete historyPages[threadId]
      historyItems.delete(threadId)
      for (const key of requests.keys()) {
        if (key.endsWith(`:${threadId}`)) requests.delete(key)
      }
    }
  }
  onScopeDispose(() => {
    for (const id of Object.keys(chatState.threadStates)) cleanupThreadState(id)
    observers.clear()
    requests.clear()
  })
  return {
    threadMessages,
    threadRuns,
    historyPages,
    pendingSends,
    getThreadState,
    resetOngoingRunGroup,
    fetchThreadMessages,
    fetchAgentState,
    observeThread,
    startRunStream: stream.startRunStream,
    resumeActiveRunForThread,
    resumeQueuedInputs,
    startInputMonitor: queue.startInputMonitor,
    cancelInput: queue.cancelInput,
    promoteInput: queue.promoteInput,
    continueQueue: queue.continueQueue
  }
})
