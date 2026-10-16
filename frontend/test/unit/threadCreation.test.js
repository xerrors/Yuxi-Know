import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { computed, reactive, ref } from 'vue'

import { createThreadForContext } from '../../src/modules/session/model/threadCreation.js'

const source = readFileSync(new URL('../../src/modules/session/ui/SessionWorkspace.vue', import.meta.url), 'utf8')

/** 执行同一视图的实际逻辑片段，测试只注入被观察的状态与外部动作。 */
function workspaceLogic(start, end, dependencies, exported) {
  const begin = source.indexOf(start)
  const block = source.slice(begin, source.indexOf(end, begin))
  return new Function(...Object.keys(dependencies), `${block}; return ${exported}`)(...Object.values(dependencies))
}

test('首次发送在创建 Thread 前冻结附件、图片和配置，后来草稿不能并入旧提交', async () => {
  const files = { value: [{ id: 'original-file' }] }
  const model = { value: 'original:model' }, approval = { value: 'default' }
  const images = [{ imageUrl: 'original-image' }]
  let resolveCreation, submitted
  const dependencies = {
    pendingSends: { value: {} }, currentChatId: { value: null }, userInput: { value: '原始输入' },
    currentAgent: { value: {} }, sendCooldownActive: { value: false }, props: { sendDisabled: false },
    isLoadingMessages: { value: false }, isWaitingForUserAction: { value: false },
    currentPendingThreadAttachments: files, currentModelSpec: model, currentToolApprovalMode: approval,
    startSendCooldown() {}, selectedModelByThread: {}, promoteDraftSelection() {},
    ensureActiveThread: () => new Promise((resolve) => { resolveCreation = resolve }),
    sessionInput: { async send(threadId, draft) { submitted = { threadId, draft } } }
  }
  const send = workspaceLogic('const handleSendMessage =', 'const handleDirectSteer =', dependencies, 'handleSendMessage')
  const sending = send({ images })
  files.value.push({ id: 'next-draft-file' })
  images.push({ imageUrl: 'next-draft-image' })
  model.value = 'next:model'
  approval.value = 'always_trust'
  resolveCreation('created-thread')
  await sending
  assert.equal(submitted.threadId, 'created-thread')
  assert.deepEqual(submitted.draft.attachments, [{ id: 'original-file' }])
  assert.deepEqual(submitted.draft.images, [{ imageUrl: 'original-image' }])
  assert.equal(submitted.draft.modelSpec, 'original:model')
  assert.equal(submitted.draft.toolApprovalMode, 'default')
})

test('延迟创建响应遇到上下文切换时不被接受', async () => {
  const context = { agentId: 'agent-a', projectId: 'auto', threadId: null }
  let currentContext = { ...context }
  let resolveRequest
  const response = new Promise((resolve) => {
    resolveRequest = resolve
  })

  const pending = createThreadForContext({
    context,
    getCurrentContext: () => currentContext,
    requestId: 'stable-request',
    create: async (requestId) => {
      assert.equal(requestId, 'stable-request')
      return response
    }
  })

  currentContext = { ...context, agentId: 'agent-b' }
  resolveRequest({ id: 'thread-a' })

  assert.deepEqual(await pending, { thread: { id: 'thread-a' }, accepted: false })
})


for (const uploadTarget of ['__draft__', 'thread-a']) {
  test(`创建响应丢失后重放审批模式，附件目标 ${uploadTarget} 按归属迁移`, async () => {
    const calls = []
    const currentChatId = { value: null }
    const approval = { value: 'default' }
    const request = { value: null }
    const dependencies = {
      currentChatId, currentAgentId: { value: 'agent' }, selectedProjectId: { value: 'auto' },
      threadCreationRequest: request, currentToolApprovalMode: approval, AUTO_PROJECT_ID: 'auto',
      createInputRequestId: () => 'stable-key', createThreadForContext,
      chatThreadsStore: { setThreadCreationInFlight() {}, async createThread(...args) {
        calls.push(structuredClone(args))
        if (calls.length === 1) throw new Error('response lost')
        return { id: 'same-session' }
      } },
      threadMessages: { value: {} },
      getThreadState: () => ({}), threadAttachmentsMap: { value: {} }, draftFilesByThread: { value: {} },
      attachmentUploadThreadKey: ref(uploadTarget), DRAFT_MODEL_KEY: '__draft__',
      promoteDraftSelection() {}, setCurrentThreadId: (id) => { currentChatId.value = id }
    }
    const create = workspaceLogic('const createActiveThread =', 'const ensureActiveThread =', dependencies, 'createActiveThread')
    await assert.rejects(create(), /response lost/)
    approval.value = 'always_trust'
    assert.equal(await create(), 'same-session')
    assert.deepEqual(calls[1], calls[0])
    assert.equal(calls[1][1], null)
    assert.equal(calls[1][2].tool_approval_mode, 'default')
    assert.equal(request.value, null)
    assert.equal(dependencies.attachmentUploadThreadKey.value, uploadTarget === '__draft__' ? 'same-session' : uploadTarget)
  })
}


