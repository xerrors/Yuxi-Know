import assert from 'node:assert/strict'
import test from 'node:test'
import { groupMarkdownReferences } from '../../src/shared/lib/markdownReferences.js'

function block(start, end, children = []) {
  return {
    dataset: { sourceStart: String(start), sourceEnd: String(end), referenceStart: String(start), referenceEnd: String(end) },
    contains(other) { return children.some((child) => child === other || child.contains(other)) }
  }
}

test('同段多个引用合并为一组，嵌套容器不成为整段高亮目标', () => {
  const first = block(3, 3), second = block(5, 5)
  const list = block(3, 5, [first, second])
  const citations = [
    { answer_start_line: 3, answer_end_line: 3, source_id: 's1' },
    { answer_start_line: 3, answer_end_line: 3, source_id: 's2' },
    { answer_start_line: 5, answer_end_line: 5, source_id: 's3' }
  ]
  const groups = groupMarkdownReferences([list, first, second], citations)
  assert.equal(groups.size, 2)
  assert.deepEqual(groups.get(first).indices, [0, 1])
  assert.deepEqual([...groups.get(first).blocks], [first])
  assert.deepEqual(groups.get(second).indices, [2])
  assert.equal(groups.has(list), false)
})

test('跨段引用只在最后一段放胶囊，保留完整正文范围', () => {
  const first = block(3, 3), second = block(5, 5)
  const groups = groupMarkdownReferences([first, second], [
    { answer_start_line: 3, answer_end_line: 5 }
  ])
  assert.deepEqual([...groups.keys()], [second])
  assert.deepEqual([...groups.get(second).blocks], [first, second])
})

test('无法匹配原文的范围不落到相邻段落或空胶囊', () => {
  assert.equal(groupMarkdownReferences([block(3, 3)], [
    { answer_start_line: 9, answer_end_line: 10 }
  ]).size, 0)
})

test('跨代码、公式或组件的旧引用不能挂到相邻正文或列表容器', () => {
  const paragraph = block(1, 1)
  const excluded = block(3, 5)
  const after = block(7, 7)
  const citations = [
    { answer_start_line: 3, answer_end_line: 5 },
    { answer_start_line: 1, answer_end_line: 7 },
    { answer_start_line: 7, answer_end_line: 7 }
  ]
  const groups = groupMarkdownReferences([paragraph, after], citations, [excluded])
  assert.deepEqual([...groups.keys()], [after])
  assert.deepEqual(groups.get(after).indices, [2])
})
