import { message } from 'ant-design-vue'
import { handleChatError } from '@/utils/errorHandler'
import { unref } from 'vue'

/**
 * Process a streaming response from the server
 * @param {Response} response - The fetch response object
 * @param {Function} onChunk - Callback function for each parsed JSON chunk. Return true to stop processing.
 */
const processStreamResponse = async (response, onChunk) => {
  if (!response || !response.body) {
    console.warn('Invalid response or missing body for stream processing')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let stopProcessing = false

  try {
    while (!stopProcessing) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmedLine = line.trim()
        if (trimmedLine) {
          try {
            const chunk = JSON.parse(trimmedLine)
            if (onChunk && onChunk(chunk)) {
              stopProcessing = true
              break
            }
          } catch (e) {
            console.warn('Failed to parse stream chunk JSON:', e, 'Line:', trimmedLine)
          }
        }
      }
    }

    if (!stopProcessing && buffer.trim()) {
      try {
        const chunk = JSON.parse(buffer.trim())
        if (onChunk) {
          onChunk(chunk)
        }
      } catch (e) {
        console.warn('Failed to parse final stream chunk JSON:', e)
      }
    }
  } finally {
    try {
      reader.releaseLock()
    } catch (e) {
      // Ignore errors on releasing lock
    }
  }
}

export function useAgentStreamHandler({
  getThreadState,
  processApprovalInStream,
  currentAgentId,
  supportsTodo,
  supportsFiles
}) {
  /**
   * Process a single stream chunk based on its status
   * @param {Object} chunk - The parsed JSON chunk
   * @param {String} threadId - The current thread ID
   * @returns {Boolean} - Returns true if processing should stop (e.g. error, finished, interrupted)
   */
  const handleStreamChunk = (chunk, threadId) => {
    const { status, msg, request_id, message: chunkMessage } = chunk
    const threadState = getThreadState(threadId)

    if (!threadState) return false

    switch (status) {
      case 'init':
        threadState.onGoingConv.msgChunks[request_id] = [msg]
        return false

      case 'loading':
        if (msg.id) {
          if (!threadState.onGoingConv.msgChunks[msg.id]) {
            threadState.onGoingConv.msgChunks[msg.id] = []
          }
          threadState.onGoingConv.msgChunks[msg.id].push(msg)
        }
        return false

      case 'error':
        handleChatError({ message: chunkMessage }, 'stream')
        // Stop the loading indicator
        if (threadState) {
          threadState.isStreaming = false

          // Abort the stream controller to stop processing further events
          if (threadState.streamAbortController) {
            threadState.streamAbortController.abort()
            threadState.streamAbortController = null
          }
        }
        return true

      case 'human_approval_required':
        // 使用审批 composable 处理审批请求
        return processApprovalInStream(chunk, threadId, unref(currentAgentId))

      case 'agent_state':
        if ((unref(supportsTodo) || unref(supportsFiles)) && chunk.agent_state) {
          console.log('[AgentState]', {
            threadId,
            todos: chunk.agent_state?.todos || [],
            files: chunk.agent_state?.files || []
          })
          threadState.agentState = chunk.agent_state
        }
        return false

      case 'finished':
        // 先标记流式结束，但保持消息显示直到历史记录加载完成
        if (threadState) {
          threadState.isStreaming = false
          if ((unref(supportsTodo) || unref(supportsFiles)) && threadState.agentState) {
            console.log(
              `[AgentState|Final] ${new Date().toLocaleTimeString()}.${new Date().getMilliseconds()}`,
              {
                threadId,
                todos: threadState.agentState?.todos || [],
                files: threadState.agentState?.files || []
              }
            )
          }
        }
        return true

      case 'interrupted':
        // 中断状态，刷新消息历史
        console.warn('[Interrupted] case')
        if (threadState) {
          threadState.isStreaming = false
        }
        // 如果有 message 字段，显示提示（例如：敏感内容检测）
        if (chunkMessage) {
          message.info(chunkMessage)
        }
        return true
    }

    return false
  }

  /**
   * Process the full agent stream response
   * @param {Response} response - The fetch response
   * @param {String} threadId - The thread ID
   * @param {Function} [onChunk] - Optional callback for each chunk (e.g. for logging)
   */
  const handleAgentResponse = async (response, threadId, onChunk = null) => {
    await processStreamResponse(response, (chunk) => {
      if (onChunk) onChunk(chunk)
      return handleStreamChunk(chunk, threadId)
    })
  }

  return {
    handleStreamChunk,
    handleAgentResponse
  }
}
