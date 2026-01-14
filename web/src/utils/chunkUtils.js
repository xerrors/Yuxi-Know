/**
 * Chunk合并工具函数
 * 用于合并多个chunk并处理重叠内容
 */

/**
 * 查找两个字符串的重叠部分
 * @param {string} str1 - 第一个字符串
 * @param {string} str2 - 第二个字符串
 * @returns {string} - 重叠部分的内容
 */
export function findOverlap(str1, str2) {
  if (!str1 || !str2) return ''

  const maxOverlap = Math.min(str1.length, str2.length)
  let overlap = ''

  // 从最长可能的重叠开始检查
  for (let i = maxOverlap; i > 10; i--) {
    const endStr1 = str1.slice(-i)
    const startStr2 = str2.slice(0, i)

    if (endStr1 === startStr2) {
      overlap = endStr1
      break
    }
  }

  return overlap
}

/**
 * 合并chunks并处理重叠内容
 * @param {Array} chunks - chunk数组，每个chunk包含id, content, chunk_order_index
 * @returns {Object} - 合并结果，包含content和chunks数组
 */
export function mergeChunks(chunks) {
  if (!chunks || chunks.length === 0) {
    return { content: '', chunks: [] }
  }

  // 按order排序
  const sorted = [...chunks].sort((a, b) => a.chunk_order_index - b.chunk_order_index)
  const merged = []
  let currentContent = ''

  for (let i = 0; i < sorted.length; i++) {
    const chunk = sorted[i]
    const content = chunk.content

    if (i === 0) {
      // 第一个chunk直接添加
      currentContent = content
      merged.push({
        ...chunk,
        startOffset: 0,
        endOffset: content.length
      })
    } else {
      // 查找重叠部分
      const overlap = findOverlap(currentContent, content)
      const newContent = content.slice(overlap.length)

      if (newContent.length > 0) {
        const startOffset = currentContent.length
        if (overlap.length > 0) {
          currentContent += newContent
        } else {
          currentContent += `\n${newContent}`
        }
        merged.push({
          ...chunk,
          startOffset,
          endOffset: currentContent.length
        })
      }
    }
  }

  return { content: currentContent, chunks: merged }
}

/**
 * 将文本分割成段落
 * @param {string} content - 文本内容
 * @returns {Array} - 段落数组
 */
export function splitIntoParagraphs(content) {
  if (!content) return []

  // 按换行符分割，保留空段落
  return content.split(/\n\n+/).filter((para) => para.trim() !== '')
}

/**
 * 为每个段落找到对应的chunk
 * @param {Array} paragraphs - 段落数组
 * @param {Array} mappedChunks - 映射后的chunks
 * @returns {Array} - 包含chunk信息的段落
 */
export function mapParagraphsToChunks(paragraphs, mappedChunks) {
  if (!paragraphs || !mappedChunks) return []

  let currentOffset = 0
  return paragraphs.map((paragraph) => {
    const paragraphLength = paragraph.length + 2 // +2 for the \n\n

    // 找到包含此位置的chunk
    const chunk =
      mappedChunks.find(
        (chunk) => currentOffset >= chunk.startOffset && currentOffset < chunk.endOffset
      ) || mappedChunks[0]

    const result = {
      content: paragraph,
      chunk,
      startOffset: currentOffset,
      endOffset: currentOffset + paragraphLength
    }

    currentOffset += paragraphLength
    return result
  })
}

/**
 * 获取chunk的预览文本
 * @param {string} content - chunk内容
 * @param {number} maxLength - 最大长度
 * @returns {string} - 预览文本
 */
export function getChunkPreview(content, maxLength = 100) {
  if (!content) return ''

  const text = content.replace(/\n+/g, ' ').trim()
  if (text.length <= maxLength) return text

  return text.slice(0, maxLength) + '...'
}
