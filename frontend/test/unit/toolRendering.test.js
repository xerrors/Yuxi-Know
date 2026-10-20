import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { after, before, test } from 'node:test'
import { createTestServer } from '../helpers/createTestServer.js'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

let server
let BaseToolCall
let ToolCallRenderer
let ReasoningBlock
let ToolCallsGroup
let parseToolCallResult
let ReadFileTool
let ImageTool
let QueryKbTool

before(async () => {
  globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
  globalThis.document = {
    documentElement: { classList: { add() {}, remove() {} } },
    getElementsByTagName: () => []
  }
  globalThis.window = { addEventListener() {}, removeEventListener() {} }
  server = await createTestServer({
    root: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..'),
    server: { middlewareMode: true }
  })
  ;({ default: BaseToolCall } = await server.ssrLoadModule(
    '/src/modules/session/ui/tools/BaseToolCall.vue'
  ))
  ;({ default: ReadFileTool } = await server.ssrLoadModule(
    '/src/modules/session/ui/tools/renderers/ReadFileTool.vue'
  ))
  ;({ default: ImageTool } = await server.ssrLoadModule(
    '/src/modules/session/ui/tools/renderers/ImageTool.vue'
  ))
  ;({ default: QueryKbTool } = await server.ssrLoadModule(
    '/src/modules/session/ui/tools/renderers/QueryKbTool.vue'
  ))
  ;({ default: ToolCallRenderer } = await server.ssrLoadModule(
    '/src/modules/session/ui/tools/ToolCallRenderer.vue'
  ))
  ;({ default: ReasoningBlock } = await server.ssrLoadModule(
    '/src/modules/session/ui/ReasoningBlockComponent.vue'
  ))
  ;({ default: ToolCallsGroup } = await server.ssrLoadModule(
    '/src/modules/session/ui/ToolCallsGroupComponent.vue'
  ))
  ;({ parseToolCallResult } = await server.ssrLoadModule(
    '/src/modules/session/ui/tools/toolRegistry.js'
  ))
})

after(async () => {
  await server?.close()
  delete globalThis.localStorage
  delete globalThis.document
  delete globalThis.window
})

/** 渲染真实组件并检查用户可见状态与结果。 */
const render = (component, props) =>
  renderToString(
    createSSRApp({ render: () => h(component, props) })
      .use(createPinia())
      .use(createRouter({ history: createMemoryHistory(), routes: [] }))
  )

for (const [name, fields] of Object.entries({
  调用错误且没有结果: { status: 'error', error_message: '无法执行' },
  调用错误且结果为空: {
    status: 'error',
    error_message: '无法执行',
    tool_call_result: { content: '' }
  },
  'failed 状态': { status: 'failed', error_message: '无法执行' },
  结果别名错误: { result: '{"status":"error","message":"无法执行"}' },
  调用错误同时有结果: { status: 'error', tool_call_result: { content: '无法执行' } },
  'ToolMessage 错误': { tool_call_result: { status: 'error', content: '无法执行' } },
  'JSON 业务错误': {
    tool_call_result: { status: 'success', content: '{"status":"error","message":"无法执行"}' }
  },
  对象业务错误: { tool_call_result: { content: { status: 'error', message: '无法执行' } } }
})) {
  test(`${name} 显示失败图标、失败文案和错误详情`, async () => {
    const toolCall = { id: 'failed-call', name: 'unknown_tool', args: {}, ...fields }
    const html = await render(BaseToolCall, {
      toolCall,
      defaultExpanded: true,
      appearance: 'timeline'
    })
    assert.match(html, /tool-error/)
    assert.match(html, /执行失败/)
    assert.match(html, /无法执行/)
    assert.doesNotMatch(html, /执行完成|tool-loading/)
    const group = await render(ToolCallsGroup, { toolCalls: [toolCall], isActive: true })
    assert.match(group, /1 失败/)
    assert.doesNotMatch(group, /1 进行中/)
  })
}

test('知识库专用模板保留错误详情，不把错误渲染成空检索结果', async () => {
  const html = await render(ToolCallRenderer, {
    toolCall: {
      id: 'kb-error',
      name: 'query_kb',
      args: {},
      tool_call_result: { status: 'error', content: '{"status":"error","message":"知识库不可用"}' }
    },
    defaultExpanded: true
  })
  assert.match(html, /tool-error/)
  assert.match(html, /知识库不可用/)
  assert.doesNotMatch(html, /未找到相关内容|未找到结果/)
})

