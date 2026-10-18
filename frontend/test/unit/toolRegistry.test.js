import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { parseToolCallArgs } from '../../src/modules/session/ui/tools/toolRegistry.js'

const ARG_PARSER_CONSUMERS = [
  'AskUserQuestionTool.vue',
  'EditFileTool.vue',
  'ExecuteTool.vue',
  'FindKbDocumentTool.vue',
  'GlobTool.vue',
  'GrepTool.vue',
  'ListDirectoryTool.vue',
  'OpenKbDocumentTool.vue',
  'QueryKbTool.vue',
  'ReadFileTool.vue',
  'SearchFileContentTool.vue',
  'SearchFileTool.vue',
  'WebSearchTool.vue',
  'WriteFileTool.vue'
]

const COMPONENTS_WITHOUT_OTHER_JSON_PARSING = ARG_PARSER_CONSUMERS.filter(
  (component) => !['AskUserQuestionTool.vue', 'WebSearchTool.vue'].includes(component)
)

test('parseToolCallArgs 以显式 args 值为准并支持对象参数', () => {
  const objectArgs = { query: 'object' }

  assert.deepEqual(parseToolCallArgs({ args: { query: 'args' } }), { query: 'args' })
  assert.strictEqual(parseToolCallArgs({ args: objectArgs }), objectArgs)
  assert.deepEqual(parseToolCallArgs({ function: { arguments: '{"query":"function"}' } }), {
    query: 'function'
  })
})

test('parseToolCallArgs 对空字符串和 malformed JSON 不回退到 function.arguments', () => {
  const functionArgs = { function: { arguments: '{"query":"function"}' } }

  assert.deepEqual(parseToolCallArgs({ args: '', ...functionArgs }), {})
  assert.deepEqual(parseToolCallArgs({ args: '{', ...functionArgs }), {})
})

test('工具组件统一消费 parseToolCallArgs，不保留本地参数解析器', () => {
  for (const component of ARG_PARSER_CONSUMERS) {
    const source = readFileSync(
      new URL(`../../src/modules/session/ui/tools/renderers/${component}`, import.meta.url),
      'utf8'
    )

    assert.match(source, /import \{[\s\S]*parseToolCallArgs[\s\S]*\} from '\.\.\/toolRegistry'/, component)
    assert.doesNotMatch(
      source,
      /props\.toolCall\.args\s*(?:\|\||\?\?)\s*props\.toolCall\.function\?\.arguments/,
      component
    )
  }

  for (const component of COMPONENTS_WITHOUT_OTHER_JSON_PARSING) {
    const source = readFileSync(
      new URL(`../../src/modules/session/ui/tools/renderers/${component}`, import.meta.url),
      'utf8'
    )

    assert.doesNotMatch(source, /JSON\.parse\((?:args|value)\)/, component)
  }
})
