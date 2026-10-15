export function formatSandboxDuration(seconds) {
  const total = Math.max(0, Math.floor(seconds))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const parts = []
  if (days) parts.push(`${days} 天`)
  if (hours) parts.push(`${hours} 小时`)
  if (minutes) parts.push(`${minutes} 分钟`)
  if (!days && !hours && (total % 60 || !parts.length)) parts.push(`${total % 60} 秒`)
  return parts.join(' ')
}

export function sandboxTimingText(status, now) {
  if (!status) return ''
  if (status.state === 'paused') {
    if (!status.paused_at) return '时间未记录'
    const elapsed = (now - Date.parse(status.paused_at)) / 1000
    return formatSandboxDuration(elapsed)
  }
  if (status.state !== 'running') return ''
  if (status.busy) return '任务或操作进行中，暂不休眠'
  if (!status.idle_deadline_at) return ''
  const remaining = (Date.parse(status.idle_deadline_at) - now) / 1000
  if (remaining <= 0) return '已达到空闲时限，等待休眠'
  return `预计 ${formatSandboxDuration(Math.ceil(remaining))} 后休眠`
}
