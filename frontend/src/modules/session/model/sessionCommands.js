import { agentApi } from '@/apis'

/** 读取当前等待点并提交回答或审批，拒绝已变更的执行归属。 */
export async function resumeSessionWaitpoint({ threadId, turnId, runId, kind, answer }) {
  if (!turnId) throw new Error('当前线程没有等待中的 Turn')
  const turn = await agentApi.getThreadTurn(threadId, turnId)
  const waitpoint = turn.yuxi.waitpoint
  if (
    turn.status !== 'requires_action' ||
    turn.yuxi.current_run_id !== runId ||
    !waitpoint?.id ||
    waitpoint.run_id !== runId
  ) {
    throw new Error('当前审批所属 Turn 已变化，请刷新后重试')
  }
  let response
  if (kind === 'tool_approval') {
    const calls = waitpoint.calls || []
    const selected = answer?.decisions || []
    if (!calls.length || calls.length !== selected.length) {
      throw new Error('审批请求已变化，请刷新后重试')
    }
    response = {
      type: 'approval',
      decisions: calls.map((call, index) => ({
        call_id: call.call_id,
        decision: selected[index].type
      }))
    }
  } else {
    const questions = waitpoint.questions || []
    if (
      !questions.length ||
      questions.some((question) => !Object.hasOwn(answer || {}, question.question_id))
    ) {
      throw new Error('请回答全部问题后再提交')
    }
    response = {
      type: 'answer',
      answers: questions.map((question) => ({
        question_id: question.question_id,
        answer: answer[question.question_id]
      }))
    }
  }
  const accepted = await agentApi.resumeThreadTurn(threadId, {
    turn_id: turnId,
    waitpoint_id: waitpoint.id,
    response,
    idempotency_key: `resume-${waitpoint.id}`
  })
  if (!accepted?.run_id) {
    throw new Error('恢复已接收但未创建 Run，请刷新后查看 Turn 状态')
  }
  return accepted
}
