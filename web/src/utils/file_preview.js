const MARKDOWN_EXTENSIONS = new Set(['.md', '.markdown', '.mdx'])
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'])
const PDF_EXTENSIONS = new Set(['.pdf'])

export const getPreviewFileExtension = (path) => {
  const normalizedPath = String(path || '')
    .trim()
    .toLowerCase()
  if (!normalizedPath) return ''

  const fileName = normalizedPath.split('/').pop() || ''
  const dotIndex = fileName.lastIndexOf('.')
  if (dotIndex <= 0) return ''
  return fileName.slice(dotIndex)
}

export const isMarkdownPreview = (path, previewType) => {
  if (previewType === 'markdown') return true
  return MARKDOWN_EXTENSIONS.has(getPreviewFileExtension(path))
}

export const getPreviewTypeByPath = (path) => {
  const extension = getPreviewFileExtension(path)
  if (IMAGE_EXTENSIONS.has(extension)) return 'image'
  if (PDF_EXTENSIONS.has(extension)) return 'pdf'
  if (MARKDOWN_EXTENSIONS.has(extension)) return 'markdown'
  return 'text'
}