test('历史搜索额度失败的卡片与汇总均显示失败，真实零结果保留空状态', async () => {
  for (const name of ['web_search', 'tavily_search', 'doubao_search']) {
    const toolCall = {
      id: 'search-quota', name, args: { query: '官方资料' }, status: 'completed',
      tool_call_result: {
        status: 'success',
        content: JSON.stringify({ query: '官方资料', results: [], error: 'Daily search package quota has been exhausted.' })
      }
    }
    const html = await render(ToolCallRenderer, { toolCall, defaultExpanded: true })
    assert.match(html, /tool-error/)
    assert.match(html, /quota has been exhausted/)
    assert.doesNotMatch(html, /未找到相关搜索结果|tool-success/)
    const group = await render(ToolCallsGroup, { toolCalls: [toolCall], isActive: false })
    assert.match(group, /1 失败/)
  }
  const empty = await render(ToolCallRenderer, {
    toolCall: { name: 'web_search', result: { query: '官方资料', results: [], error: null } },
    defaultExpanded: true
  })
  assert.match(empty, /未找到相关搜索结果/)
  assert.match(empty, /tool-success/)
  assert.doesNotMatch(empty, /tool-error/)
  const ordinary = await render(BaseToolCall, {
    toolCall: { name: 'unknown_tool', result: { error: '业务数据中的字段' } },
    defaultExpanded: true
  })
  assert.match(ordinary, /tool-success/)
})

test('有效的 0 和 false 结果可见，普通结果文本中的 error 不冒充状态', async () => {
  for (const content of [0, false, 'status: error', { rows: [{ status: 'error' }] }]) {
    const html = await render(BaseToolCall, {
      toolCall: { name: 'unknown_tool', tool_call_result: { content } },
      defaultExpanded: true
    })
    assert.match(html, /tool-success/)
    assert.match(html, /tool-result-renderer/)
    assert.doesNotMatch(html, /tool-error/)
  }
})

