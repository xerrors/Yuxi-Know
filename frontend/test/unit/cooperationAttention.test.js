import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createSSRApp, h, nextTick, ref, watch } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createTestServer } from '../helpers/createTestServer.js'
import {
  getCooperationPendingActions,
  getSessionAttentionLabel
} from '../../src/modules/session/model/cooperationAttention.js'

let server, CooperationAttention
before(async () => {
  server = await createTestServer({ server: { middlewareMode: true, hmr: false } })
  ;({ default: CooperationAttention } = await server.ssrLoadModule(
    '/src/modules/session/ui/CooperationAttention.vue'
  ))
})
after(async () => {
  await server?.close()
})

const member = (sessionId, waitingFor, status = 'waiting') => ({
  session_id: sessionId,
  name: sessionId,
  turn_status: status,
  waiting_for: waitingFor
})
const render = async (actions, error = '') => {
  const app = createSSRApp(CooperationAttention, { actions, error })
  app.component('a-popover', {
    props: ['trigger', 'placement', 'open', 'afterVisibleChange'],
    emits: ['openChange'],
    setup:
      (_, { slots }) =>
      () =>
        slots.default()
  })
  return renderToString(app)
}

test('人工待办只来自其他成员当前等待中的回答或审批', () => {
  const sessions = [
    member('root', 'approval'),
    member('child', 'answer'),
    member('grandchild', 'approval'),
    member('cooperation', 'cooperation'),
    member('unknown', 'unknown'),
    ...['completed', 'cancelled', 'failed', 'running', 'cancelling'].map((status) =>
      member(status, 'approval', status)
    )
  ]
  assert.deepEqual(getCooperationPendingActions(sessions, 'root'), [
    { sessionId: 'child', name: 'child', label: '待回答', action: '去回答' },
    { sessionId: 'grandchild', name: 'grandchild', label: '待审批', action: '查看审批' }
  ])
  assert.equal(getSessionAttentionLabel(null), '')
  assert.equal(getSessionAttentionLabel(member('done', 'answer', 'completed')), '')
})

test('单项和多项提供明确动作，空列表移除胶囊，查询失败仍显示重试', async () => {
  const actions = getCooperationPendingActions([member('资料整理', 'approval')], 'root')
  const single = await render(actions)
  assert.match(single, /资料整理 待审批/)
  assert.match(single, /查看审批/)
  assert.match(single, /role="status"/)
  const multi = await render([
    ...actions,
    ...getCooperationPendingActions([member('检索', 'answer')], 'root')
  ])
  assert.match(multi, /2 个协作任务需要你处理 · 1 待审批 \/ 1 待回答/)
  assert.match(multi, /查看待办/)
  assert.doesNotMatch(await render([]), /class="attention-pill"/)
  const stale = await render(actions, 'offline')
  assert.match(stale, /资料整理 待审批/)
  assert.match(stale, /协作状态更新失败，显示最近已知待办/)
  assert.match(stale, /重试/)
  assert.match(await render([], 'offline'), /协作状态更新失败/)
})

test('查看单项或选择列表成员只发起导航，不消费待办', async () => {
  const actions = getCooperationPendingActions([member('child', 'answer')], 'root')
  const opened = []
  let state
  await renderToString(
    createSSRApp({
      setup() {
        state = CooperationAttention.setup(
          { actions, error: '' },
          {
            expose() {},
            emit: (event, id) => opened.push([event, id])
          }
        )
        return () => h('div')
      }
    })
  )
  state.handleClick()
  assert.deepEqual(opened, [['open', 'child']])
  assert.equal(actions.length, 1)
  actions.push({ sessionId: 'second', name: 'second', label: '待审批', action: '查看审批' })
  state.handleClick()
  assert.equal(opened.length, 1, '多项不能默认替用户选择成员')
  state.openAction(actions[1])
  assert.deepEqual(opened.at(-1), ['open', 'second'])
  assert.equal(actions.length, 2)
})

test('慢等待点恢复后才聚焦，隐藏或轮次变化撤销聚焦', async (t) => {
  const source = readFileSync(
    new URL('../../src/modules/session/ui/SessionWorkspace.vue', import.meta.url),
    'utf8'
  )
  const functionSource = source.slice(
    source.indexOf('async function focusPendingAction()'),
    source.indexOf('const handleAgentStateRefresh')
  )
  let ready,
    focused = false,
    resumed = false
  const workspaceReady = new Promise((resolve) => {
    ready = resolve
  })
  const workspaceActive = ref(true)
  const currentApprovalModalVisible = ref(false)
  const currentThreadState = ref({ turnStatus: 'requires_action', currentTurnId: 'turn' })
  const pendingActionFocusTurnId = ref(null)
  const stops = []
  t.after(() => stops.forEach((stop) => stop()))
  const focus = new Function(
    'workspaceReady',
    'resumeCurrentRunForVisiblePage',
    'nextTick',
    'messageInputStageRef',
    'workspaceActive',
    'currentThreadState',
    'pendingActionFocusTurnId',
    'currentApprovalModalVisible',
    'watch',
    `${functionSource}; return focusPendingAction`
  )(
    workspaceReady,
    async () => {
      resumed = true
    },
    nextTick,
    {
      value: {
        querySelector: () => ({
          focus() {
            focused = true
          }
        })
      }
    },
    workspaceActive,
    currentThreadState,
    pendingActionFocusTurnId,
    currentApprovalModalVisible,
    (...args) => stops.push(watch(...args))
  )
  const pending = focus()
  await nextTick()
  assert.equal(resumed, false)
  assert.equal(focused, false)
  ready()
  await pending
  assert.equal(resumed, true)
  assert.equal(focused, false, '导航恢复返回时，等待点仍可能未到达')
  currentApprovalModalVisible.value = true
  await nextTick()
  await nextTick()
  assert.equal(focused, true)
  focused = false
  currentApprovalModalVisible.value = false
  await focus()
  workspaceActive.value = false
  await nextTick()
  currentApprovalModalVisible.value = true
  await nextTick()
  assert.equal(focused, false, '晚到的卡片不能抢隐藏视图的焦点')
  workspaceActive.value = true
  currentApprovalModalVisible.value = false
  await focus()
  currentThreadState.value.currentTurnId = 'another-turn'
  await nextTick()
  currentApprovalModalVisible.value = true
  await nextTick()
  assert.equal(focused, false)
  currentApprovalModalVisible.value = false
  await focus()
  currentThreadState.value.turnStatus = 'in_progress'
  await nextTick()
  currentThreadState.value.turnStatus = 'requires_action'
  currentApprovalModalVisible.value = true
  await nextTick()
  await nextTick()
  assert.equal(focused, false, '同一轮次恢复后，新等待点不能复用旧聚焦意图')
})