test('新建会话按稳定 agent_id 找到当前智能体，详情到达后替换列表摘要', () => {
  const dependencies = {
    computed, currentAgentId: ref('slug'), agents: ref([{ agent_id: 'slug', name: '摘要' }]), agentDetails: ref({})
  }
  const agent = workspaceLogic('const currentAgent = computed', 'const currentChatId = computed', dependencies, 'currentAgent')
  assert.equal(agent.value.name, '摘要')
  dependencies.agentDetails.value.slug = { agent_id: 'slug', name: '完整详情' }
  assert.equal(agent.value.name, '完整详情')
  dependencies.currentAgentId.value = 'missing'
  assert.equal(agent.value, null)
})

test('模型选择按当前选择、Session、智能体默认值响应式回退，新建草稿独立', () => {
  const dependencies = {
    computed, selectedModelByThread: reactive({ thread: 'selected:model', __draft__: 'draft:model' }),
    currentChatId: ref('thread'), currentThread: ref({ agent: { model: 'session:model' } }),
    agentDefaultModel: ref('agent:model'), DRAFT_MODEL_KEY: '__draft__'
  }
  const model = workspaceLogic('const currentModelSpec = computed', 'const handleModelSelect =', dependencies, 'currentModelSpec')
  assert.equal(model.value, 'selected:model')
  delete dependencies.selectedModelByThread.thread
  assert.equal(model.value, 'session:model')
  dependencies.currentThread.value = null
  assert.equal(model.value, 'agent:model')
  dependencies.currentChatId.value = null
  assert.equal(model.value, 'draft:model')
})

test('预写 Thread 身份也须加载历史，已有历史的视图只恢复订阅', async () => {
  for (const historyLoaded of [false, true]) {
    const actions = []
    const dependencies = {
      threadCreationInFlight: ref(false), agentStore: { isInitialized: true }, threads: ref([{ id: 'thread' }]),
      currentThreadId: ref('thread'), getThreadState: () => ({ historyLoaded }),
      props: { embedded: false }, workspaceActive: ref(true), chatThreadsStore: { setCurrentThreadId() {} },
      resumeCurrentRunForVisiblePage: async () => actions.push('resume'), selectChat: async id => actions.push(id)
    }
    const select = workspaceLogic('const selectThreadFromRoute =', 'const sessionInput =', dependencies, 'selectThreadFromRoute')
    assert.equal(await select('thread'), true)
    assert.deepEqual(actions, [historyLoaded ? 'resume' : 'thread'])
  }
})


test('附件上传固定打开时的目标，切换会话和再次打开分别保留各自归属', async () => {
  const currentChatId = ref('thread-a')
  const attachmentUploadModalOpen = ref(false)
  const draftFilesByThread = ref({})
  const actions = workspaceLogic('const handleAttachmentUpload =', 'const handleAttachmentRemove =', {
    currentChatId, attachmentUploadModalOpen, draftFilesByThread,
    attachmentUploadThreadKey: ref(null), DRAFT_MODEL_KEY: '__draft__',
    currentAgentId: ref('agent'), AgentValidator: { validateAgentIdWithError: () => true },
    handleValidationError() {}, attachmentInitialFiles: ref([]), attachmentInitialFilesKey: ref(0),
    File: class File {}
  }, '{ open: handleAttachmentUpload, confirm: handleTmpAttachmentsAdded }')
  await actions.open()
  currentChatId.value = 'thread-b'
  await actions.open()
  actions.confirm([{ id: 'file-a' }])
  assert.deepEqual(draftFilesByThread.value, { 'thread-a': [{ id: 'file-a' }] })
  attachmentUploadModalOpen.value = false
  await actions.open()
  actions.confirm([{ id: 'file-b' }])
  assert.deepEqual(draftFilesByThread.value['thread-b'], [{ id: 'file-b' }])
  assert.deepEqual(draftFilesByThread.value['thread-a'], [{ id: 'file-a' }])
})