test('工具结果中的图片块按顺序渲染，编码不会作为文本显示', async () => {
  const image = { type: 'image', base64: 'cGljdHVyZQ==', mime_type: 'image/png' }
  for (const content of [
    [image],
    'data:image/png;base64,cGljdHVyZQ==',
    JSON.stringify([{ type: 'text', text: '读取完成' }, image, { type: 'text', text: '后续说明' }]),
    [{ type: 'input_image', image_url: 'data:image/png;base64,cGljdHVyZQ==' }],
    [{ type: 'image', data: 'cGljdHVyZQ==', mimeType: 'image/png' }]
  ]) {
    const html = await render(BaseToolCall, {
      toolCall: { name: 'read_file', tool_call_result: { content } },
      defaultExpanded: true
    })
    assert.match(html, /<img[^>]+src="data:image\/png;base64,cGljdHVyZQ=="/)
    assert.match(html, /aria-label="放大查看工具结果图片/)
    assert.doesNotMatch(html, /<pre[^>]*>[^<]*cGljdHVyZQ==/)
    if (typeof content === 'string' && content.startsWith('[')) {
      assert.ok(html.indexOf('读取完成') < html.indexOf('<img'))
      assert.ok(html.indexOf('后续说明') > html.indexOf('<img'))
    }
  }
})

test('图片来源不可用时给出提示，普通对象仍显示 JSON', async () => {
  for (const image of [
    { type: 'image', base64: 'private-image-payload' },
    { type: 'image_url', image_url: { url: 'javascript:alert(1)' } }
  ]) {
    const html = await render(BaseToolCall, {
      toolCall: { name: 'read_file', result: [image] },
      defaultExpanded: true
    })
    assert.match(html, /图片无法加载/)
    assert.doesNotMatch(html, /private-image-payload|javascript:|<img/)
  }
  const html = await render(BaseToolCall, {
    toolCall: { name: 'read_file', result: { rows: [1, 2] } },
    defaultExpanded: true
  })
  assert.match(html, /rows/)
  assert.doesNotMatch(html, /<img/)
})

test('实际图片结果显示查看图片和图片图标，隐藏文件名与路径参数', async () => {
  const args = { file_path: '/workspace/private/screenshot.png' }
  const html = await render(ReadFileTool, {
    toolCall: {
      name: 'read_file',
      args,
      result: JSON.stringify([{ type: 'image', base64: 'cGljdHVyZQ==', mime_type: 'image/png' }])
    },
    defaultExpanded: true
  })
  assert.match(html, /查看图片/)
  assert.match(html, /lucide-image/)
  assert.doesNotMatch(html, /读取文件|screenshot\.png|file_path|参数:/)

  for (const result of ['普通文件内容', '图片读取失败']) {
    const html = await render(ReadFileTool, {
      toolCall: {
        name: 'read_file',
        args,
        result,
        status: result === '图片读取失败' ? 'error' : 'completed'
      },
      defaultExpanded: true
    })
    assert.match(html, /读取文件/)
    assert.match(html, /screenshot\.png/)
    assert.match(html, /file_path/)
    assert.doesNotMatch(html, /查看图片/)
  }
})

test('生成图片工具的普通 URL 和内联图片共用图片结果，普通文本不会丢失', async () => {
  for (const content of ['https://example.com/image.png', 'data:image/png;base64,cGljdHVyZQ==']) {
    const html = await render(ImageTool, {
      toolCall: { name: 'image_gen', tool_call_result: { content } },
      defaultExpanded: true
    })
    assert.match(html, /<img/)
    assert.match(html, /放大查看工具结果图片/)
  }
  const html = await render(ImageTool, {
    toolCall: { name: 'image_gen', result: '未生成图片' },
    defaultExpanded: true
  })
  assert.match(html, /未生成图片/)
  assert.doesNotMatch(html, /<img/)
})

test('协作工具保留 0 和 false 结果', async () => {
  for (const [name, content] of [
    ['create_session', 0],
    ['create_session', false],
    ['list_sessions', 0],
    ['list_sessions', false]
  ]) {
    const html = await render(ToolCallRenderer, {
      toolCall: { name, tool_call_result: { content } },
      defaultExpanded: true
    })
    assert.equal(parseToolCallResult({ tool_call_result: { content } }), content)
    assert.match(html, /tool-result/)
    assert.match(html, /tool-success/)
  }
})

test('明确的 ToolMessage 错误不会被专用工具覆盖为完成', async () => {
  for (const name of ['create_session', 'subagent_start']) {
    const html = await render(ToolCallRenderer, {
      toolCall: {
        id: 'cooperation-error',
        name,
        args: {},
        tool_call_result: { status: 'error', content: '{"status":"started","message":"启动失败"}' }
      },
      defaultExpanded: true
    })
    assert.match(html, /tool-error/)
    assert.match(html, /启动失败/)
    assert.doesNotMatch(html, /已完成|已启动/)
    assert.match(html, /失败/)
  }
  const html = await render(BaseToolCall, {
    toolCall: { status: 'error', error_message: '调用失败' },
    status: 'completed'
  })
  assert.match(html, /tool-error/)
  assert.doesNotMatch(html, /执行完成/)
})

test('思考描述显示最后一行，展开后保留完整内容', async () => {
  const content = '先检查文件。\n再确认结果。'
  const html = await render(ReasoningBlock, { content, isActive: true })
  assert.match(html, /is-timeline/)
  assert.match(html, /lucide-brain/)
  assert.match(html, /思考/)
  assert.match(html, /再确认结果。/)
  assert.doesNotMatch(html, /先检查文件。/)
  assert.match(html, /aria-expanded="false"/)
  assert.doesNotMatch(html, /<p class="reasoning-content"/)
  const expanded = await render(ReasoningBlock, { content, defaultExpanded: true })
  assert.match(expanded, /<p class="reasoning-content"/)
  assert.match(expanded, /先检查文件。\n再确认结果。/)
  for (const text of [
    '先检查文件。\r\n再确认结果。\r\n  ',
    '再确认结果。',
    '先检查文件。\r再确认结果。'
  ]) {
    const preview = await render(ReasoningBlock, { content: text, isActive: true })
    assert.match(preview, /再确认结果。/)
    assert.doesNotMatch(preview, /先检查文件。/)
  }
})

test('派发成功保留工具结果，后续会话失败由协作状态展示', async () => {
  const toolCall = {
    name: 'create_session',
    args: {},
    tool_call_result: { content: { status: 'accepted', session_id: 'child', turn_id: 'turn' } }
  }
  const row = await render(ToolCallRenderer, { toolCall })
  assert.match(row, /tool-success/)
  assert.doesNotMatch(row, /tool-error/)
})

test('知识库列表错误不显示暂无知识库', async () => {
  const html = await render(ToolCallRenderer, {
    toolCall: {
      name: 'list_kbs',
      args: {},
      tool_call_result: { status: 'error', content: '列表读取失败' }
    },
    defaultExpanded: true
  })
  assert.match(html, /执行失败/)
  assert.match(html, /列表读取失败/)
  assert.doesNotMatch(html, /暂无知识库/)
})

test('incomplete 工具显示中断终态而非加载图标', async () => {
  const html = await render(BaseToolCall, {
    toolCall: { id: 'stopped', name: 'execute', args: {}, status: 'incomplete' },
    defaultExpanded: true,
    appearance: 'timeline'
  })
  assert.match(html, /已中断/)
  assert.doesNotMatch(html, /tool-loading|正在调用工具/)
  const question = await render(ToolCallRenderer, {
    toolCall: {
      id: 'question',
      name: 'ask_user_question',
      args: { questions: [] },
      status: 'incomplete'
    }
  })
  assert.match(question, /已中断/)
  assert.doesNotMatch(question, /tool-loading/)
})


test('知识库检索失败显示错误结果，正常空检索仍显示空状态', async () => {
  const failure = await render(QueryKbTool, {
    toolCall: { name: 'query_kb', tool_call_result: { status: 'error', content: '工具 query_kb 执行失败：RuntimeError' } },
    defaultExpanded: true
  })
  assert.match(failure, /tool-error/)
  assert.match(failure, /query_kb 执行失败/)
  assert.doesNotMatch(failure, /未找到相关知识库内容/)
  const empty = await render(QueryKbTool, {
    toolCall: { name: 'query_kb', tool_call_result: { status: 'success', content: '{"results":[]}' } },
    defaultExpanded: true
  })
  assert.match(empty, /未找到相关知识库内容/)
  assert.doesNotMatch(empty, /tool-error/)
})
