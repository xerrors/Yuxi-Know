/** 同一回答块的引用合并，范围跨块时胶囊落在最后的命中块。 */
export function groupMarkdownReferences(blocks, citations, excluded = []) {
  const groups = new Map()
  for (const [index, citation] of citations.entries()) {
    if (excluded.some((block) =>
      Number(block.dataset.sourceStart) <= citation.answer_end_line &&
      Number(block.dataset.sourceEnd) >= citation.answer_start_line)) continue
    const matches = blocks.filter((block) =>
      Number(block.dataset.referenceStart) <= citation.answer_end_line &&
      Number(block.dataset.referenceEnd) >= citation.answer_start_line)
    const innermost = matches.filter((block) =>
      !matches.some((other) => other !== block && block.contains(other)))
    if (!innermost.length) continue
    const tail = innermost.at(-1)
    if (!groups.has(tail)) groups.set(tail, { blocks: new Set(), indices: [] })
    const group = groups.get(tail)
    innermost.forEach((block) => group.blocks.add(block))
    group.indices.push(index)
  }
  return groups
}

/** 胶囊使用可辨认的站点或文件名，完整标题由来源卡片展示。 */
export function referenceSourceLabel(source) {
  if (source.kind === 'web') return new URL(source.url).hostname.replace(/^www\./, '')
  return source.title || '知识库文件'
}

/** 保留原有 Markdown 结构，只在块尾添加来源胶囊。 */
export function decorateMarkdownReferences(root, citations) {
  root.querySelectorAll('.reference-citation').forEach((node) => node.remove())
  root.querySelectorAll('.reference-answer-highlight').forEach((node) =>
    node.classList.remove('reference-answer-highlight', 'reference-answer-active'))
  const blocks = [...root.querySelectorAll('[data-reference-start]')]
    .filter((block) => !block.closest('[data-reference-excluded]'))
  const excluded = [...root.querySelectorAll('[data-reference-excluded]')]
  for (const [tail, group] of groupMarkdownReferences(blocks, citations, excluded)) {
    group.blocks.forEach((block) => block.classList.add('reference-answer-highlight'))
    const badge = root.ownerDocument.createElement('button')
    badge.type = 'button'
    badge.className = 'reference-citation'
    badge.dataset.referenceIndices = group.indices.join(',')
    const label = root.ownerDocument.createElement('span')
    label.className = 'reference-citation-label'
    label.textContent = referenceSourceLabel(citations[group.indices[0]].source)
    badge.appendChild(label)
    if (group.indices.length > 1) {
      const count = root.ownerDocument.createElement('span')
      count.className = 'reference-citation-count'
      count.textContent = `+${group.indices.length - 1}`
      badge.appendChild(count)
    }
    badge.setAttribute('aria-label', `查看来源：${label.textContent}，共 ${group.indices.length} 条引用`)
    badge.setAttribute('aria-haspopup', 'dialog')
    badge.setAttribute('aria-expanded', 'false')
    const destination = tail.matches('tr') ? tail.querySelector('td:last-child, th:last-child') : tail
    destination.appendChild(badge)
  }
}
