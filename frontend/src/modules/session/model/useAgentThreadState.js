import { createItemState } from './agentItems.js'

const createOngoingRunGroupState = () => ({ ...createItemState(), optimisticMessages: {} })

const IDLE_QUEUE_SNAPSHOT = Object.freeze({
  status: 'ready',
  queue_paused: false
})

export function useAgentThreadState({
  chatState,
  onBeforeResetThread = null,
  onBeforeCleanupThread = null
}) {
  const resetThreadUiState = (threadState) => {
    if (!threadState) return
    threadState.replyLoadingVisible = false
    threadState.pendingInputId = null
  }

  const getThreadState = (threadId) => {
    if (!threadId) return null
    if (!chatState.threadStates[threadId]) {
      chatState.threadStates[threadId] = {
        displayText: {},
        isStreaming: false,
        runStreamAbortController: null,
        runReconnectTimer: null,
        runReconnectAttempts: 0,
        activeRunId: null,
        currentTurnId: null,
        turnStatus: null,
        activeRunSteerable: false,
        threadCursor: null,
        replyLoadingVisible: false,
        pendingInputId: null,
        pendingInterrupt: null,
        agentStateRequestVersion: 0,
        ongoingRunGroup: createOngoingRunGroupState(),
        agentState: null,
        contextCompressing: false,
        queuedInputs: [],
        queueSnapshot: { ...IDLE_QUEUE_SNAPSHOT },
        continueQueueInFlight: false,
        inputQueueMonitor: null
      }
    }
    return chatState.threadStates[threadId]
  }

  const abortAllInputMonitors = (threadState) => {
    if (!threadState) return
    clearTimeout(threadState.inputQueueMonitor?.timer)
    threadState.inputQueueMonitor?.controller?.abort()
    threadState.inputQueueMonitor = null
  }

  const cleanupThreadState = (threadId) => {
    if (!threadId) return
    const threadState = chatState.threadStates[threadId]
    if (!threadState) return

    if (typeof onBeforeCleanupThread === 'function') {
      onBeforeCleanupThread(threadId)
    }

    if (threadState.runStreamAbortController) {
      threadState.runStreamAbortController.abort()
    }
    clearTimeout(threadState.runReconnectTimer)
    abortAllInputMonitors(threadState)
    delete chatState.threadStates[threadId]
  }

  const resetOngoingRunGroup = (threadId, { preserveInputMonitors = false } = {}) => {
    if (threadId) {
      const threadState = getThreadState(threadId)
      if (!threadState) return

      if (typeof onBeforeResetThread === 'function') {
        onBeforeResetThread(threadId)
      }

      if (threadState.runStreamAbortController) {
        threadState.runStreamAbortController.abort()
        threadState.runStreamAbortController = null
      }
      clearTimeout(threadState.runReconnectTimer)
      threadState.runReconnectTimer = null
      if (!preserveInputMonitors) {
        abortAllInputMonitors(threadState)
      }

      threadState.ongoingRunGroup = createOngoingRunGroupState()
      resetThreadUiState(threadState)
      return
    }

    Object.keys(chatState.threadStates).forEach((id) => {
      cleanupThreadState(id)
    })
  }

  return {
    getThreadState,
    cleanupThreadState,
    resetOngoingRunGroup
  }
}

export { IDLE_QUEUE_SNAPSHOT }
