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
    source.indexOf('const isSendButtonDisabled =')
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
  assert.equal(dependencies.agentPanelFilesystemRefreshVersion.value, 4, '终态即使在后台也必须使当前线程预览失效')
  handlers.onTerminalDetected({ threadId: 'other-thread', runId: 'other-run' })
  assert.equal(dependencies.agentPanelFilesystemRefreshVersion.value, 4, '其它线程终态不得刷新当前线程预览')
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

test('提交进行中不显示未知接收结果，失败后才提供幂等重试入口', async () => {
  for (const submitting of [true, false]) {
    const html = await renderToString(createSSRApp({
      data: () => ({
        currentChatId: 'thread',
        pendingSends: { thread: { submitting } },
        showStartScreen: false,
        isLoadingMessages: false,
        agentExecutionAvailable: true,
        sendCooldownActive: false,
        handleSendMessage() {}
      }),
      render
    }))
    assert.equal(html.includes('发送结果待确认'), !submitting)
  }
})

test('智能体加载或不可用时保留编辑器区域，并禁止输入', async () => {
  const surfaceStart = source.lastIndexOf('<div', source.indexOf('class="message-input-surface"'))
  const surface = source.slice(surfaceStart, source.indexOf('>', surfaceStart) + 1)
  const inputStart = source.indexOf('<AgentInputArea', surfaceStart)
  const disabled = source.slice(inputStart).match(/:disabled="([^"]+)"/)[1]
  const renderSurface = compile(`${surface}<input :disabled="${disabled}" /></div>`)
  for (const status of ['loading', 'ready', 'unavailable', 'error']) {
    const html = await renderToString(createSSRApp({
      data: () => ({
        currentChatId: 'thread',
        currentToolApprovalVisible: false,
        threadCreationInFlight: false,
        agentExecutionAvailable: status === 'ready'
      }),
      render: renderSurface
    }))
    assert.ok(html.includes('message-input-surface'), `${status} 不能卸载编辑器`)
    assert.equal(html.includes(' disabled'), status !== 'ready')
  }
})

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
        'threadCreationInFlight',
        `${layoutExpression}; return showStartScreen`
      )(computed, props, currentThreadId, ref(false))
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
          assert.equal(html.includes('正在加载消息'), false, '编辑器上方不再单独加载消息')
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

test('智能体、历史和创建加载共用一个 Spin，加载不占据编辑器布局', async () => {
  const loadingExpression = source.slice(source.indexOf('const isSessionLoading ='), source.indexOf('/** 重用对话加载入口'))
  const loadingStart = source.lastIndexOf('<div', source.indexOf('class="session-loading"'))
  const renderLoading = compile(source.slice(loadingStart, source.indexOf('<div class="chat-box">', loadingStart)))
  for (const messages of [false, true]) {
    for (const agent of ['ready', 'loading']) {
      for (const creating of [false, true]) {
        for (const historyLoaded of [false, true]) {
          const isSessionLoading = new Function(
            'computed', 'isLoadingMessages', 'props', 'threadCreationInFlight', 'currentChatId', 'sessionAgentStatus', 'currentThreadState',
            `${loadingExpression}; return isSessionLoading`
          )(computed, ref(messages), { isNewSession: true }, ref(creating), ref('thread'), ref(agent), ref({ historyLoaded }))
          const html = await renderToString(createSSRApp({
            data: () => ({ isSessionLoading: isSessionLoading.value }),
            components: { 'a-spin': { template: '<span data-shared-spin />' } },
            render: renderLoading
          }))
          const loading = creating || (!historyLoaded && (messages || agent === 'loading'))
          assert.equal((html.match(/data-shared-spin/g) || []).length, loading ? 1 : 0)
          assert.equal(html.includes('正在加载对话'), loading)
        }
      }
    }
  }
})

