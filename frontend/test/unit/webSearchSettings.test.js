import assert from 'node:assert/strict'
import test from 'node:test'
import { WEB_PROVIDERS, defaultProvider, keyState, testOutcome, testPayload } from '../../src/modules/settings/model/webSearchSettings.js'

test('三个独立 Provider 保持展示顺序，豆包不能用于 Fetch', () => {
  assert.deepEqual(WEB_PROVIDERS.map(({ id }) => id), ['tavily', 'deepseek', 'doubao'])
  const configured = Object.fromEntries(WEB_PROVIDERS.map(({ id }) => [id, { sensitive_state: { api_key: { configured: true } } }]))
  assert.equal(defaultProvider('search', {}, configured), 'tavily')
  assert.equal(defaultProvider('fetch', {}, { doubao: configured.doubao }), undefined)
  assert.equal(defaultProvider('search', { web_search_provider: 'deepseek' }, configured), 'deepseek')
  assert.equal(defaultProvider('search', { web_search_provider: ' TAVILY ' }, configured), 'tavily')
  assert.equal(defaultProvider('fetch', {}, { deepseek: configured.deepseek }), 'deepseek')
})

test('固定测试使用内置查询和文档，空草稿不传 Key', () => {
  assert.equal(keyState(undefined).configured, false)
  assert.deepEqual(testPayload('doubao', 'search'), { provider: 'doubao', query: 'Python 官方文档', count: 1 })
  assert.deepEqual(testPayload('deepseek', 'fetch', ' draft '), {
    provider: 'deepseek', url: 'https://docs.python.org/3/tutorial/index.html', api_key: 'draft'
  })
  assert.equal('api_key' in testPayload('tavily', 'search', '  '), false)
})

test('测试仅在取得搜索结果或非空正文后通过', () => {
  assert.deepEqual(testOutcome('search', { results: [{ url: 'https://example.com' }] }), { state: 'passed' })
  assert.deepEqual(testOutcome('fetch', { content: '# Body' }), { state: 'passed' })
  assert.equal(testOutcome('search', { results: [] }).state, 'failed')
  assert.equal(testOutcome('fetch', { content: '  ' }).state, 'failed')
})
