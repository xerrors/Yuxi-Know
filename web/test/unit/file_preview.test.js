import assert from 'node:assert/strict'
import test from 'node:test'
import { getPreviewTypeByPath, normalizePreviewResponse } from '../../src/utils/file_preview.js'

for (const path of ['/报表.xlsx', '/历史.XLS']) {
  test(`${path} 进入 Office 预览，PDF 响应保留原件身份`, async () => {
    assert.equal(getPreviewTypeByPath(path), 'office')
    const result = await normalizePreviewResponse(
      new Response('%PDF-1.4\npreview', { headers: { 'content-type': 'application/pdf' } }),
      { path, filename: path.slice(1) }
    )
    assert.equal(result.previewType, 'pdf')
    assert.equal(result.supported, true)
    assert.equal(result.path, path)
    assert.equal(result.filename, path.slice(1))
  })
}

test('Excel 超限或转换失败时保留服务端拒绝结果', async () => {
  const result = await normalizePreviewResponse(
    Response.json({ preview_type: 'unsupported', supported: false, message: '文件过大' }),
    { path: '/报表.xlsx' }
  )
  assert.equal(result.status, 'unsupported')
  assert.equal(result.supported, false)
  assert.equal(result.message, '文件过大')
  assert.equal(getPreviewTypeByPath('/报表.xlsm'), 'unsupported')
})

test('后台预览生成状态保留加载提示，错误终态结束加载', async () => {
  const loading = await normalizePreviewResponse(Response.json({
    status: 'loading', preview_type: 'office', supported: true, message: '正在生成预览...'
  }), { path: '/报表.xlsx' })
  assert.equal(loading.loading, true)
  assert.equal(loading.loadingMessage, '正在生成预览...')
  const failed = await normalizePreviewResponse(Response.json({
    status: 'error', preview_type: 'office', supported: false, message: '预览生成失败'
  }), { path: '/报表.xlsx' })
  assert.equal(failed.loading, false)
  assert.equal(failed.status, 'error')
  assert.equal(failed.errorMessage, '预览生成失败')
})
