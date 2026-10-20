import assert from 'node:assert/strict'
import test, { after, before } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createTestServer } from '../helpers/createTestServer.js'

let parseDownloadFilename
let server

before(async () => {
  server = await createTestServer({
    root: fileURLToPath(new URL('../..', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom'
  })
  ;({ parseDownloadFilename } = await server.ssrLoadModule('/src/shared/lib/file_utils.js'))
})

after(async () => {
  await server?.close()
})

test('parseDownloadFilename 在 filename* 与 filename 并存时优先解码 UTF-8 filename*', () => {
  assert.equal(
    parseDownloadFilename(
      "attachment; filename*=UTF-8''%E6%8A%A5%E5%91%8A.txt; filename=\"fallback.txt\""
    ),
    '报告.txt'
  )
})

test('parseDownloadFilename 解码普通 filename 的 percent encoding', () => {
  assert.equal(
    parseDownloadFilename('attachment; filename="report%20final.txt"'),
    'report final.txt'
  )
  assert.equal(
    parseDownloadFilename("attachment; filename='encoded%20report.txt'"),
    'encoded report.txt'
  )
})

test('parseDownloadFilename 缺失 header 返回空字符串', () => {
  assert.equal(parseDownloadFilename(null), '')
  assert.equal(parseDownloadFilename(''), '')
})

test('parseDownloadFilename 对 malformed percent encoding 回退 ASCII filename', () => {
  assert.equal(
    parseDownloadFilename(
      'attachment; filename*=UTF-8\'\'bad%ZZ; filename="fallback.txt"'
    ),
    'fallback.txt'
  )
})

test('parseDownloadFilename 对 malformed 普通 filename 保留原值', () => {
  assert.equal(
    parseDownloadFilename('attachment; filename="report%ZZ.txt"'),
    'report%ZZ.txt'
  )
})
