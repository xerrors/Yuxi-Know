import { reactive } from 'vue'
import { message } from 'ant-design-vue'
import { handleChatError } from '@/utils/errorHandler'
import { agentApi } from '@/apis'

export function useApproval({ getThreadState, resetOnGoingConv, fetchThreadMessages }) {
  // 审批状态
  const approvalState = reactive({
    showModal: false,
    question: '',
    operation: '',
    threadId: null,
    interruptInfo: null
  })

  // 处理审批逻辑
  const handleApproval = async (approved, currentAgentId) => {
    const threadId = approvalState.threadId
    if (!threadId) {
      message.error('无效的审批请求')
      approvalState.showModal = false
      return
    }

    const threadState = getThreadState(threadId)
    if (!threadState) {
      message.error('无法找到对应的对话线程')
      approvalState.showModal = false
      return
    }

    // 关闭弹窗
    approvalState.showModal = false

    // 清理旧的流式控制器（如果存在）
    if (threadState.streamAbortController) {
      threadState.streamAbortController.abort()
      threadState.streamAbortController = null
    }

    // 标记为处理中
    threadState.isStreaming = true
    resetOnGoingConv(threadId)
    threadState.streamAbortController = new AbortController()

    console.log('🔄 [APPROVAL] Starting resume process:', { approved, threadId, currentAgentId })

    try {
      // 调用恢复接口
      const response = await agentApi.resumeAgentChat(
        currentAgentId,
        {
          thread_id: threadId,
          approved: approved
        },
        {
          signal: threadState.streamAbortController?.signal
        }
      )

      console.log('🔄 [APPROVAL] Resume API response received')

      if (!response.ok) {
        const errorText = await response.text()
        console.error('Resume API error:', response.status, errorText)
        throw new Error(`HTTP error! status: ${response.status}, details: ${errorText}`)
      }

      console.log('🔄 [APPROVAL] Resume API successful, returning response for stream processing')
      return response // 返回响应供调用方处理流式数据
    } catch (error) {
      console.error('❌ [APPROVAL] Resume failed:', error)
      if (error.name !== 'AbortError') {
        handleChatError(error, 'resume')
        message.error(`恢复对话失败: ${error.message || '未知错误'}`)
      }
      // 重置状态 - 只在错误时重置
      threadState.isStreaming = false
      threadState.streamAbortController = null
      throw error // 重新抛出错误让调用方处理
    }
    // 移除 finally 块 - 让组件管理流式状态的生命周期
  }

  // 在流式处理中处理审批请求
  const processApprovalInStream = (chunk, threadId, currentAgentId) => {
    if (chunk.status !== 'human_approval_required') {
      return false
    }

    const { interrupt_info } = chunk
    const threadState = getThreadState(threadId)

    if (!threadState) return false

    // 停止显示"处理中"状态，让用户可以看到并操作审批弹窗
    threadState.isStreaming = false

    // 显示审批弹窗
    approvalState.showModal = true
    approvalState.question = interrupt_info?.question || '是否批准以下操作？'
    approvalState.operation = interrupt_info?.operation || '未知操作'
    approvalState.threadId = chunk.thread_id || threadId
    approvalState.interruptInfo = interrupt_info

    // 刷新消息历史显示已执行的部分
    fetchThreadMessages({ agentId: currentAgentId, threadId: threadId })

    return true // 表示已处理审批请求，应停止流式处理
  }

  // 重置审批状态
  const resetApprovalState = () => {
    approvalState.showModal = false
    approvalState.question = ''
    approvalState.operation = ''
    approvalState.threadId = null
    approvalState.interruptInfo = null
  }

  return {
    approvalState,
    handleApproval,
    processApprovalInStream,
    resetApprovalState
  }
}
