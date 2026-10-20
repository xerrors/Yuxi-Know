import assert from 'node:assert/strict'
import test, { after, before } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createTestServer } from '../helpers/createTestServer.js'

let mentionUtils
let server

before(async () => {
  server = await createTestServer({
    root: fileURLToPath(new URL('../..', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom'
  })
  mentionUtils = await server.ssrLoadModule('/src/modules/session/model/mention_utils.js')
})

after(async () => {
  await server?.close()
})

test('删除无空格相邻正文前的 mention 时使用 chip 边界', () => {
  const { expandMentionDeletionRange, parseMentionText } = mentionUtils
  const text = '@knowledge:示例知识库这个知识库有什么作用'
  const mentionEnd = '@knowledge:示例知识库'.length

  assert.deepEqual(parseMentionText(text), [
    {
      kind: 'mention',
      raw: text,
      type: 'knowledge',
      value: '示例知识库这个知识库有什么作用',
      start: 0,
      end: text.length
    }
  ])
  assert.deepEqual(
    expandMentionDeletionRange(text, mentionEnd, mentionEnd, 'backward', [
      { start: 0, end: mentionEnd }
    ]),
    { start: 0, end: mentionEnd }
  )
})

test('没有 chip 边界时仍按文本 mention 解析删除', () => {
  const { expandMentionDeletionRange } = mentionUtils
  const text = '@knowledge:"示例知识库" 后文'
  const mentionEnd = '@knowledge:"示例知识库"'.length

  assert.deepEqual(expandMentionDeletionRange(text, mentionEnd, mentionEnd), {
    start: 0,
    end: mentionEnd
  })
})

test('智能体引用保存稳定 ID，同名智能体仍保持独立且可以整体删除', async () => {
  const { buildMentionResourceItems } = await server.ssrLoadModule(
    '/src/modules/session/model/mention_resource_items.js'
  )
  const {
    formatMentionToken,
    parseMentionText,
    buildMentionDisplayLabels,
    getMentionDisplayLabel,
    expandMentionDeletionRange
  } = mentionUtils
  const mention = {
    agents: [
      { agent_id: 'research-a', name: '研究员', description: '研究资料' },
      { agent_id: 'research-b', name: '研究员', description: '核对结果' }
    ]
  }
  const items = buildMentionResourceItems(mention).agents
  assert.deepEqual(
    items.map((item) => item.value),
    ['research-a', 'research-b']
  )
  const text = formatMentionToken(items[1].type, items[1].value)
  assert.equal(text, '@agent:research-b')
  const [segment] = parseMentionText(text)
  assert.equal(segment.type, 'agent')
  assert.equal(segment.value, 'research-b')
  assert.equal(
    getMentionDisplayLabel(segment.type, segment.value, buildMentionDisplayLabels(mention)),
    '研究员'
  )
  assert.deepEqual(expandMentionDeletionRange(text, text.length), { start: 0, end: text.length })
  assert.equal(mentionUtils.findActiveMentionQuery(text, text.length), null)
})
