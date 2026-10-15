import assert from 'node:assert/strict'
import test from 'node:test'
import { createItemState, mergeItemSnapshot } from '../../src/modules/session/model/agentItems.js'
import { useStreamSmoother } from '../../src/modules/session/model/useStreamSmoother.js'

function playback(t) {
  const frames = new Map()
  let id = 0
  t.mock.method(globalThis, 'setTimeout', (fn) => { frames.set(++id, fn); return id })
  t.mock.method(globalThis, 'clearTimeout', (key) => frames.delete(key))
  const state = { itemState: { items: {} }, displayText: {} }
  const smoother = useStreamSmoother({ getThreadState: () => state })
  t.after(() => smoother.resetThread('thread'))
  return { state, smoother, frames, tick() {
    const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach((fn) => fn())
  }, push(text) {
    state.itemState.items.m = { type: 'message', content: [{ type: 'output_text', text }] }
    smoother.updateText('m', 'thread')
  } }
}

test('平滑只更新展示正文，协议 item 已保存完整值', (t) => {
  const p = playback(t)
  const text = '正文'.repeat(120)
  p.push(text)
  assert.equal(p.state.displayText.m, '')
  assert.equal(p.state.itemState.items.m.content[0].text, text)
  p.tick()
  assert.ok(p.state.displayText.m.length > 0 && p.state.displayText.m.length < text.length)
  for (let frame = 0; frame < 100; frame++) p.tick()
  assert.equal(p.state.displayText.m, text)
  assert.equal(p.frames.size, 0)
})

test('done flush 立即显示完整值，取消残留帧且保留完整协议', (t) => {
  const p = playback(t)
  p.push('文'.repeat(200))
  p.smoother.flushThread('thread')
  assert.deepEqual(p.state.displayText, {})
  assert.equal(p.state.itemState.items.m.content[0].text, '文'.repeat(200))
  assert.equal(p.frames.size, 0)
})

test('每帧不拆开组合字符或 emoji', (t) => {
  const p = playback(t)
  const grapheme = '👩‍💻'
  p.push(grapheme.repeat(80))
  while (p.frames.size) {
    p.tick()
    assert.equal(p.state.displayText.m.replaceAll(grapheme, ''), '')
  }
})


test('活动快照补回完成块后立即清除已追上的旧平滑文本', (t) => {
  const p = playback(t)
  p.state.itemState = createItemState()
  p.push('part')
  p.state.itemState.items.m = { ...p.state.itemState.items.m, id: 'm', status: 'in_progress', yuxi: {} }
  while (p.frames.size) p.tick()
  assert.equal(p.state.displayText.m, 'part')
  mergeItemSnapshot(p.state.itemState, [{ id: 'm', type: 'message', status: 'in_progress',
    content: [{ type: 'output_text', text: 'whole' }], yuxi: { completed_content_indices: [0] } }])
  p.smoother.flushThread('thread')
  assert.equal(p.state.displayText.m ?? p.state.itemState.items.m.content[0].text, 'whole')
})
