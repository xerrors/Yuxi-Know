import assert from 'node:assert/strict'
import test from 'node:test'

import { createPinia, setActivePinia } from 'pinia'
import { createTestServer } from '../helpers/createTestServer.js'

const storageValues = new Map([['user_token', 'test-token']])
globalThis.localStorage = {
  getItem: (key) => storageValues.get(key) ?? null,
  setItem: (key, value) => storageValues.set(key, String(value)),
  removeItem: (key) => storageValues.delete(key),
  clear: () => storageValues.clear()
}

test('知识库文件修改守卫拒绝只读、锁定和筛选场景', async () => {
  const server = await createTestServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { canDropOnFileBreadcrumb } = await server.ssrLoadModule('/src/shared/lib/fileDrop.js')
    const { canMutateKnowledgeFiles, canDragKnowledgeFile, canDropKnowledgeFileIntoFolder } =
      await server.ssrLoadModule('/src/modules/knowledge/model/knowledgeFileMutations.js')

    assert.equal(canMutateKnowledgeFiles({}), true)
    for (const blockedState of [{ readonly: true }, { locked: true }, { filtered: true }]) {
      assert.equal(canMutateKnowledgeFiles(blockedState), false)
    }

    const realFile = { file_id: 'file-1' }
    const realFolder = { file_id: 'folder-1', is_folder: true }
    assert.equal(
      canDragKnowledgeFile({
        enabled: true,
        record: realFile,
        breadcrumbs: [],
        files: [realFolder]
      }),
      true
    )
    assert.equal(canDropKnowledgeFileIntoFolder(realFile, realFolder), true)
    assert.equal(canDropOnFileBreadcrumb({ enabled: true, item: {}, index: 0, count: 2 }), true)
    assert.equal(canDropKnowledgeFileIntoFolder(realFolder, realFolder), false)
    assert.equal(
      canDropOnFileBreadcrumb({ enabled: true, item: { dropDisabled: true }, index: 0, count: 2 }),
      false
    )
    assert.equal(canDropOnFileBreadcrumb({ enabled: true, item: {}, index: 1, count: 2 }), false)
  } finally {
    await server.close()
  }
})

test('知识库文件夹移动与重命名 API 使用管理端 PUT 契约', async () => {
  const server = await createTestServer({ server: { middlewareMode: true }, appType: 'custom' })
  const requests = []
  globalThis.fetch = async (url, options = {}) => {
    requests.push({
      url,
      method: options.method,
      body: options.body ? JSON.parse(options.body) : undefined
    })
    return new Response(JSON.stringify({ file_id: 'folder-1' }), {
      status: 200,
      headers: { 'content-type': 'application/json' }
    })
  }

  try {
    setActivePinia(createPinia())
    const { useUserStore } = await server.ssrLoadModule('/src/modules/identity/model/user.js')
    useUserStore().userRole = 'superadmin'
    const { documentApi } = await server.ssrLoadModule('/src/apis/knowledge_api.js')
    await documentApi.renameFolder('kb-1', 'folder-1', '新名称')
    await documentApi.moveDocument('kb-1', 'file-1', 'folder-2')

    assert.deepEqual(requests, [
      {
        url: '/api/knowledge/knowledge-bases/kb-1/folders/folder-1/rename',
        method: 'PUT',
        body: { folder_name: '新名称' }
      },
      {
        url: '/api/knowledge/knowledge-bases/kb-1/documents/file-1/move',
        method: 'PUT',
        body: { new_parent_id: 'folder-2' }
      }
    ])
  } finally {
    await server.close()
  }
})
