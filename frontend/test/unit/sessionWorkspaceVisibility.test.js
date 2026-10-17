import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { computed, reactive, ref, compile, createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

const source = readFileSync(
  new URL('../../src/modules/session/ui/SessionWorkspace.vue', import.meta.url),
  'utf8'
)

test('人工等待取消期间显示停止反馈，即使没有流和排队消息', () => {
  const state = ref({ cancellationPending: true })
  const expressions = source.slice(
    source.indexOf('const isProcessing ='),
    source.indexOf('const replyElapsedSeconds =')
  )
  const values = new Function(
    'computed',
    'currentThreadState',
    'isStreaming',
    'hasQueuedInputs',
    'currentQueueSnapshot',
    'isWaitingForUserAction',
    'queuedInputCount',
    `${expressions}; return { isProcessing, isReplyLoading, replyLoadingText }`
  )(computed, state, ref(false), ref(false), ref({ status: 'ready' }), ref(true), ref(0))
  assert.equal(values.isProcessing.value, true)
  assert.equal(values.isReplyLoading.value, true)
  assert.equal(values.replyLoadingText.value, '正在停止，等待任务清理完成...')
})

test('隐藏成员标签继续接收终态，但不标已读或滚动；显示后恢复可见副作用', () => {
  const props = reactive({ visible: false })
  const visibility = source.slice(
    source.indexOf('const workspaceActivated ='),
    source.indexOf('// ==================== LOCAL CHAT')
  )
  const { workspaceActive, workspaceActivated } = new Function(
    'computed',
    'ref',
    'props',
    `${visibility}; return { workspaceActive, workspaceActivated }`
  )(computed, ref, props)
  const viewed = [],
    resumed = []
  let scrolls = 0
  const dependencies = {
    getThreadState() {},
    currentAgentId: ref('agent'),
    handlePublicEvent() {},
    fetchThreadMessages() {},
    fetchAgentState() {},
    resetThreadExecution() {},
    streamSmoother: {},
    workspaceActive,
    pageVisible: ref(true),
    scrollController: {
      scrollToBottom() {
        scrolls++
      }
    },
    approvalState: {},
    hideApprovalState() {},
    resumeQueuedInputs: (id) => resumed.push(id),
    currentThreadId: ref('child'),
    chatThreadsStore: { markThreadViewed: (id) => viewed.push(id) },
    agentPanelFilesystemRefreshVersion: ref(0),
    sessionRuntime: {}
  }
  const registration = source.slice(
    source.indexOf('const runtimeView ='),
    source.indexOf('let releaseRuntimeView')
  )
  const handlers = new Function(
    ...Object.keys(dependencies),
    `${registration}; return runtimeView`
  )(...Object.values(dependencies))
  const complete = () => {
    handlers.onTerminalDetected({ threadId: 'child', runId: 'run' })
    handlers.onScrollToBottom()
  }
  complete()
  assert.deepEqual(resumed, [], '恢复由共享运行内核负责')
  assert.deepEqual(viewed, [])
  assert.equal(scrolls, 0)
  props.visible = true
  complete()
  assert.deepEqual(viewed, ['child'])
  assert.equal(scrolls, 1)
  dependencies.pageVisible.value = false
  complete()
  assert.deepEqual(viewed, ['child'], '浏览器后台标签也不能标记已读')
  assert.equal(scrolls, 1)
  dependencies.pageVisible.value = true
  workspaceActivated.value = false
  complete()
  assert.deepEqual(viewed, ['child'], 'KeepAlive 后台页面也不能标记已读')
  assert.equal(scrolls, 1)
})

test('另一视图完成审批后，本视图立即解除旧等待点的输入遮罩', () => {
  const expression = source.slice(
    source.indexOf('const currentApprovalModalVisible ='),
    source.indexOf('const currentApprovalQuestions =')
  )
  const pending = { interruptedRunId: 'run', waitpointId: 'approval-1' }
  const shared = ref({ pendingInterrupt: pending })
  const local = reactive({ showModal: true, threadId: 'thread', ...pending })
  const visible = new Function(
    'computed',
    'approvalState',
    'visibleApprovalThreadId',
    'currentThreadState',
    `${expression}; return currentApprovalModalVisible`
  )(computed, local, ref('thread'), shared)
  assert.equal(visible.value, true)
  shared.value.pendingInterrupt = null
  assert.equal(visible.value, false, '其他视图提交并清除共享等待点后不再阻塞输入')
  shared.value.pendingInterrupt = { interruptedRunId: 'run2', waitpointId: 'approval-2' }
  assert.equal(visible.value, false, '旧面板也不能代表新 Run 的审批')
  Object.assign(local, shared.value.pendingInterrupt)
  assert.equal(visible.value, true)
})

const view = readFileSync(new URL('../../src/pages/AgentView.vue', import.meta.url), 'utf8')
const dock = source.slice(
  source.lastIndexOf('<div', source.indexOf('ref="messageInputDockRef"')),
  source.indexOf('<section', source.indexOf('ref="messageInputDockRef"'))
)
const render = compile(`${dock}</div></div>`)
const layoutExpression = source.slice(
  source.indexOf('const showStartScreen ='),
  source.indexOf('const currentThread =')
)

test('新建路由且没有线程才显示欢迎布局，加载和空消息不改变布局', async () => {
  assert.ok(view.includes(':is-new-session="!threadId"'), '新建布局由路由传入')
  for (const isNewSession of [false, true]) {
    for (const threadId of [null, 'created-thread']) {
      const props = reactive({ isNewSession })
      const currentThreadId = ref(threadId)
      const showStartScreen = new Function(
        'computed',
        'props',
        'currentThreadId',
        `${layoutExpression}; return showStartScreen`
      )(computed, props, currentThreadId)
      for (const isLoadingMessages of [false, true]) {
        for (const runGroups of [[], [{ id: 'history' }]]) {
          const html = await renderToString(
            createSSRApp({
              data: () => ({
                isNewSession,
                currentChatId: threadId,
                pendingSends: {},
                showStartScreen: showStartScreen.value,
                isLoadingMessages,
                runGroups,
                randomGreeting: '欢迎测试'
              }),
              render
            })
          )
          assert.equal(html.includes('start-screen'), isNewSession && !threadId)
          assert.equal(html.includes('欢迎测试'), isNewSession && !threadId)
          assert.equal(html.includes('正在加载消息'), isLoadingMessages)
        }
      }
      props.isNewSession = true
      currentThreadId.value = null
      assert.equal(showStartScreen.value, true)
      currentThreadId.value = 'just-created'
      assert.equal(showStartScreen.value, false, '创建完成立即收起欢迎布局')
      props.isNewSession = false
      currentThreadId.value = null
      assert.equal(showStartScreen.value, false, '已有会话加载时不显示欢迎布局')
    }
  }
})
