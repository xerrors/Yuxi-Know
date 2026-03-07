import { reactive } from 'vue'
import { message } from 'ant-design-vue'
import { handleChatError } from '@/utils/errorHandler'
import { agentApi } from '@/apis'

const normalizeOptions = (rawOptions) => {
  if (!Array.isArray(rawOptions)) return []
  return rawOptions
    .map((item) => {
      if (item && typeof item === 'object') {
        const label = String(item.label || item.value || '').trim()
        const value = String(item.value || item.label || '').trim()
        return label && value ? { label, value } : null
      }
      const text = String(item || '').trim()
      return text ? { label: text, value: text } : null
    })
    .filter(Boolean)
}

const toLegacyApprovalOptions = () => [
  { label: '批准 (Recommended)', value: 'approve' },
  { label: '拒绝', value: 'reject' }
]

const extractQuestionPayload = (chunk) => {
  const interruptInfo = chunk?.interrupt_info || {}
  const rawOptions =
    chunk?.options || interruptInfo?.options || (interruptInfo?.operation ? toLegacyApprovalOptions() : [])
  const options = normalizeOptions(rawOptions)
  const operation = chunk?.operation || interruptInfo?.operation || ''

  const source = chunk?.source || interruptInfo?.source || (operation ? 'get_approved_user_goal' : 'interrupt')
  const multiSelect = Boolean(chunk?.multi_select ?? interruptInfo?.multi_select ?? false)
  let allowOther = Boolean(chunk?.allow_other ?? interruptInfo?.allow_other ?? true)
  const questionId = chunk?.question_id || interruptInfo?.question_id || ''
  const question = chunk?.question || interruptInfo?.question || '请选择一个选项'
  const legacyMode = source === 'get_approved_user_goal' && options.length === 2
  if (source === 'get_approved_user_goal') {
    allowOther = false
  }

  return {
    questionId,
    question,
    options,
    multiSelect,
    allowOther,
    source,
    operation,
    legacyMode
  }
}

const inferApprovedFromAnswer = (answer) => {
  if (answer === 'approve') return true
  if (answer === 'reject') return false
  return null
}

export function useApproval({ getThreadState, resetOnGoingConv, fetchThreadMessages }) {
  const approvalState = reactive({
    showModal: false,
    questionId: '',
    question: '',
    operation: '',
    options: [],
    multiSelect: false,
    allowOther: true,
    source: '',
    legacyMode: false,
    threadId: null
  })

  const handleApproval = async (answer, currentAgentId, agentConfigId = null) => {
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

    approvalState.showModal = false

    if (threadState.streamAbortController) {
      threadState.streamAbortController.abort()
      threadState.streamAbortController = null
    }

    threadState.isStreaming = true
    resetOnGoingConv(threadId)
    threadState.streamAbortController = new AbortController()

    const approved = inferApprovedFromAnswer(answer)
    const requestBody = {
      thread_id: threadId,
      answer,
      config: agentConfigId ? { agent_config_id: agentConfigId } : {}
    }
    if (approved !== null) {
      requestBody.approved = approved
    }

    try {
      const response = await agentApi.resumeAgentChat(currentAgentId, requestBody, {
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
    if (chunk.status !== 'ask_user_question_required' && chunk.status !== 'human_approval_required') {
      return false
    }

    const threadState = getThreadState(threadId)
    if (!threadState) return false

    const payload = extractQuestionPayload(chunk)
    if (!payload.options.length) {
      payload.options = toLegacyApprovalOptions()
      payload.legacyMode = true
      payload.allowOther = false
    }

    threadState.isStreaming = false

    approvalState.showModal = true
    approvalState.questionId = payload.questionId
    approvalState.question = payload.question
    approvalState.operation = payload.operation
    approvalState.options = payload.options
    approvalState.multiSelect = payload.multiSelect
    approvalState.allowOther = payload.allowOther
    approvalState.source = payload.source
    approvalState.legacyMode = payload.legacyMode
    approvalState.threadId = chunk.thread_id || threadId

    fetchThreadMessages({ agentId: currentAgentId, threadId })

    return true
  }

  const resetApprovalState = () => {
    approvalState.showModal = false
    approvalState.questionId = ''
    approvalState.question = ''
    approvalState.operation = ''
    approvalState.options = []
    approvalState.multiSelect = false
    approvalState.allowOther = true
    approvalState.source = ''
    approvalState.legacyMode = false
    approvalState.threadId = null
  }

  return {
    approvalState,
    handleApproval,
    processApprovalInStream,
    resetApprovalState
  }
}
