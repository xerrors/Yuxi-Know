import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { createPinia, setActivePinia } from 'pinia'
import {
  buildUploadParams,
  collectUploadMetadata,
  isHiddenUploadPath,
  shouldAcceptUploadFile
} from '../../src/modules/knowledge/model/uploadMetadata.js'
import { createTestServer } from '../helpers/createTestServer.js'

function readSource(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), 'utf8')
}

const storageValues = new Map()
globalThis.localStorage = {
  getItem: (key) => storageValues.get(key) ?? null,
  setItem: (key, value) => storageValues.set(key, String(value)),
  removeItem: (key) => storageValues.delete(key),
  clear: () => storageValues.clear()
}

test('知识库详情页下拉菜单提供上传文件夹入口', () => {
  const source = readSource('../../src/pages/KnowledgeBaseInfoView.vue')
  const menu = source.slice(
    source.indexOf('<Transition name="file-action-menu">'),
    source.indexOf('</Transition>')
  )

  assert.match(menu, /onUploadFolderAction/)
  assert.match(menu, /上传文件夹/)
  assert.match(source, /showAddFilesModal\(\{\s*isFolder:\s*true,\s*mode:\s*'folder'\s*\}\)/)
})

test('上传元数据收集保留相对路径并过滤隐藏文件', () => {
  const files = [
    {
      status: 'done',
      response: {
        file_path: 'minio://bucket/kb_test/upload/doc1.txt',
        content_hash: 'hash1',
        size: 10
      },
      webkitRelativePath: 'my_folder/sub/doc1.txt'
    },
    {
      status: 'done',
      response: {
        file_path: 'minio://bucket/kb_test/upload/doc2.txt',
        content_hash: 'hash2',
        size: 20
      },
      webkitRelativePath: 'my_folder/doc2.txt'
    },
    { status: 'uploading', response: { file_path: 'minio://bucket/kb_test/upload/doc3.txt' } },
    { status: 'done', response: {} },
    {
      status: 'done',
      response: {
        file_path: 'minio://bucket/kb_test/upload/doc4.txt',
        content_hash: 'hash4',
        size: Number.POSITIVE_INFINITY
      },
      originFileObj: { webkitRelativePath: 'origin/doc4.txt' }
    }
  ]

  const result = collectUploadMetadata(files)

  assert.deepEqual(result.items, [
    'minio://bucket/kb_test/upload/doc1.txt',
    'minio://bucket/kb_test/upload/doc2.txt',
    'minio://bucket/kb_test/upload/doc4.txt'
  ])
  assert.deepEqual(result.content_hashes, {
    'minio://bucket/kb_test/upload/doc1.txt': 'hash1',
    'minio://bucket/kb_test/upload/doc2.txt': 'hash2',
    'minio://bucket/kb_test/upload/doc4.txt': 'hash4'
  })
  assert.deepEqual(result.file_sizes, {
    'minio://bucket/kb_test/upload/doc1.txt': 10,
    'minio://bucket/kb_test/upload/doc2.txt': 20
  })
  assert.deepEqual(result.source_paths, {
    'minio://bucket/kb_test/upload/doc1.txt': 'my_folder/sub/doc1.txt',
    'minio://bucket/kb_test/upload/doc2.txt': 'my_folder/doc2.txt',
    'minio://bucket/kb_test/upload/doc4.txt': 'origin/doc4.txt'
  })
  assert.equal(isHiddenUploadPath('.env', ''), true)
  assert.equal(isHiddenUploadPath('doc.txt', 'folder/.hidden/doc.txt'), true)
  assert.equal(isHiddenUploadPath('doc.txt', 'folder/sub/doc.txt'), false)
  assert.equal(
    shouldAcceptUploadFile(null, () => true),
    false
  )
  assert.equal(
    shouldAcceptUploadFile({ name: '.env' }, () => true),
    false
  )
  assert.equal(
    shouldAcceptUploadFile(
      { name: 'doc.txt', webkitRelativePath: 'folder/.hidden/doc.txt' },
      () => true
    ),
    false
  )
  assert.equal(
    shouldAcceptUploadFile(
      { name: 'doc.txt', originFileObj: { webkitRelativePath: 'folder/doc.txt' } },
      (name) => name.endsWith('.txt')
    ),
    true
  )
  const params = buildUploadParams({ content_type: 'file' }, result)
  assert.deepEqual(params.source_paths, result.source_paths)
  const withoutSources = buildUploadParams(
    {},
    { content_hashes: {}, file_sizes: {}, source_paths: {} }
  )
  assert.equal('source_paths' in withoutSources, false)
})

test('documentApi.addDocuments 能够将 source_paths 正确打包发送给知识库文档添加端点', async () => {
  const server = await createTestServer({
    server: { middlewareMode: true },
    appType: 'custom'
  })

  try {
    storageValues.set('user_token', 'test-token')
    const requests = []
    globalThis.fetch = async (url, options = {}) => {
      requests.push({ url, options })
      return new Response(JSON.stringify({ status: 'success', message: '已添加' }), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })
    }

    setActivePinia(createPinia())
    const { useUserStore } = await server.ssrLoadModule('/src/modules/identity/model/user.js')
    const userStore = useUserStore()
    userStore.userRole = 'admin'
    userStore.token = 'test-token'

    const { documentApi } = await server.ssrLoadModule('/src/apis/knowledge_api.js')

    const items = [
      'minio://bucket/kb_test/upload/doc1.txt',
      'minio://bucket/kb_test/upload/doc2.txt'
    ]
    const params = {
      content_type: 'file',
      content_hashes: {
        'minio://bucket/kb_test/upload/doc1.txt': 'hash1',
        'minio://bucket/kb_test/upload/doc2.txt': 'hash2'
      },
      source_paths: {
        'minio://bucket/kb_test/upload/doc1.txt': 'my_folder/sub/doc1.txt',
        'minio://bucket/kb_test/upload/doc2.txt': 'my_folder/doc2.txt'
      }
    }

    const response = await documentApi.addDocuments('kb_123', items, params)

    assert.equal(response.status, 'success')
    assert.equal(requests.length, 1)
    assert.equal(requests[0].url, '/api/knowledge/knowledge-bases/kb_123/documents')
    assert.equal(requests[0].options.method, 'POST')
    const parsedBody = JSON.parse(requests[0].options.body)
    assert.deepEqual(parsedBody.items, items)
    assert.deepEqual(parsedBody.params.source_paths, {
      'minio://bucket/kb_test/upload/doc1.txt': 'my_folder/sub/doc1.txt',
      'minio://bucket/kb_test/upload/doc2.txt': 'my_folder/doc2.txt'
    })
  } finally {
    await server.close()
  }
})
