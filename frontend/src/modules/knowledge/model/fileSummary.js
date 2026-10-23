import { getFileStatusView } from './knowledge_file_policy.js'

const ATTENTION_STATUSES = [
  { status: 'error_parsing', tone: 'error' },
  { status: 'error_indexing', aliases: ['failed'], tone: 'error' },
  { status: 'uploaded', tone: 'warning' },
  { status: 'parsed', tone: 'warning' },
  { status: 'waiting', tone: 'warning' },
  { status: 'parsing', tone: 'info' },
  { status: 'indexing', tone: 'info' },
  { status: 'processing', tone: 'info' }
]

/** 使用全库逐状态计数，失败优先；健康文件不占据关注入口。 */
export function fileAttention(stats = {}) {
  const counts = stats.file_status_counts || {}
  const rows = ATTENTION_STATUSES.map((item) => ({
    ...item,
    label: getFileStatusView(item.status).label,
    count: [item.status, ...(item.aliases || [])].reduce(
      (sum, status) => sum + Number(counts[status] || 0),
      0
    )
  })).filter((item) => item.count > 0)
  for (const [status, count] of Object.entries(counts)) {
    if (
      count > 0 &&
      !['indexed', 'done'].includes(status) &&
      !ATTENTION_STATUSES.some((item) => item.status === status || item.aliases?.includes(status))
    ) {
      rows.push({ status, label: `其他状态（${status}）`, count, tone: 'warning' })
    }
  }
  const tone = ['error', 'warning', 'info'].find((level) =>
    rows.some((item) => item.tone === level)
  )
  return { rows, tone, total: rows.reduce((sum, row) => sum + row.count, 0) }
}

/** 错误详情只展示持久文本，缺失时不编造原因。 */
export function fileFailureReason(file) {
  return file.error_message?.trim() || '未记录失败原因。可重试处理，或查看对应后台作业。'
}
