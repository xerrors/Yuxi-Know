const optionProvider = (option) => option?.params?.provider

export const webProviders = (options = []) =>
  (Array.isArray(options) ? options : [])
    .filter((option) => optionProvider(option)?.id)
    .map((option) => ({
      id: optionProvider(option).id,
      name: option.name,
      environment: optionProvider(option).environment,
      fetch: Boolean(optionProvider(option).supports_fetch),
      optionKey: option.key
    }))

export const keyState = (option) =>
  option?.sensitive_state?.api_key || { source: 'none', configured: false }

export const defaultProvider = (operation, config, providers, options) => {
  const selected = config[`web_${operation}_provider`]?.trim().toLowerCase()
  if (selected) return selected
  return providers.find(
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
