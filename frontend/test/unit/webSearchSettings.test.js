import assert from 'node:assert/strict'
import test from 'node:test'
import { defaultProvider, keyState, testOutcome, testPayload, webProviders } from '../../src/modules/settings/model/webSearchSettings.js'

const optionRecords = [
  { key: 'tavily_search_opts', name: 'Tavily', params: { provider: { id: 'tavily', supports_fetch: true, environment: 'TAVILY_API_KEY' } } },
  { key: 'deepseek_search_opts', name: 'DeepSeek', params: { provider: { id: 'deepseek', supports_fetch: true, environment: 'DEEPSEEK_API_KEY' } } },
  { key: 'doubao_search_opts', name: '豆包 Custom', params: { provider: { id: 'doubao', supports_fetch: false, environment: 'DOUBAO_SEARCH_API_KEY' } } },
  { key: 'unrelated', name: '无关配置', params: { fields: [] } }
]

test('三个独立 Provider 从配置元数据派生顺序，豆包不能用于 Fetch', () => {
  const providers = webProviders(optionRecords)
  assert.deepEqual(providers.map(({ id }) => id), ['tavily', 'deepseek', 'doubao'])
  assert.equal(providers.find(({ id }) => id === 'doubao').fetch, false)
  assert.equal(providers.find(({ id }) => id === 'tavily').environment, 'TAVILY_API_KEY')
  const configured = Object.fromEntries(providers.map(({ id }) => [id, { sensitive_state: { api_key: { configured: true } } }]))
  assert.equal(defaultProvider('search', {}, providers, configured), 'tavily')
  assert.equal(defaultProvider('fetch', {}, providers, { doubao: configured.doubao }), undefined)
  assert.equal(defaultProvider('search', { web_search_provider: 'deepseek' }, providers, configured), 'deepseek')
  assert.equal(defaultProvider('search', { web_search_provider: ' TAVILY ' }, providers, configured), 'tavily')
  assert.equal(defaultProvider('fetch', {}, providers, { deepseek: configured.deepseek }), 'deepseek')
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
