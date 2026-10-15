import assert from 'node:assert/strict'
import test from 'node:test'

import { createMarkdownRenderer } from '../../src/shared/lib/markdown_preview.js'

test('无代码高亮器时 Markdown 仍保留结构化渲染', () => {
  const renderer = createMarkdownRenderer({ themeName: 'github-light', highlighter: null })
  const html = renderer.render('# Skill\n\n```python\nprint(42)\n```')
  assert.match(html, /<h1>Skill<\/h1>/)
  assert.match(html, /<pre><code/)
})

test('定位预览保留空行后的标题、正文与代码块原始行号', () => {
  const renderer = createMarkdownRenderer({ themeName: 'github-light', highlighter: null })
  const content = '# 标题\n\n正文\n\n```txt\n代码\n```'
  const html = renderer.render(content, { sourceLines: true })
  assert.match(html, /<h1 data-source-start="1" data-source-end="1">/)
  assert.match(html, /<p data-source-start="3" data-source-end="3">/)
  assert.match(html, /<div data-source-start="5" data-source-end="7"><pre>/)
  assert.doesNotMatch(renderer.render(content), /data-source-start/)
})

test('引用映射保留前导空行与 SVG 预览后正文的原始行号', () => {
  const renderer = createMarkdownRenderer({ themeName: 'github-light', highlighter: null })
  const content = '\n\n结论。\n\n```svg\n<svg><text>图示</text></svg>\n```\n\n后续结论。'
  const html = renderer.render(content, { sourceLines: true })
  assert.match(html, /<p data-source-start="3" data-source-end="3">结论。/)
  assert.match(html, /<div data-source-start="5" data-source-end="7"><div class="svg-inline-render">/)
  assert.match(html, /<p data-source-start="9" data-source-end="9">后续结论。/)
  assert.doesNotMatch(html, /language-svg/)
})

test('frontmatter 保留多行字段的 YAML 缩进', () => {
  const renderer = createMarkdownRenderer({ themeName: 'github-light', highlighter: null })
  const html = renderer.render(`---
name: minimax-pdf
description:
  Use this skill when visual quality and design identity matter for a PDF.
  CREATE (generate from scratch): "make a PDF", "generate a report".
license: MIT
metadata:
  version: "1.0"
  category: document-generation
---
`)

  assert.match(html, /class="frontmatter-card"/)
  assert.match(html, /minimax-pdf/)
  assert.match(html, /Use this skill when visual quality and design identity matter for a PDF\./)
  assert.match(html, /document-generation/)
})

test('relative document images resolve beside their artifact with the same authorization boundary', async () => {
  const { resolveMarkdownImageUrl } = await import('../../src/shared/lib/markdown_preview.js')
  const base = '/api/v1/agents/sessions/thread-1/artifacts/home/user/workspace/project/parsed/document.md'
  const origin = 'https://yuxi.example'
  assert.equal(
    resolveMarkdownImageUrl('images/chart.png', base, origin),
    '/api/v1/agents/sessions/thread-1/artifacts/home/user/workspace/project/parsed/images/chart.png'
  )
  assert.equal(resolveMarkdownImageUrl('images/chart.png', '', origin), null)
  assert.equal(resolveMarkdownImageUrl('https://outside.example/api/knowledge/knowledge-bases/a/images/x.png', base, origin), null)
  assert.equal(resolveMarkdownImageUrl('//outside.example/x.png', base, origin), null)
  assert.equal(resolveMarkdownImageUrl('/api/knowledge/knowledge-bases/kb/images/kb-images/chart.png', '', origin), '/api/knowledge/knowledge-bases/kb/images/kb-images/chart.png')
})