test('首条待消费输入只展示消息气泡，后续输入、暂停及附件准备保留队列入口', () => {
  const state = ref({
    pendingInputId: 'primary',
    optimisticInputs: { primary: [{ content: '首条消息' }] },
    queuedInputs: [{ input_id: 'primary' }, { input_id: 'later' }],
    queueSnapshot: { status: 'ready' }
  })
  const expressions = source.slice(source.indexOf('const currentQueuedInputs ='), source.indexOf('const queuedInputCount ='))
  const { primaryQueuedInput, visibleQueuedInputs, currentQueuedInputs } = new Function(
    'computed', 'currentThreadState', 'IDLE_QUEUE_SNAPSHOT',
    `${expressions}; return { primaryQueuedInput, visibleQueuedInputs, currentQueuedInputs }`
  )(computed, state, { status: 'ready' })
  assert.equal(primaryQueuedInput.value.input_id, 'primary')
  assert.deepEqual(visibleQueuedInputs.value.map((input) => input.input_id), ['later'])
  assert.equal(currentQueuedInputs.value.length, 2, '展示去重不能改写持久队列投影')
  state.value.queueSnapshot.status = 'paused'
  assert.equal(primaryQueuedInput.value, null)
  assert.equal(visibleQueuedInputs.value.length, 2, '暂停后必须保留继续队列及取消入口')
  state.value.queueSnapshot.status = 'ready'
  state.value.queuedInputs[0].attachment_status = 'preparing'
  assert.equal(primaryQueuedInput.value, null)
  assert.equal(visibleQueuedInputs.value.length, 2, '附件准备状态仍需展示')
  delete state.value.queuedInputs[0].attachment_status
  delete state.value.optimisticInputs.primary
  assert.equal(primaryQueuedInput.value, null)
  assert.equal(visibleQueuedInputs.value.length, 2, '没有消息气泡时不能隐藏排队输入')
})

test('首条输入在回复位置保留取消入口，取消期间禁用重复操作', async () => {
  const marker = source.indexOf('v-if="primaryQueuedInput &&')
  const start = source.lastIndexOf('<button', marker)
  const renderCancel = compile(source.slice(start, source.indexOf('</button>', marker) + '</button>'.length))
  for (const primary of [null, { input_id: 'pending' }]) {
    for (const cancelling of [false, true]) {
      for (const activeRunId of [null, 'running']) {
        const html = await renderToString(createSSRApp({
          data: () => ({
            primaryQueuedInput: primary,
            currentThreadState: { activeRunId },
            cancellingInputIds: new Set(cancelling ? ['pending'] : []),
            handleCancelQueuedInput() {}
          }),
          components: { X: { template: '<span />' } },
          render: renderCancel
        }))
        const visible = Boolean(primary) && !activeRunId
        assert.equal(html.includes('取消这条待处理输入'), visible, 'Run 已启动时使用停止运行入口')
        assert.equal(html.includes(' disabled'), visible && cancelling)
      }
    }
  }
})

test('仅有 warnings 时状态面板展示警告，警告清除后恢复空态', () => {
  const currentAgentState = ref({ warnings: [
    { code: 'mcp_unavailable', source: 'mcp:attendance', message: '考勤未连接' },
    { code: 'mcp_unavailable', source: 'mcp:github', message: 'GitHub 未连接' }
  ] })
  const expression = source.slice(
    source.indexOf('const hasVisibleStateSections ='),
    source.indexOf('const { mentionConfig }')
  )
  const visible = new Function(
    'computed', 'currentAgentState', 'currentTokenUsage', 'currentStateFiles',
    'currentArtifactFiles', 'cooperationSessions',
    `${expression}; return hasVisibleStateSections`
  )(computed, currentAgentState, ref(null), ref([]), ref([]), ref([]))
  assert.equal(visible.value, true)
  currentAgentState.value = { warnings: [] }
  assert.equal(visible.value, false)
})

test('状态警告逐条渲染安全文本，空列表不显示警告区域', async () => {
  const start = source.indexOf('<section v-if="currentAgentState?.warnings?.length"')
  const renderWarnings = compile(source.slice(start, source.indexOf('</section>', start) + '</section>'.length))
  const warnings = [
    { code: 'mcp_unavailable', source: 'mcp:attendance', message: '考勤未连接' },
    { code: 'mcp_unavailable', source: 'mcp:github', message: 'GitHub <连接失败>' }
  ]
  const renderState = (values) => renderToString(createSSRApp({
    data: () => ({ currentAgentState: { warnings: values } }),
    render: renderWarnings
  }))
  const html = await renderState(warnings)
  assert.equal((html.match(/<p>/g) || []).length, 2)
  assert.ok(html.includes('考勤未连接'))
  assert.ok(html.includes('GitHub &lt;连接失败&gt;'))
  assert.ok(!(await renderState([])).includes('state-warning'))
})
