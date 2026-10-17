export const WEB_PROVIDERS = [
  { id: 'tavily', name: 'Tavily', environment: 'TAVILY_API_KEY', fetch: true },
  { id: 'deepseek', name: 'DeepSeek', environment: 'DEEPSEEK_API_KEY', fetch: true },
  { id: 'doubao', name: '豆包 Custom', environment: 'DOUBAO_SEARCH_API_KEY', fetch: false }
]

export const keyState = (option) =>
  option?.sensitive_state?.api_key || { source: 'none', configured: false }

export const defaultProvider = (operation, config, options) => {
  const selected = config[`web_${operation}_provider`]?.trim().toLowerCase()
  if (selected) return selected
  return WEB_PROVIDERS.find(
    (provider) => (operation === 'search' || provider.fetch) && keyState(options[provider.id]).configured
  )?.id
}

export const testPayload = (provider, operation, draft = '') => ({
  provider,
  ...(operation === 'search'
    ? { query: 'Python 官方文档', count: 1 }
    : { url: 'https://docs.python.org/3/tutorial/index.html' }),
  ...(draft.trim() ? { api_key: draft.trim() } : {})
})

export const testOutcome = (operation, response) => {
  const passed = operation === 'search'
    ? Array.isArray(response?.results) && response.results.length > 0
    : typeof response?.content === 'string' && Boolean(response.content.trim())
  return passed
    ? { state: 'passed' }
    : { state: 'failed', error: operation === 'search' ? '未返回搜索结果' : '未返回网页正文' }
}
