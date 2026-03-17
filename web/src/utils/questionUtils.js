/**
 * 问题和选项规范化工具
 */

const DEFAULT_OTHER_OPTION_VALUE = '__other__'

/**
 * 判断选项是否为"其他"选项
 */
export const isOtherOption = (option) => {
  if (!option || typeof option !== 'object') return false
  const label = String(option.label || '')
    .trim()
    .toLowerCase()
  const value = String(option.value || '')
    .trim()
    .toLowerCase()

  return (
    value === DEFAULT_OTHER_OPTION_VALUE ||
    value === 'other' ||
    label.includes('其他') ||
    label.includes('other')
  )
}

/**
 * 规范化选项列表
 */
export const normalizeOptions = (rawOptions) => {
  if (!Array.isArray(rawOptions)) return []

  return rawOptions
    .map((item) => {
      if (item && typeof item === 'object') {
        const label = String(item.label || item.value || '').trim()
        const value = String(item.value || item.label || '').trim()
        return label && value ? { label, value } : null
      }

      const text = String(item || '').trim()
      return text ? { label: text, value: text } : null
    })
    .filter(Boolean)
}

/**
 * 规范化问题列表
 */
export const normalizeQuestions = (rawQuestions) => {
  if (!Array.isArray(rawQuestions)) return []

  return rawQuestions
    .map((item, index) => {
      if (!item || typeof item !== 'object') return null

      const question = String(item.question || '').trim()
      if (!question) return null

      const questionId =
        String(item.questionId || item.question_id || '').trim() || `q-${index + 1}`
      const operation = String(item.operation || '').trim()
      const allowOther = Boolean(item.allowOther ?? item.allow_other ?? true)
      const baseOptions = normalizeOptions(item.options || [])
      const hasOtherOption = baseOptions.some((option) => isOtherOption(option))
      const options =
        allowOther && !hasOtherOption
          ? [...baseOptions, { label: '其他', value: DEFAULT_OTHER_OPTION_VALUE }]
          : baseOptions

      return {
        questionId,
        question,
        options,
        multiSelect: Boolean(item.multiSelect ?? item.multi_select ?? false),
        allowOther,
        operation
      }
    })
    .filter(Boolean)
}

/**
 * 从旧格式构建单个问题（向后兼容）
 */
export const buildLegacyQuestion = (chunk, interruptInfo) => {
  const question = String(chunk?.question || interruptInfo?.question || '').trim()
  if (!question) return null

  const operation = String(chunk?.operation || interruptInfo?.operation || '').trim()

  return {
    questionId: String(chunk?.question_id || interruptInfo?.question_id || '').trim() || 'q-1',
    question,
    options: normalizeOptions(chunk?.options || interruptInfo?.options || []),
    multiSelect: Boolean(chunk?.multi_select ?? interruptInfo?.multi_select ?? false),
    allowOther: Boolean(chunk?.allow_other ?? interruptInfo?.allow_other ?? true),
    operation
  }
}

export { DEFAULT_OTHER_OPTION_VALUE }
