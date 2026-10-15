import { agentApi } from '@/apis'
import { handleChatError } from '@/shared/lib/errorHandler'
import { getReconnectDelay } from './reconnectBackoff.js'

export const processRunSseResponse = async (response, onEvent) => {
  if (!response || !response.body) return
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventType = 'message'
  let eventId = null
  let dataLines = []

  const dispatch = async () => {
    if (dataLines.length === 0) return
    const dataText = dataLines.join('\n')
    let parsed
    try {
      parsed = JSON.parse(dataText)
    } catch (e) {
      console.warn('Failed to parse run SSE data:', e, dataText)
      return
    }
    await onEvent(eventType, parsed, eventId)
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const rawLine of lines) {
        const line = rawLine.replace(/\r$/, '')
        if (!line) {
          await dispatch()
          eventType = 'message'
          eventId = null
          dataLines = []
          continue
        }

        if (line.startsWith(':')) {
          continue
        }
        if (line.startsWith('event:')) {
          eventType = line.slice(6).trim() || 'message'
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trimStart())
        } else if (line.startsWith('id:')) {
          eventId = line.slice(3).trim()
        }
      }
    }
  } finally {
    try {
      await reader.cancel()
      reader.releaseLock()
    } catch {
      // ignore
    }
  }
}

export function useAgentRunStream({
  getThreadState,
  isThreadActive = () => true,
  handlePublicEvent,
  fetchThreadMessages,
  fetchAgentState,
  resetThreadExecution,
  onScrollToBottom,
  streamSmoother,
  onInterruptDetected = null,
  onTerminalDetected = null,
  onRunStarted = null
}) {
  const stopRunStreamSubscription = (threadId) => {
    const ts = getThreadState(threadId)
    if (!ts) return
    streamSmoother?.flushThread(threadId)
    ts.runStreamAbortController?.abort()
    ts.runStreamAbortController = null
    clearTimeout(ts.runReconnectTimer)
    ts.runReconnectTimer = null
  }

  const settleTurn = (threadId, turnId, status, runId, touchedThreadIds) => {
    if (!isThreadActive(threadId)) return
    const ts = getThreadState(threadId)
    if (!ts || ts.currentTurnId !== turnId) return
    ts.runStateVersion = (ts.runStateVersion || 0) + 1
    const version = ts.runStateVersion
    ts.cooperationWaiting = false
    streamSmoother?.flushThread(threadId)
    ts.runStreamAbortController?.abort()
    ts.runStreamAbortController = null
    ts.isStreaming = false
    ts.turnStatus = status
    ts.activeRunSteerable = false
    ts.replyLoadingVisible = false
    ts.pendingInputId = null
    ts.runReconnectAttempts = 0
    if (status === 'requires_action') {
      ts.activeRunId = runId
    } else {
      ts.activeRunId = null
      ts.currentTurnId = null
      ts.pendingInterrupt = null
    }
    void (async () => {
      let refreshed = false
      try {
        await fetchThreadMessages({ threadId, turnId, fresh: true })
        refreshed = true
      } catch (error) {
        console.warn('Failed to refresh terminal history; retaining streamed output:', error)
      }
      if (
        !isThreadActive(threadId) ||
        getThreadState(threadId) !== ts ||
        ts.runStateVersion !== version
      )
        return
      if (status !== 'requires_action' && refreshed)
        resetThreadExecution(threadId, { preserveInputMonitors: true })
      void fetchAgentState(threadId)
      if (status === 'requires_action') onInterruptDetected?.({ threadId, runId })
      else onTerminalDetected?.({ threadId, runId, touchedThreadIds: [...touchedThreadIds] })
      if (status === 'completed') onScrollToBottom?.(threadId)
    })()
  }

  const reconcileTurn = async (threadId, turnId, fallbackRunId) => {
    const ts = getThreadState(threadId)
    const version = ts?.runStateVersion
    const turn = await agentApi.getThreadTurn(threadId, turnId)
    if (!isThreadActive(threadId)) return true
    if (!ts || getThreadState(threadId) !== ts || ts.currentTurnId !== turnId) return true
    if (ts.runStateVersion !== version) return false
    ts.runStateVersion = (ts.runStateVersion || 0) + 1
    const currentRunId = turn.yuxi.current_run_id || fallbackRunId
    if (['requires_action', 'completed', 'failed', 'cancelled'].includes(turn.status)) {
      settleTurn(threadId, turnId, turn.status, currentRunId, new Set([threadId]))
      return true
    }
    ts.activeRunId = currentRunId
    ts.cooperationWaiting = turn.yuxi.waitpoint?.kind === 'cooperation'
    ts.turnStatus = turn.status
    ts.isStreaming = true
    ts.activeRunSteerable = !ts.cooperationWaiting
    return false
  }

  const startRunStream = async (threadId, runId, afterCursor = null, options = {}) => {
    if (!threadId || !isThreadActive(threadId)) return
    const ts = getThreadState(threadId)
    if (!ts) return
    const version = ts.runStateVersion
    const turnId =
      options.turnId ||
      ts.currentTurnId ||
      (await agentApi.getPublicThread(threadId)).yuxi.current_turn?.id
    if (
      !turnId ||
      !isThreadActive(threadId) ||
      getThreadState(threadId) !== ts ||
      ts.runStateVersion !== version
    )
      return
    if (ts.currentTurnId === turnId && ts.activeRunId === runId && ts.runStreamAbortController)
      return

    stopRunStreamSubscription(threadId)
    ts.runStateVersion = (ts.runStateVersion || 0) + 1
    const controller = new AbortController()
    ts.runStreamAbortController = controller
    ts.cooperationWaiting = ts.currentTurnId === turnId && !!ts.cooperationWaiting
    ts.currentTurnId = turnId
    ts.activeRunId = runId
    ts.turnStatus = 'in_progress'
    ts.pendingInterrupt = null
    ts.activeRunSteerable = !ts.cooperationWaiting
    ts.isStreaming = true
    if (options.inputId) ts.pendingInputId = options.inputId
    onRunStarted?.({ threadId, runId, inputId: options.inputId })

    let sawTurnEnd = false
    try {
      if (afterCursor || ts.threadCursor) {
        sawTurnEnd = await reconcileTurn(threadId, turnId, runId)
        if (sawTurnEnd) return
      }
      if (controller.signal.aborted || ts.runStreamAbortController !== controller) return
      const response = await agentApi.streamThreadEvents(threadId, afterCursor || ts.threadCursor, {
        signal: controller.signal
      })
      if (!response.ok) throw new Error(`SSE response not ok: ${response.status}`)
      await processRunSseResponse(response, async (_event, data, eventId) => {
        if (!data || controller.signal.aborted || ts.currentTurnId !== turnId) return
        ts.runReconnectAttempts = 0
        if (data.session_id !== threadId) return
        if (data.type === 'yuxi.session.resync') {
          // 暂停消费，让 ReadableStream 缓冲新事件，快照应用后再继续合并。
          await fetchThreadMessages({ threadId, turnId, fresh: true })
          sawTurnEnd = await reconcileTurn(threadId, turnId, ts.activeRunId)
          if (eventId) ts.threadCursor = String(eventId)
          return
        }
        if (data.turn_id !== turnId) {
          if (eventId) ts.threadCursor = String(eventId)
          return
        }
        const status = data.turn?.status
        const owner = data.yuxi?.current_run_id || data.current_run_id
        if (
          ['requires_action', 'completed', 'failed', 'cancelled', 'in_progress', 'queued'].includes(status)
        ) {
          if (owner && data.yuxi?.run_id !== owner) return
          // 同一 SSE 会跨协作恢复的多个 Run，事件进展也必须使旧快照失效。
          ts.runStateVersion = (ts.runStateVersion || 0) + 1
          const eventVersion = ts.runStateVersion
          if (data.yuxi?.run_id !== ts.activeRunId) {
            const turn = await agentApi.getThreadTurn(threadId, turnId)
            if (controller.signal.aborted || ts.runStateVersion !== eventVersion) return
            ts.activeRunId = turn.yuxi.current_run_id
            if (data.yuxi?.run_id !== turn.yuxi.current_run_id) return
          }
        }
        if (['in_progress', 'queued'].includes(status)) {
          ts.pendingInterrupt = null
          ts.cooperationWaiting = data.waitpoint?.kind === 'cooperation'
          ts.turnStatus = status
          ts.isStreaming = true
          ts.activeRunSteerable = !ts.cooperationWaiting
        }
        handlePublicEvent(data, threadId)
        if (eventId) ts.threadCursor = String(eventId)
        if (['requires_action', 'completed', 'failed', 'cancelled'].includes(status)) {
          sawTurnEnd = true
          settleTurn(
            threadId,
            turnId,
            status,
            data.yuxi?.run_id || ts.activeRunId,
            new Set([threadId])
          )
        }
      })
      if (!sawTurnEnd && !controller.signal.aborted) {
        sawTurnEnd = await reconcileTurn(threadId, turnId, runId)
      }
    } catch (error) {
      if (error?.name !== 'AbortError' && !controller.signal.aborted) {
        console.error('Thread SSE stream error:', error)
        try {
          sawTurnEnd = await reconcileTurn(threadId, turnId, runId)
        } catch (lookupError) {
          console.warn('Failed to reconcile Thread after SSE error:', lookupError)
        }
        if (!sawTurnEnd) handleChatError(error, 'stream')
      }
    } finally {
      if (ts.runStreamAbortController === controller) ts.runStreamAbortController = null
      if (!sawTurnEnd && !controller.signal.aborted && ts.currentTurnId === turnId) {
        const reconnectAttempt = ts.runReconnectAttempts || 0
        ts.runReconnectAttempts = reconnectAttempt + 1
        ts.runReconnectTimer = setTimeout(() => {
          ts.runReconnectTimer = null
          if (
            !controller.signal.aborted &&
            ts.currentTurnId === turnId &&
            !ts.runStreamAbortController
          ) {
            void startRunStream(threadId, ts.activeRunId, ts.threadCursor, { turnId })
          }
        }, getReconnectDelay(reconnectAttempt))
      }
    }
  }

  const resumeActiveRunForThread = async (threadId) => {
    if (!threadId || !isThreadActive(threadId)) return
    const ts = getThreadState(threadId)
    if (!ts) return
    const version = ts.runStateVersion
    const thread = await agentApi.getPublicThread(threadId)
    if (
      !isThreadActive(threadId) ||
      getThreadState(threadId) !== ts ||
      ts.runStateVersion !== version
    )
      return
    const turnId = thread.yuxi.current_turn?.id
    if (!turnId) {
      ts.cooperationWaiting = false
      ts.activeRunId = null
      ts.currentTurnId = null
      ts.turnStatus = null
      ts.isStreaming = false
      return
    }
    const turn = await agentApi.getThreadTurn(threadId, turnId)
    if (
      !isThreadActive(threadId) ||
      getThreadState(threadId) !== ts ||
      ts.runStateVersion !== version
    )
      return
    ts.runStateVersion = (ts.runStateVersion || 0) + 1
    ts.currentTurnId = turnId
    ts.activeRunId = turn.yuxi.current_run_id
    ts.turnStatus = turn.status
    if (['queued', 'in_progress'].includes(turn.status)) {
      ts.cooperationWaiting = turn.yuxi.waitpoint?.kind === 'cooperation'
      ts.isStreaming = true
      ts.activeRunSteerable = !ts.cooperationWaiting
      if (!ts.runStreamAbortController) {
        void startRunStream(threadId, turn.yuxi.current_run_id, ts.threadCursor, { turnId })
      }
    } else {
      settleTurn(threadId, turnId, turn.status, turn.yuxi.current_run_id, new Set([threadId]))
    }
  }

  return { startRunStream, resumeActiveRunForThread, stopRunStreamSubscription }
}
