import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { after, before, test } from 'node:test'
import { createTestServer } from '../helpers/createTestServer.js'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'

let server
let QueryResultChunk

before(async () => {
  server = await createTestServer({
    root: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..'),
    server: { middlewareMode: true }
  })
  ;({ default: QueryResultChunk } = await server.ssrLoadModule(
    '/src/modules/knowledge/ui/QueryResultChunk.vue'
  ))
})

after(async () => server?.close())

/** 渲染实际检索片段，验证评分与不可信文本的用户可见结果。 */
function render(chunk) {
  return renderToString(createSSRApp({ render: () => h(QueryResultChunk, { chunk, index: 0 }) }))
}

for (const [scoreType, label, score] of [
  ['bm25', '关键词相关度', 12.3],
  ['cosine', '向量相似度', 0],
  ['hybrid', '混合检索分数', 0.8],
  ['fusion', '融合排名分数', 0.01]
]) {
  test(`${label} 展示原始分数，零分仍可见`, async () => {
    const html = await render({ score_type: scoreType, score, content: '正文' })
    assert.match(html, new RegExp(`${label}: ${score.toFixed(4)}`))
    assert.doesNotMatch(html, /%/)
  })
}

test('高亮和完整正文中的 HTML 保持文字，只有命中段生成 mark', async () => {
  const html = await render({
    score_type: 'bm25',
    score: 4,
    content: '<script>alert(1)</script>完整正文',
    highlights: [
      [
        { text: '<img src=x onerror=alert(1)>', matched: false },
        { text: 'Milvus', matched: true }
      ]
    ]
  })
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/)
  assert.match(html, /<mark[^>]*>Milvus<\/mark>/)
  const fullText = await render({ content: '<script>alert(1)</script>完整正文' })
  assert.match(fullText, /&lt;script&gt;alert\(1\)&lt;\/script&gt;完整正文/)
  assert.doesNotMatch(fullText, /<script/)
  assert.match(html, /展开完整片段/)
  assert.doesNotMatch(html, /<script|<img/)
})

test('普通片段正文保留完整文本并默认限制展示行数', async () => {
  const html = await render({ content: '完整正文', score: 0.2, score_type: 'cosine' })
  assert.match(html, /完整正文/)
  assert.doesNotMatch(html, /<mark|<details/)
  assert.match(html, /class="[^"]*is-collapsed/)
})


test('长文件名使用独立文件按钮，完整名称保留在 title 中', async () => {
  const name = 'Supplementary Information-very-long-file-name.docx'
  const html = await render({ content: '正文', metadata: { file_id: 'file-1', source: name, start_line: 91, end_line: 135 } })
  assert.match(html, /class="result-open"/)
  assert.match(html, new RegExp(`title="${name}"`))
  assert.match(html, /class="result-filename"/)
  assert.match(html, /行 91–135/)
})


test('缺少文件ID时保留来源名称，不提供无法打开的文件按钮', async () => {
  const html = await render({ content: '正文', metadata: { source: '外部来源.md' } })
  assert.match(html, /外部来源.md/)
  assert.doesNotMatch(html, /class="result-open"/)
})
