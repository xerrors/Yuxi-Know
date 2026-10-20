import { message } from 'ant-design-vue'
import { applyAgentEvent } from '@/modules/session/model/agentItems'

/** 主、子 Thread 共用公开事件消费入口。 */
export function useAgentStreamHandler({
  getThreadState,
  processApprovalInStream,
  streamSmoother
}) {
  const handlePublicEvent = (event, threadId) => {
    if (event.session_id !== threadId) return false
    const state = getThreadState(threadId)
    if (!state) return false
    const type = event.type
    if (
      type === 'yuxi.session.turn.state' &&
      state.activeRunId &&
      event.yuxi?.run_id !== state.activeRunId
    )
      return false
    applyAgentEvent(state.itemState, event)
    if (type.endsWith('output_text.delta') || type.endsWith('reasoning.delta')) {
      state.replyLoadingVisible = false
      streamSmoother?.updateText(event.item_id, threadId)
    } else if (type.endsWith('.done')) {
      streamSmoother?.flushThread(threadId)
    }
    if (type === 'agent.session.turn.failed') {
      message.error(event.turn?.error?.message || '本次运行失败，请检查模型配置后重试')
    }
    if (type === 'yuxi.session.turn.state') {
      state.agentStateRequestVersion = (state.agentStateRequestVersion || 0) + 1
      state.agentState = event.agent_state
    } else if (type === 'yuxi.session.turn.context_compression') {
      state.contextCompressing = event.compression?.status === 'started'
    } else if (type === 'yuxi.session.turn.waiting') {
      state.currentTurnId = event.turn_id
      state.activeRunId = event.yuxi.run_id
      state.turnStatus = event.turn.status
      state.replyLoadingVisible = false
      return processApprovalInStream?.(event, threadId) || false
    }
    return false
  }
  return { handlePublicEvent }
}
