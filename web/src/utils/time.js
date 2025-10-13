import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'
import relativeTime from 'dayjs/plugin/relativeTime'

dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const DEFAULT_TZ = 'Asia/Shanghai'
dayjs.tz.setDefault(DEFAULT_TZ)

const NUMERIC_REGEX = /^-?\d+(?:\.\d+)?$/

const coerceDayjs = (value) => {
  if (value === null || value === undefined) {
    return null
  }

  if (typeof value === 'number') {
    return dayjs(value).tz(DEFAULT_TZ)
  }

  const stringValue = String(value).trim()
  if (!stringValue) {
    return null
  }

  if (NUMERIC_REGEX.test(stringValue)) {
    const numeric = Number(stringValue)
    if (Number.isNaN(numeric)) {
      return null
    }

    // 值小于 10^12 时视为秒级时间戳，否则视为毫秒
    if (Math.abs(numeric) < 1e12) {
      return dayjs.unix(numeric).tz(DEFAULT_TZ)
    }
    return dayjs(numeric).tz(DEFAULT_TZ)
  }

  // 解析 ISO 字符串（dayjs 会自动识别时区信息，如 Z 后缀表示 UTC）
  const parsed = dayjs(stringValue)
  if (!parsed.isValid()) {
    return null
  }
  // 转换为上海时区
  return parsed.tz(DEFAULT_TZ)
}

export const parseToShanghai = (value) => coerceDayjs(value)

export const formatDateTime = (value, format = 'YYYY-MM-DD HH:mm') => {
  const parsed = coerceDayjs(value)
  if (!parsed) return '-'
  return parsed.format(format)
}

export const formatFullDateTime = (value) => formatDateTime(value, 'YYYY-MM-DD HH:mm:ss')

export const formatRelative = (value) => {
  const parsed = coerceDayjs(value)
  if (!parsed) return '-'
  return parsed.fromNow()
}

export const sortByDatetimeDesc = (items, accessor) => {
  const copy = [...items]
  copy.sort((a, b) => {
    const first = coerceDayjs(accessor(a))
    const second = coerceDayjs(accessor(b))

    if (!first && !second) return 0
    if (!first) return 1
    if (!second) return -1
    return second.valueOf() - first.valueOf()
  })
  return copy
}

export default dayjs
