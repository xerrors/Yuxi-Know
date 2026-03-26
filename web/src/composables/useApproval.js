import { reactive } from 'vue'
import { message } from 'ant-design-vue'
import { handleChatError } from '@/utils/errorHandler'
import { agentApi } from '@/apis'
import { normalizeQuestions, buildLegacyQuestion } from '@/utils/questionUtils'

const extractQuestionPayload = (chunk) => {
  const interruptInfo = chunk?.interrupt_info || {}
  const rawQuestions = chunk?.questions || interruptInfo?.questions || []
  const source = chunk?.source || interruptInfo?.source || 'interrupt'
  let questions = normalizeQuestions(rawQuestions)

  if (!questions.length) {
    const legacyQuestion = buildLegacyQuestion(chunk, interruptInfo)
    if (legacyQuestion) {
      questions = [legacyQuestion]
    }
  }

  return {
    questions,
    source
  }
}

const parseApprovedDecision = (answer) => {
  const parseFromValue = (value) => {
    if (typeof value === 'boolean') return value
    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase()
      if (normalized === 'approve' || normalized === 'approved' || normalized === 'true')
        return true
      if (normalized === 'reject' || normalized === 'rejected' || normalized === 'false')
        return false
    }
    return null
  }

  const direct = parseFromValue(answer)
  if (direct !== null) return direct

  if (answer && typeof answer === 'object' && !Array.isArray(answer)) {
    const values = Object.values(answer)
    if (values.length === 1) {
      return parseFromValue(values[0])
    }
  }

  return null
}

export function useApproval({ getThreadState, resetOnGoingConv, fetchThreadMessages }) {
  const approvalState = reactive({
    showModal: false,
    questions: [],
    status: '',
    threadId: null
  })

  const handleApproval = async (answer, currentAgentId, agentConfigId) => {
    const threadId = approvalState.threadId
    if (!threadId) {
      message.error('无效的提问请求')
      approvalState.showModal = false
      return
    }

    const threadState = getThreadState(threadId)
    if (!threadState) {
      message.error('无法找到对应的对话线程')
      approvalState.showModal = false
      return
    }

    if (!agentConfigId) {
      message.error('缺少智能体配置，请重新选择配置后重试')
      approvalState.showModal = false
      return
    }

    approvalState.showModal = false

    if (threadState.streamAbortController) {
      threadState.streamAbortController.abort()
      threadState.streamAbortController = null
    }

    threadState.isStreaming = true
    resetOnGoingConv(threadId)
    threadState.streamAbortController = new AbortController()

    const requestBody = {
      thread_id: threadId,
      config: { agent_config_id: agentConfigId }
    }

    if (approvalState.status === 'human_approval_required') {
      const approved = parseApprovedDecision(answer)
      if (approved !== null) {
        requestBody.approved = approved
      } else {
        requestBody.answer = answer
      }
    } else {
      requestBody.answer = answer
    }

    try {
      const response = await agentApi.resumeAgentChat(threadId, requestBody, {
        signal: threadState.streamAbortController?.signal
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP error! status: ${response.status}, details: ${errorText}`)
      }

      return response
    } catch (error) {
      if (error.name !== 'AbortError') {
        handleChatError(error, 'resume')
        message.error(`恢复对话失败: ${error.message || '未知错误'}`)
      }
      threadState.isStreaming = false
      threadState.streamAbortController = null
      throw error
    }
  }

  const processApprovalInStream = (chunk, threadId, currentAgentId) => {
    if (
      chunk.status !== 'ask_user_question_required' &&
      chunk.status !== 'human_approval_required'
    ) {
      return false
    }

    const threadState = getThreadState(threadId)
    if (!threadState) return false

    const payload = extractQuestionPayload(chunk)
    if (!payload.questions.length) return false

    threadState.isStreaming = false

    approvalState.showModal = true
    approvalState.questions = payload.questions
    approvalState.status = chunk.status || ''
    approvalState.threadId = chunk.thread_id || threadId

    fetchThreadMessages({ agentId: currentAgentId, threadId })

    return true
  }

  const resetApprovalState = () => {
    approvalState.showModal = false
    approvalState.questions = []
    approvalState.status = ''
    approvalState.threadId = null
  }

  return {
    approvalState,
    handleApproval,
    processApprovalInStream,
    resetApprovalState
  }
}
