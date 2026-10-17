import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { computed, reactive, ref } from 'vue'
import { widgetFormMessage } from '../../src/shared/lib/chatWidgets.js'

const workspace = readFileSync(
  new URL('../../src/modules/session/ui/SessionWorkspace.vue', import.meta.url),
  'utf8'
)
const renderer = readFileSync(
  new URL('../../src/shared/ui/WidgetRenderer.vue', import.meta.url),
  'utf8'
)
const node = readFileSync(new URL('../../src/shared/ui/WidgetNode.vue', import.meta.url), 'utf8')

/** 执行真实提交入口，检查表单与编辑器的提交快照互不混用。 */
function setupSender() {
  const sent = []
  const deps = {
    computed,
    props: reactive({ sendDisabled: false }),
    isLoadingMessages: ref(false),
    isProcessing: ref(false),
    isWaitingForUserAction: ref(false),
    sendCooldownActive: ref(false),
    pendingSends: ref({}),
    currentChatId: ref('thread'),
    currentAgent: ref({ id: 'agent' }),
    userInput: ref('尚未发送的草稿'),
    currentPendingThreadAttachments: ref([{ id: 'attachment' }]),
    currentModelSpec: ref('model'),
    currentToolApprovalMode: ref('request'),
    startSendCooldown() {},
    sessionInput: {
      async send(thread, draft, options) {
        sent.push({ thread, draft, options })
        return true
      }
    }
  }
  const source = workspace.slice(
    workspace.indexOf('const widgetActionsDisabled ='),
    workspace.indexOf('const handleDirectSteer =')
  )
  const functions = new Function(
    ...Object.keys(deps),
    `${source}; return { handleSendMessage, widgetActionsDisabled }`
  )(...Object.values(deps))
  return { ...deps, ...functions, sent }
}

test('表单发送独立文本而不带编辑器草稿和附件，普通发送仍带附件', async () => {
  const view = setupSender()
  assert.equal(await view.handleSendMessage({ text: '目的地：南京', fromWidget: true }), true)
  assert.equal(view.sent[0].draft.text, '目的地：南京')
  assert.deepEqual(view.sent[0].draft.attachments, [])
  assert.deepEqual(view.sent[0].draft.images, [])
  assert.equal(view.userInput.value, '尚未发送的草稿')
  assert.deepEqual(view.currentPendingThreadAttachments.value, [{ id: 'attachment' }])
  await view.handleSendMessage()
  assert.equal(view.sent[1].draft.text, '尚未发送的草稿')
  assert.deepEqual(view.sent[1].draft.attachments, [{ id: 'attachment' }])
})

test('等待回答、接收失败和发送禁用不允许表单重复创建输入', async () => {
  const view = setupSender()
  for (const state of [
    view.isWaitingForUserAction,
    view.isLoadingMessages,
    view.sendCooldownActive
  ]) {
    state.value = true
    assert.equal(view.widgetActionsDisabled.value, true)
    assert.equal(await view.handleSendMessage({ text: '答案', fromWidget: true }), false)
    state.value = false
  }
  view.pendingSends.value.thread = { text: '上一次回答' }
  assert.equal(view.widgetActionsDisabled.value, true)
  assert.equal(await view.handleSendMessage({ text: '答案', fromWidget: true }), false)
  assert.deepEqual(view.sent, [])
})

/** 执行真实反馈处理，只有会话确认接收才显示已发送。 */
function setupFeedback(handler) {
  const props = reactive({ disabled: false, actionHandler: handler })
  const values = Object.fromEntries(
    ['feedback', 'submitting', 'submitted', 'failed'].map((key) => [
      key,
      ref(key === 'feedback' ? '' : false)
    ])
  )
  const source = renderer.slice(
    renderer.indexOf('async function handleAction('),
    renderer.indexOf('</script>')
  )
  const handle = new Function('props', ...Object.keys(values), `${source}; return handleAction`)(
    props,
    ...Object.values(values)
  )
  return { ...values, props, handle }
}

test('提交中阻止重复操作，接收后显示已发送，错误允许重试', async () => {
  let accept
  const view = setupFeedback(
    () =>
      new Promise((resolve) => {
        accept = resolve
      })
  )
  const pending = view.handle({ type: 'send_message', text: '填写结果' })
  assert.equal(view.submitting.value, true)
  assert.equal(view.feedback.value, '正在发送…')
  assert.equal(view.submitted.value, false)
  await view.handle({ type: 'send_message', text: '重复提交' })
  accept(true)
  await pending
  assert.equal(view.submitted.value, true)
  assert.equal(view.feedback.value, '已发送')
  const rejected = setupFeedback(async () => false)
  await rejected.handle({ type: 'send_message', text: '填写结果' })
  assert.equal(rejected.failed.value, true)
  assert.equal(rejected.submitted.value, false)
  assert.match(rejected.feedback.value, /未能发送/)
  rejected.props.actionHandler = async () => true
  await rejected.handle({ type: 'send_message', text: '填写结果' })
  assert.equal(rejected.feedback.value, '已发送')
})

test('保留旧草稿动作，不把草稿反馈成已发送', async () => {
  const view = setupFeedback(() => undefined)
  await view.handle('续聊草稿')
  assert.equal(view.submitted.value, false)
  assert.equal(view.feedback.value, '已填写到消息草稿，请检查后发送。')
})

test('同一输入经会话重试接收后，原表单消除失败提示并显示已发送', async () => {
  let submission
  const view = setupFeedback(async (action) => {
    submission = action
    return false
  })
  await view.handle({ type: 'send_message', text: '用户回答' })
  assert.equal(view.failed.value, true)
  submission.onAccepted()
  assert.equal(view.submitted.value, true)
  assert.equal(view.failed.value, false)
  assert.equal(view.feedback.value, '已发送')
})

test('合法字段名 reportValidity 遮蔽表单属性时仍使用原生校验，非法输入不发送', () => {
  const actions = []
  const props = {
    disabled: false,
    node: {
      type: 'Form',
      onSubmitAction: { type: 'send_message', payload: { text: '请确认结果。' } },
      children: [{ type: 'Input', name: 'reportValidity', label: '验证结果', required: true }]
    }
  }
  const formError = ref('')
  const source = node.slice(node.indexOf('function submitForm('), node.indexOf('/** 提交按钮'))
  const submit = new Function(
    'props',
    'HTMLFormElement',
    'formError',
    'widgetFormMessage',
    'FormData',
    'emit',
    `${source}; return submitForm`
  )(
    props,
    {
      prototype: {
        reportValidity() {
          return this.valid
        }
      }
    },
    formError,
    widgetFormMessage,
    class {
      constructor(form) {
        return form.entries
      }
    },
    (...action) => actions.push(action)
  )
  const form = {
    reportValidity: { name: 'reportValidity' },
    valid: true,
    entries: [['reportValidity', '符合要求']]
  }
  assert.doesNotThrow(() => submit({ currentTarget: form }))
  assert.deepEqual(actions, [
    ['action', { type: 'send_message', text: '请确认结果。\n验证结果：符合要求' }]
  ])
  form.valid = false
  submit({ currentTarget: form })
  assert.equal(actions.length, 1)
  form.valid = true
  form.entries[0][1] = ' '
  submit({ currentTarget: form })
  assert.equal(formError.value, '请填写验证结果')
  assert.equal(actions.length, 1)
})
