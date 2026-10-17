import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'
import { compileScript, parse } from 'vue/compiler-sfc'
import * as debug from '../../src/modules/session/model/messageDebug.js'
import * as timing from '../../src/modules/session/model/runTiming.js'
import { resolveLangfuseTraceUrl } from '../../src/shared/lib/langfuse.js'

/** 执行真实组件脚本，保留分组和跳转逻辑。 */
function setupComponent(name, api = {}) {
  const scope = effectScope()
  const windows = []
  const notices = []
  const props = reactive({ threadId: 'thread-a', active: false, runActive: false })
  const deps = {
    ...debug, ...timing, computed, reactive, ref, watch,
    onMounted() {}, onBeforeUnmount() {}, onDeactivated() {},
    document: { visibilityState: 'visible', addEventListener() {}, removeEventListener() {} },
    window: { open() {
      const target = { closed: false, close() { this.closed = true }, location: { replace(url) { target.url = url } } }
      windows.push(target)
      return target
    } },
    message: { warning: (text) => notices.push(text), error: (text) => notices.push(text) },
    agentApi: api, feedbackApi: api, resolveLangfuseTraceUrl,
    formatDateTime: (value) => value, copyTextToClipboard() {}
  }
  for (const name of ['Check', 'ChevronRight', 'Clock', 'Copy', 'ExternalLink', 'LoaderCircle', 'RefreshCw', 'Search', 'TriangleAlert', 'X', 'JsonTreeViewer', 'AlertCircle', 'ArrowUpRight', 'ChevronRight', 'Lightbulb', 'MessageSquare', 'ThumbsDown', 'ThumbsUp', 'FallbackAvatar', 'ResourceEmptyState']) deps[name] = {}
  const path = name === 'debug'
    ? '../../src/modules/session/ui/MessageDebugPanel.vue'
    : '../../src/modules/dashboard/ui/AgentFeedbackList.vue'
  const { descriptor } = parse(readFileSync(new URL(path, import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: 'turn-trace' }).content
    .replace(/^import[\s\S]*?from '[^']+'\n/gm, '')
    .replace('export default', 'return')
  const component = new Function(...Object.keys(deps), script)(...Object.values(deps))
  const form = scope.run(() => component.setup(props, { expose() {} }))
  return { form, props, windows, notices, stop: () => scope.stop() }
}

test('调试面板按 Turn 合并恢复 Run，保留零消息轮次与真实整轮状态', () => {
  const { form, stop } = setupComponent('debug')
  try {
    form.messageAudits.value = [
      { id: 1, type: 'human', run_id: 'r1', turn_id: 't1', content: '问题' },
      { id: 2, type: 'ai', run_id: 'r2', turn_id: 't1', content: '恢复回答' }
    ]
    form.runTraces.value = [
      { run_id: 'r1', turn_id: 't1', status: 'interrupted', timing: { created_at: '2026-10-16T00:00:00Z', total_latency_ms: 4000 } },
      { run_id: 'r2', turn_id: 't1', status: 'completed', timing: { created_at: '2026-10-16T00:00:20Z', total_latency_ms: 4000 } },
      { run_id: 'r3', turn_id: 't2', status: 'cancelled' }
    ]
    form.turnTraces.value = [
      { turn_id: 't1', status: 'waiting', created_at: '2026-10-16T00:00:00Z' },
      { turn_id: 't2', status: 'cancelled' }
    ]
    assert.deepEqual(form.baseGroups.value.map((group) => [group.turnId, group.items.length]), [['t1', 2], ['t2', 0]])
    const first = form.baseGroups.value[0]
    assert.equal(first.runs.length, 2)
    assert.equal(form.turnStatus(first), 'waiting')
    form.selectTurn(first)
    assert.equal(form.selectedTargetData.value.turn_id, 't1')
    assert.deepEqual(form.selectedTargetData.value.runs.map((run) => run.run_id), ['r1', 'r2'])
    assert.equal(form.combinedTrace.value.durationMs, 8000)
    assert.equal(form.combinedTrace.value.spans.length, 2)
    assert.ok(form.combinedTrace.value.spans.every((mark) => mark.groupKey === first.key))
    form.timelineRangeStart.value = 625
    assert.deepEqual(form.filteredTimelineGroups.value[0].visibleItems.map((item) => item.raw.id), [2])
  } finally { stop() }
})

test('选择同一 Turn 的零消息失败 Run 时保留轮次，排除其他执行窗口', () => {
  const { form, stop } = setupComponent('debug')
  try {
    form.messageAudits.value = [{ id: 1, type: 'ai', run_id: 'r1', turn_id: 't1', content: '第一段' }]
    form.runTraces.value = [
      { run_id: 'r1', turn_id: 't1', status: 'interrupted', timing: { created_at: '2026-10-16T00:00:00Z', total_latency_ms: 4000 } },
      { run_id: 'r2', turn_id: 't1', status: 'failed', timing: { created_at: '2026-10-16T00:00:20Z', total_latency_ms: 4000 } },
      { run_id: 'r3', turn_id: 't2', status: 'cancelled', timing: { created_at: '2026-10-16T00:00:30Z', total_latency_ms: 4000 } }
    ]
    form.timelineRangeStart.value = 417
    form.timelineRangeEnd.value = 650
    assert.deepEqual(form.filteredTimelineGroups.value.map((group) => [group.turnId, group.visibleItems.length]), [['t1', 0]])
  } finally { stop() }
})

test('跨 Run 范围筛选保持消息顺序，缺失时间窗口的记录仍可搜索', () => {
  const { form, stop } = setupComponent('debug')
  try {
    form.messageAudits.value = [
      { id: 1, type: 'human', run_id: 'r1', turn_id: 't1', content: '问题' },
      { id: 2, type: 'ai', run_id: 'r1', turn_id: 't1', content: '初次回答' },
      { id: 3, type: 'tool', run_id: 'r2', turn_id: 't1', content: '恢复工具' },
      { id: 4, type: 'ai', run_id: 'r2', turn_id: 't1', content: '恢复回答' },
      { id: 5, type: 'ai', run_id: 'r3', turn_id: 't1', content: '缺少时间窗口' }
    ]
    form.runTraces.value = [
      { run_id: 'r1', turn_id: 't1', timing: { created_at: '2026-10-16T00:00:00Z', total_latency_ms: 4000 } },
      { run_id: 'r2', turn_id: 't1', timing: { created_at: '2026-10-16T00:00:20Z', total_latency_ms: 4000 } },
      { run_id: 'r3', turn_id: 't1' }
    ]
    const visibleIds = () => form.filteredTimelineGroups.value.flatMap((group) =>
      group.visibleItems.map((item) => item.raw.id)
    )
    assert.deepEqual(visibleIds(), [1, 2, 3, 4, 5])
    form.timelineRangeStart.value = 625
    assert.deepEqual(visibleIds(), [3, 4, 5])
    form.currentFilter.value = 'ai'
    assert.deepEqual(visibleIds(), [4, 5])
    form.searchQuery.value = '缺少时间'
    assert.deepEqual(visibleIds(), [5])
    form.searchQuery.value = '初次回答'
    assert.deepEqual(visibleIds(), [])
  } finally { stop() }
})

test('调试面板使用 Turn 地址接口，切换会话后关闭迟到的跳转窗口', async () => {
  let finish
  const calls = []
  const panel = setupComponent('debug', { getTurnLangfuse: (...args) => {
    calls.push(args)
    return new Promise((resolve) => { finish = resolve })
  } })
  try {
    const pending = panel.form.openTurnInLangfuse('t1')
    assert.deepEqual(calls, [['thread-a', 't1']])
    panel.props.threadId = 'thread-b'
    finish({ turn_id: 't1', langfuse_url: 'https://langfuse.example/trace/t1' })
    await pending
    assert.equal(panel.windows[0].closed, true)
    assert.equal(panel.windows[0].url, undefined)
  } finally { panel.stop() }
})

test('两个入口均打开后端的 Turn Trace，缺失 Trace 时关闭空窗口并提示', async () => {
  for (const name of ['debug', 'feedback']) {
    for (const available of [true, false]) {
      const calls = []
      const panel = setupComponent(name, { getTurnLangfuse: async (...args) => {
        calls.push(args)
        return { turn_id: 't1', langfuse_trace_id: available ? 'trace-t1' : null, langfuse_url: available ? 'https://langfuse.example/trace/t1' : null }
      } })
      try {
        await panel.form.openTurnInLangfuse(name === 'debug' ? 't1' : { id: 'feedback-1', turn_id: 't1' })
        assert.deepEqual(calls, name === 'debug' ? [['thread-a', 't1']] : [['feedback-1']])
        assert.equal(panel.windows[0].opener, null)
        assert.equal(panel.windows[0].url, available ? 'https://langfuse.example/trace/t1' : undefined)
        assert.equal(panel.windows[0].closed, !available)
        if (!available) {
          const text = name === 'debug' ? panel.notices[0] : panel.form.traceError.value
          assert.match(text, /本轮暂无可用/)
        }
      } finally { panel.stop() }
    }
  }
})

test('反馈详情关闭后迟到的观测查询不继续跳转', async () => {
  let finish
  const panel = setupComponent('feedback', { getTurnLangfuse: () => new Promise((resolve) => { finish = resolve }) })
  try {
    panel.form.showDetails({ id: 'f1' }, { currentTarget: {} })
    await nextTick()
    const pending = panel.form.openTurnInLangfuse({ id: 'f1' })
    panel.form.detailOpen.value = false
    await nextTick()
    finish({ langfuse_url: 'https://langfuse.example/trace/t1' })
    await pending
    assert.equal(panel.windows[0].closed, true)
    assert.equal(panel.windows[0].url, undefined)
  } finally { panel.stop() }
})
