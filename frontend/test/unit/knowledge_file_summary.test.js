import assert from 'node:assert/strict'
import test from 'node:test'
import { fileAttention, fileFailureReason } from '../../src/modules/knowledge/model/fileSummary.js'

test('失败在其他目录仍以全库计数显示，错误严重度高于待处理和处理中', () => {
  const summary = fileAttention({ file_status_counts: { error_parsing: 2, parsed: 9, parsing: 1, indexed: 30 } })
  assert.equal(summary.tone, 'error')
  assert.equal(summary.total, 12)
  assert.deepEqual(summary.rows.map(({ label, count }) => [label, count]), [['解析失败', 2], ['待入库', 9], ['解析中', 1]])
})

test('健康或空库隐藏入口，待处理高于处理中；历史失败不能隐身或重复计数', () => {
  assert.deepEqual(fileAttention({ file_status_counts: { indexed: 20, done: 8 } }).rows, [])
  assert.equal(fileAttention().total, 0)
  assert.equal(fileAttention({ file_status_counts: { uploaded: 1, indexing: 2 } }).tone, 'warning')
  assert.equal(fileAttention({ file_status_counts: { indexing: 2 } }).tone, 'info')
  const failures = fileAttention({ file_status_counts: { failed: 1, error_indexing: 2 } })
  assert.equal(failures.rows.length, 1)
  assert.equal(failures.rows[0].count, 3)
  assert.equal(failures.tone, 'error')
  assert.equal(fileAttention({ file_status_counts: { unexpected: 1 } }).tone, 'warning')
})

test('长错误保留换行与特殊字符，缺失原因明确提示', () => {
  const reason = '<parser>\n' + '原因'.repeat(1000)
  assert.equal(fileFailureReason({ error_message: reason }), reason)
  assert.match(fileFailureReason({ error_message: '  ' }), /未记录失败原因/)
  assert.match(fileFailureReason({}), /未记录失败原因/)
})
