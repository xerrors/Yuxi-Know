// 文件相关工具函数
import {
  FileTextFilled,
  FileMarkdownFilled,
  FilePdfFilled,
  FileWordFilled,
  FileExcelFilled,
  FileImageFilled,
  FileUnknownFilled,
  FilePptFilled
} from '@ant-design/icons-vue'
import { formatRelative, parseToShanghai } from '@/utils/time'

// 根据文件扩展名获取文件图标
export const getFileIcon = (filename) => {
  if (!filename) return FileUnknownFilled

  const extension = filename.toLowerCase().split('.').pop()

  const iconMap = {
    // 文本文件
    txt: FileTextFilled,
    text: FileTextFilled,
    log: FileTextFilled,

    // Markdown文件
    md: FileMarkdownFilled,
    markdown: FileMarkdownFilled,

    // PDF文件
    pdf: FilePdfFilled,

    // Word文档
    doc: FileWordFilled,
    docx: FileWordFilled,

    // Excel文档
    xls: FileExcelFilled,
    xlsx: FileExcelFilled,
    csv: FileExcelFilled,

    // PPT文档
    ppt: FilePptFilled,
    pptx: FilePptFilled,

    // 图片文件
    jpg: FileImageFilled,
    jpeg: FileImageFilled,
    png: FileImageFilled,
    gif: FileImageFilled,
    bmp: FileImageFilled,
    svg: FileImageFilled,
    webp: FileImageFilled,

    // HTML文件
    html: FileTextFilled,
    htm: FileTextFilled
  }

  return iconMap[extension] || FileUnknownFilled
}

// 根据文件扩展名获取文件图标颜色
export const getFileIconColor = (filename) => {
  if (!filename) return '#8c8c8c'

  const extension = filename.toLowerCase().split('.').pop()

  const colorMap = {
    // 文本文件 - 蓝色
    txt: '#1890ff',
    text: '#1890ff',
    log: '#1890ff',

    // Markdown文件 - 深灰色
    md: '#595959',
    markdown: '#595959',

    // PDF文件 - 红色
    pdf: '#ff4d4f',

    // Word文档 - 深蓝色
    doc: '#2f54eb',
    docx: '#2f54eb',

    // Excel文档 - 绿色
    xls: '#52c41a',
    xlsx: '#52c41a',
    csv: '#52c41a',

    // PPT文档 - 橙色
    ppt: '#f6720d',
    pptx: '#f6720d',

    // 图片文件 - 紫色
    jpg: '#722ed1',
    jpeg: '#722ed1',
    png: '#722ed1',
    gif: '#722ed1',
    bmp: '#722ed1',
    svg: '#722ed1',
    webp: '#722ed1',

    // HTML文件 - 橙色
    html: '#fa8c16',
    htm: '#fa8c16'
  }

  return colorMap[extension] || '#8c8c8c'
}

// Format relative time with CST baseline
export const formatRelativeTime = (value) => formatRelative(value)

// 格式化标准时间
export const formatStandardTime = (value) => {
  const parsed = parseToShanghai(value)
  if (!parsed) return '-'
  return parsed.format('YYYY年MM月DD日 HH:mm:ss')
}

// 获取状态文本
export const getStatusText = (status) => {
  const statusMap = {
    done: '处理完成',
    failed: '处理失败',
    processing: '处理中',
    waiting: '等待处理'
  }
  return map[status] || status
}

// 格式化文件大小
export const formatFileSize = (bytes) => {
  if (bytes === 0 || bytes === '0') return '0 B'
  if (!bytes) return '-'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}
