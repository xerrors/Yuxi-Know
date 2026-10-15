const raf = (callback) => typeof requestAnimationFrame === 'function'
  ? requestAnimationFrame(callback) : setTimeout(callback, 16)
const cancelFrame = (id) => typeof cancelAnimationFrame === 'function'
  ? cancelAnimationFrame(id) : clearTimeout(id)

/** 只平滑展示文本；item、done 和恢复始终使用完整协议状态。 */
export function useStreamSmoother({ getThreadState }) {
  const frames = new Map()
  const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' })
  const updateText = (itemId, threadId) => {
    const state = getThreadState(threadId)
    const item = state?.itemState.items[itemId]
    if (!item || item.type !== 'message') return
    if (globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
    state.displayText ||= {}
    state.displayText[itemId] ||= ''
    const key = `${threadId}:${itemId}`
    if (frames.has(key)) return
    const tick = () => {
      frames.delete(key)
      const current = getThreadState(threadId)
      const text = current?.itemState.items[itemId]?.content.map((part) => part.text || '').join('') || ''
      const shown = current?.displayText[itemId] || ''
      if (!current) return
      const graphemes = [...segmenter.segment(text)].map((part) => part.segment)
      const shownCount = [...segmenter.segment(shown)].length
      const count = Math.min(graphemes.length, shownCount + Math.max(2, Math.ceil((graphemes.length - shownCount) / 12)))
      current.displayText[itemId] = graphemes.slice(0, count).join('')
      if (current.displayText[itemId] !== text) frames.set(key, raf(tick))
    }
    frames.set(key, raf(tick))
  }
  const flushThread = (threadId) => {
    const state = getThreadState(threadId)
    if (!state) return
    for (const [key, frame] of frames) {
      if (key.startsWith(`${threadId}:`)) { cancelFrame(frame); frames.delete(key) }
    }
    state.displayText = {}
  }
  const resetThread = (threadId = null) => {
    for (const [key, frame] of frames) {
      if (!threadId || key.startsWith(`${threadId}:`)) { cancelFrame(frame); frames.delete(key) }
    }
    if (threadId) flushThread(threadId)
  }
  return { updateText, flushThread, resetThread }
}
