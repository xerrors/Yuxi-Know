import assert from 'node:assert/strict'
import test from 'node:test'

import {
  WORKSPACE_UPLOAD_MAX_FILE_BYTES,
  buildFolderUploadBatches,
  collectFolderUploadEntries,
  validateFolderUploadEntries
} from '../../src/modules/workspace/model/workspaceFolderUpload.js'

const entry = (relativePath, size = 1) => ({
  file: { name: relativePath.split('/').pop(), size },
  relativePath
})

test('收集文件夹选择时保留 webkitRelativePath 和隐藏文件', () => {
  const visible = { name: 'a.txt', size: 3, webkitRelativePath: 'root/a.txt' }
  const hidden = { name: '.env', size: 4, webkitRelativePath: 'root/.env' }

  assert.deepEqual(collectFolderUploadEntries([visible, hidden]), [
    { file: visible, relativePath: 'root/a.txt' },
    { file: hidden, relativePath: 'root/.env' }
  ])
})

test('缺少相对路径时拒绝继续，避免静默平铺', () => {
  assert.throws(
    () => collectFolderUploadEntries([{ name: 'a.txt', size: 1 }]),
    /无法获取 a\.txt 的文件夹路径/
  )
})

test('保留文件夹名前导空白，不把不同目录合并', () => {
  const file = { name: 'a.txt', size: 1, webkitRelativePath: ' root/sub/a.txt' }

  assert.equal(collectFolderUploadEntries([file])[0].relativePath, ' root/sub/a.txt')
})

test('单文件超过后端上限时提前拒绝', () => {
  const oversized = WORKSPACE_UPLOAD_MAX_FILE_BYTES + 1
  assert.throws(
    () => validateFolderUploadEntries([entry('root/large.bin', oversized)]),
    /超过 100 MB/
  )
  assert.doesNotThrow(() =>
    validateFolderUploadEntries([entry('root/limit.bin', WORKSPACE_UPLOAD_MAX_FILE_BYTES)])
  )
})

test('按文件数量和总字节数分批且保持顺序', () => {
  const entries = [
    entry('root/a.txt', 6),
    entry('root/b.txt', 6),
    entry('root/c.txt', 6),
    entry('root/d.txt', 6),
    entry('root/e.txt', 6)
  ]

  const byCount = buildFolderUploadBatches(entries, { maxFiles: 2, maxBytes: 1000 })
  assert.deepEqual(
    byCount.map((batch) => batch.map((item) => item.relativePath)),
    [['root/a.txt', 'root/b.txt'], ['root/c.txt', 'root/d.txt'], ['root/e.txt']]
  )

  const byBytes = buildFolderUploadBatches(entries, { maxFiles: 50, maxBytes: 12 })
  assert.deepEqual(
    byBytes.map((batch) => batch.map((item) => item.relativePath)),
    [['root/a.txt', 'root/b.txt'], ['root/c.txt', 'root/d.txt'], ['root/e.txt']]
  )
})

test('单个文件超过批次字节预算时独立成批', () => {
  const entries = [entry('root/small.txt', 1), entry('root/large.bin', 30), entry('root/after.txt', 1)]

  const batches = buildFolderUploadBatches(entries, { maxFiles: 50, maxBytes: 18 })

  assert.deepEqual(
    batches.map((batch) => batch.map((item) => item.relativePath)),
    [['root/small.txt'], ['root/large.bin'], ['root/after.txt']]
  )
})

test('空选择不产生批次', () => {
  assert.deepEqual(buildFolderUploadBatches([]), [])
})
