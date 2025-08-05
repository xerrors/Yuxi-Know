// 文件相关工具函数
import { FileTextFilled, FileMarkdownFilled, FilePdfFilled, FileWordFilled, FileExcelFilled, FileImageFilled, FileUnknownFilled } from '@ant-design/icons-vue';

// 根据文件扩展名获取文件图标
export const getFileIcon = (filename) => {
  if (!filename) return FileUnknownFilled

  const extension = filename.toLowerCase().split('.').pop()

  const iconMap = {
    // 文本文件
    'txt': FileTextFilled,
    'text': FileTextFilled,
    'log': FileTextFilled,

    // Markdown文件
    'md': FileMarkdownFilled,
    'markdown': FileMarkdownFilled,

    // PDF文件
    'pdf': FilePdfFilled,

    // Word文档
    'doc': FileWordFilled,
    'docx': FileWordFilled,

    // Excel文档
    'xls': FileExcelFilled,
    'xlsx': FileExcelFilled,
    'csv': FileExcelFilled,

    // 图片文件
    'jpg': FileImageFilled,
    'jpeg': FileImageFilled,
    'png': FileImageFilled,
    'gif': FileImageFilled,
    'bmp': FileImageFilled,
    'svg': FileImageFilled,
    'webp': FileImageFilled,
  }

  return iconMap[extension] || FileUnknownFilled
}

// 根据文件扩展名获取文件图标颜色
export const getFileIconColor = (filename) => {
  if (!filename) return '#8c8c8c'

  const extension = filename.toLowerCase().split('.').pop()

  const colorMap = {
    // 文本文件 - 蓝色
    'txt': '#1890ff',
    'text': '#1890ff',
    'log': '#1890ff',

    // Markdown文件 - 深蓝色
    'md': '#0050b3',
    'markdown': '#0050b3',

    // PDF文件 - 红色
    'pdf': '#ff4d4f',

    // Word文档 - 深蓝色
    'doc': '#2f54eb',
    'docx': '#2f54eb',

    // Excel文档 - 绿色
    'xls': '#52c41a',
    'xlsx': '#52c41a',
    'csv': '#52c41a',

    // 图片文件 - 紫色
    'jpg': '#722ed1',
    'jpeg': '#722ed1',
    'png': '#722ed1',
    'gif': '#722ed1',
    'bmp': '#722ed1',
    'svg': '#722ed1',
    'webp': '#722ed1',
  }

  return colorMap[extension] || '#8c8c8c'
}

// Format relative time with more granularity: days ago, weeks ago, months ago
export const formatRelativeTime = (timestamp, offset = 0) => {
    // If you want to adjust to UTC+8, set offset to 8, otherwise 0
    const timezoneOffset = offset * 60 * 60 * 1000; // offset in milliseconds
    const adjustedTimestamp = timestamp + timezoneOffset;

    const now = Date.now();
    const secondsPast = (now - adjustedTimestamp) / 1000;

    if (secondsPast < 60) {
        return Math.round(secondsPast) + ' 秒前';
    } else if (secondsPast < 3600) {
        return Math.round(secondsPast / 60) + ' 分钟前';
    } else if (secondsPast < 86400) {
        return Math.round(secondsPast / 3600) + ' 小时前';
    } else if (secondsPast < 86400 * 7) {
        // Less than 7 days
        return Math.round(secondsPast / 86400) + ' 天前';
    } else if (secondsPast < 86400 * 30) {
        // Less than 30 days, show in weeks
        return Math.round(secondsPast / (86400 * 7)) + ' 周前';
    } else if (secondsPast < 86400 * 365) {
        // Less than 1 year, show in months
        return Math.round(secondsPast / (86400 * 30)) + ' 月前';
    } else {
        // More than 1 year, show full date
        const date = new Date(adjustedTimestamp);
        const year = date.getFullYear();
        const month = date.getMonth() + 1;
        const day = date.getDate();
        return `${year} 年 ${month} 月 ${day} 日`;
    }
}

// 格式化标准时间
export const formatStandardTime = (timestamp) => {
  const date = new Date(timestamp);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  const second = String(date.getSeconds()).padStart(2, '0');
  return `${year}年${month}月${day}日 ${hour}:${minute}:${second}`;
}

// 获取状态文本
export const getStatusText = (status) => {
  const statusMap = {
    'done': '处理完成',
    'failed': '处理失败',
    'processing': '处理中',
    'waiting': '等待处理'
  }
  return statusMap[status] || status
}