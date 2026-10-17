/** 从后端响应读取可安全打开的 Langfuse Trace 地址。 */
export function resolveLangfuseTraceUrl(payload) {
  if (typeof payload?.langfuse_url !== 'string') return null
  const value = payload.langfuse_url.trim()
  if (!value) return null
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? value : null
  } catch {
    return null
  }
}
